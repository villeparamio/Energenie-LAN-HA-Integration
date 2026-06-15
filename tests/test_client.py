"""End-to-end tests for EnergenieClient against an in-process fake device.

The fake server speaks the real protocol (using the proven-correct crypto from
pyegpm.protocol), so these tests exercise the full client I/O path — establish,
authorize, status read, control round-trip, wrong-password timeout, and clean
errors on an unreachable/closed peer — without touching the real hardware.
"""

from __future__ import annotations

import socket
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "energenie_lan"
    ),
)

from pyegpm import const  # noqa: E402
from pyegpm.client import (  # noqa: E402
    EnergenieAuthError,
    EnergenieClient,
    EnergenieConnectionError,
)
from pyegpm.protocol import (  # noqa: E402
    decrypt_status_raw,
    derive_key,
    encrypt_controls,
    solve_task,
)

PASSWORD = "testpass"
# Fixed task so the test is deterministic.
TASK = bytes([0x12, 0x34, 0x56, 0x78])

# Per-socket raw v2.1 state bytes for a desired on/off.
_RAW_ON = const.V21_STATE_ON
_RAW_OFF = const.V21_STATE_OFF


def _encode_status(states: list[bool], key: bytes) -> bytes:
    """Server side: encrypt the 4 socket states into a status frame."""
    raw = [_RAW_ON if on else _RAW_OFF for on in states]
    # encrypt_controls is the exact inverse of decrypt_status_raw, so the client
    # will decrypt this back into `raw`.
    return encrypt_controls(raw, key, TASK)


class FakeDevice:
    """A minimal one-shot EnerGenie LAN server for a single session."""

    def __init__(self, states: list[bool], *, accept_auth: bool = True) -> None:
        self.states = list(states)
        self.accept_auth = accept_auth
        self.key = derive_key(PASSWORD)
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(1)
        self.port = self._srv.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        try:
            self._srv.close()
        except OSError:
            pass

    def _serve(self) -> None:
        try:
            conn, _ = self._srv.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(5.0)
            try:
                self._session(conn)
            except (OSError, ValueError):
                pass

    def _session(self, conn: socket.socket) -> None:
        # 1) start byte
        start = conn.recv(1)
        if start != const.START_BYTE:
            return
        # 2) send task challenge
        conn.sendall(TASK)
        # 3) read 4-byte response and validate
        resp = self._recv(conn, 4)
        if resp != solve_task(TASK, self.key):
            # Wrong password: the real device stays connected but silent, so the
            # client detects the failure via timeout. Hold the socket open
            # (sending nothing) until the client gives up and closes.
            try:
                while conn.recv(16):
                    pass
            except OSError:
                pass
            return
        if not self.accept_auth:
            return
        # 4) send current status
        conn.sendall(_encode_status(self.states, self.key))
        # 5) optionally read a control frame (4 bytes) or close byte (1 byte)
        try:
            data = conn.recv(4)
        except socket.timeout:
            return
        if len(data) == 4:
            controls = decrypt_status_raw(data, self.key, TASK)
            for i, op in enumerate(controls):
                if op == const.SWITCH_ON:
                    self.states[i] = True
                elif op == const.SWITCH_OFF:
                    self.states[i] = False
            conn.sendall(_encode_status(self.states, self.key))

    @staticmethod
    def _recv(conn: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf


@pytest.fixture
def device():
    dev = FakeDevice([False, False, True, True])
    dev.start()
    yield dev
    dev.close()


def _client(port: int, **kw) -> EnergenieClient:
    return EnergenieClient("127.0.0.1", PASSWORD, port=port, timeout=2.0, **kw)


def test_get_status(device):
    assert _client(device.port).get_status() == [False, False, True, True]


def test_set_socket_on(device):
    result = _client(device.port).set_socket(0, True)
    assert result == [True, False, True, True]


def test_set_socket_off():
    dev = FakeDevice([True, True, True, True])
    dev.start()
    try:
        assert _client(dev.port).set_socket(2, False) == [True, True, False, True]
    finally:
        dev.close()


def test_wrong_password_raises_auth_error():
    dev = FakeDevice([False, False, False, False])
    dev.start()
    try:
        client = EnergenieClient("127.0.0.1", "wrongpass", port=dev.port, timeout=1.0)
        with pytest.raises(EnergenieAuthError):
            client.get_status()
    finally:
        dev.close()


def test_unreachable_port_raises_connection_error():
    # Nothing listening on this port -> clean connection error, no hang.
    client = EnergenieClient("127.0.0.1", PASSWORD, port=1, timeout=1.0)
    with pytest.raises(EnergenieConnectionError):
        client.get_status()


def test_server_closes_immediately_raises_connection_error():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        conn.close()  # drop right after accept

    threading.Thread(target=serve, daemon=True).start()
    try:
        client = EnergenieClient("127.0.0.1", PASSWORD, port=port, timeout=1.0)
        with pytest.raises(EnergenieConnectionError):
            client.get_status()
    finally:
        srv.close()
