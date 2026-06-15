"""Standalone synchronous client for the EnerGenie EG-PM(S)2-LAN strip.

No Home Assistant dependency. All network I/O is blocking sockets, so the HA
layer must run these calls in an executor (see custom_components/energenie_lan).

Session model (mirrors egctl, the validation oracle): the device accepts roughly
ONE TCP session at a time and drops idle connections, so every public operation
opens a fresh session (connect -> start -> authorize -> ... -> close). This is
exactly what `egctl` does per invocation and is the most robust approach.

Ported from egctl (MIT, Vitaly Sinilin): https://github.com/unterwulf/egctl
"""

from __future__ import annotations

import logging
import select
import socket
from contextlib import contextmanager
from typing import Iterator

from .const import (
    DEFAULT_PORT,
    PROTO_V20,
    PROTO_V21,
    PROTO_WLAN,
    SOCKET_COUNT,
    START_BYTE,
    STATCRYP_LEN,
    TASK_LEN,
)
from .protocol import (
    build_controls,
    decrypt_status_raw,
    derive_key,
    encrypt_controls,
    interpret_states,
    solve_task,
    states_to_bools,
)

_LOGGER = logging.getLogger(__name__)

# egctl.c establish_connection(): 4 attempts, 125 ms each, sending the start byte.
_START_ATTEMPTS = 4
_START_WAIT = 0.125
# egctl.c authorize(): 4 second wait for the post-auth status frame.
_AUTH_WAIT = 4.0


class EnergenieError(Exception):
    """Base error for the EnerGenie LAN client."""


class EnergenieConnectionError(EnergenieError):
    """Could not reach / talk to the device (timeout, refused, reset...)."""


class EnergenieAuthError(EnergenieError):
    """Authorization failed (wrong password) — device stayed silent."""


class EnergenieProtocolError(EnergenieError):
    """Device responded but the bytes could not be decoded for any protocol."""


def _hex(data: bytes) -> str:
    """Hex dump for debug logging. NEVER used on the password/key."""
    return " ".join(f"{b:02X}" for b in data)


class EnergenieClient:
    """Synchronous client for one EnerGenie LAN power strip.

    Usage:
        with EnergenieClient(host, password) as client:
            states = client.get_status()   # list[bool] of length 4
            client.set_socket(0, True)
    """

    def __init__(
        self,
        host: str,
        password: str,
        port: int = DEFAULT_PORT,
        proto: str = PROTO_V21,
        timeout: float = 4.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        # Protocol to try first; the others are used as fallback on decode.
        self._proto = proto
        self._key = derive_key(password)
        # Order of protocols to attempt when decoding status: configured first.
        self._proto_order = [proto] + [
            p for p in (PROTO_V21, PROTO_V20, PROTO_WLAN) if p != proto
        ]

    # --- context manager (CLAUDE.md: connect()/close()) ----------------------
    # Operations are self-contained sessions, so the context manager is just a
    # convenience wrapper; nothing to keep open between calls.
    def __enter__(self) -> "EnergenieClient":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    # --- low-level session ---------------------------------------------------
    @contextmanager
    def _session(self) -> Iterator[tuple[socket.socket, bytes]]:
        """Open a session and yield (sock, task) ready for status/control.

        Performs: TCP connect -> establish (start byte) -> authorize.
        Always closes the socket, sending the start byte to release the device
        without the 4 s server-side idle timeout (egctl.c close_session()).
        """
        try:
            sock = socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            )
        except OSError as err:
            raise EnergenieConnectionError(
                f"Unable to connect to {self.host}:{self.port}: {err}"
            ) from err

        try:
            sock.settimeout(self.timeout)
            self._establish(sock)
            task = self._authorize(sock)
            yield sock, task
        finally:
            try:
                # egctl.c close_session(): an invalid sequence frees the device.
                sock.sendall(START_BYTE)
            except OSError:
                pass
            sock.close()

    def _establish(self, sock: socket.socket) -> None:
        """egctl.c establish_connection().

        The device ignores the first Start condition while still on timeout from
        a previous session, so retry up to 4 times waiting 125 ms each.
        """
        for _ in range(_START_ATTEMPTS):
            try:
                sock.sendall(START_BYTE)
            except OSError as err:
                raise EnergenieConnectionError(f"Send failed: {err}") from err
            ready, _, _ = select.select([sock], [], [], _START_WAIT)
            if ready:
                return
        raise EnergenieConnectionError(
            "Unable to establish connection with device (no response to start)"
        )

    def _authorize(self, sock: socket.socket) -> bytes:
        """egctl.c authorize(): read 4-byte task, send response, await status.

        The device has no explicit auth-failure reply; the only signal is a
        timeout while waiting for the status frame, which we map to auth error.
        """
        task = self._recv_exact(sock, TASK_LEN)
        _LOGGER.debug("task: %s", _hex(task))

        response = solve_task(task, self._key)
        _LOGGER.debug("res:  %s", _hex(response))
        try:
            sock.sendall(response)
        except OSError as err:
            raise EnergenieConnectionError(f"Send failed: {err}") from err

        # Wait for the post-auth status frame; silence == bad password.
        ready, _, _ = select.select([sock], [], [], _AUTH_WAIT)
        if not ready:
            raise EnergenieAuthError(
                "Authorization failed (no response — wrong password?)"
            )
        return task

    def _recv_exact(self, sock: socket.socket, count: int) -> bytes:
        """Read exactly `count` bytes or raise (egctl.c xread())."""
        chunks: list[bytes] = []
        remaining = count
        while remaining > 0:
            try:
                chunk = sock.recv(remaining)
            except socket.timeout as err:
                raise EnergenieConnectionError(
                    f"Timed out reading from device after {self.timeout}s"
                ) from err
            except OSError as err:
                raise EnergenieConnectionError(f"Read failed: {err}") from err
            if not chunk:
                raise EnergenieConnectionError("Device closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_status(self, sock: socket.socket, task: bytes) -> list[bool]:
        """Read + decrypt + interpret one status frame (egctl.c recv_status()).

        Tries the configured protocol first, then the others (pms21 -> pms20
        fallback per CLAUDE.md). Returns a list[bool] of length 4.
        """
        statcryp = self._recv_exact(sock, STATCRYP_LEN)
        _LOGGER.debug("statcryp: %s", _hex(statcryp))
        raw = decrypt_status_raw(statcryp, self._key, task)

        for proto in self._proto_order:
            canonical = interpret_states(raw, proto)
            if canonical is not None:
                if proto != self._proto:
                    _LOGGER.debug(
                        "decoded status using fallback protocol %s", proto
                    )
                return states_to_bools(canonical)

        raise EnergenieProtocolError(
            "Could not decode status for any known protocol "
            f"(raw decrypted bytes: {_hex(bytes(raw))})"
        )

    # --- public API ----------------------------------------------------------
    def get_status(self) -> list[bool]:
        """Return the on/off state of the 4 sockets (index 0 == socket 1)."""
        with self._session() as (sock, task):
            return self._recv_status(sock, task)

    def set_socket(self, index: int, state: bool) -> list[bool]:
        """Switch a single socket (0-based) on/off; leave the rest untouched.

        Returns the resulting status. Mirrors egctl's status -> control ->
        status sequence within one session.
        """
        if not 0 <= index < SOCKET_COUNT:
            raise ValueError(f"socket index out of range: {index}")
        desired: list[bool | None] = [None] * SOCKET_COUNT
        desired[index] = state
        return self._switch(desired)

    def set_all(self, states: list[bool]) -> list[bool]:
        """Set all 4 sockets at once. Returns the resulting status."""
        if len(states) != SOCKET_COUNT:
            raise ValueError("states must have exactly 4 entries")
        return self._switch(list(states))

    def _switch(self, desired: list[bool | None]) -> list[bool]:
        """One session: consume status, send controls, read new status."""
        controls = build_controls(desired)
        with self._session() as (sock, task):
            # egctl.c main(): recv_status() BEFORE send_controls() — the device
            # has already queued the post-auth status frame; we must drain it.
            self._recv_status(sock, task)
            ctrlcryp = encrypt_controls(controls, self._key, task)
            _LOGGER.debug("ctrlcryp: %s", _hex(ctrlcryp))
            try:
                sock.sendall(ctrlcryp)
            except OSError as err:
                raise EnergenieConnectionError(f"Send failed: {err}") from err
            return self._recv_status(sock, task)
