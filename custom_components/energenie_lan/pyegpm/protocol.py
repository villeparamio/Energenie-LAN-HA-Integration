"""Pure-Python port of the EnerGenie EG-PM(S)2-LAN native crypto / framing.

This module contains ONLY the wire-protocol arithmetic (key derivation,
challenge-response, status decrypt and control encrypt). It has no I/O and no
Home Assistant dependency, so it is trivially unit-testable against known
vectors.

Ported 1:1 from egctl by Vitaly Sinilin (MIT license):
    https://github.com/unterwulf/egctl  (egctl.c)
Cross-checked against asig/energenie native.go (Andreas Signer, GPLv3) — used
only for verification, no code copied from it.

Every function below cites the egctl function it comes from. The magic numbers
and arithmetic are EXACT; do not "simplify" them.
"""

from __future__ import annotations

from .const import (
    DONT_SWITCH,
    KEY_LEN,
    SOCKET_COUNT,
    STATE_INVALID,
    STATE_OFF,
    STATE_OFF_VOLTAGE,
    STATE_ON,
    STATE_ON_NO_VOLTAGE,
    SWITCH_OFF,
    SWITCH_ON,
    V21_STATE_OFF,
    V21_STATE_ON,
    WLAN_STATE_OFF,
    WLAN_STATE_ON,
)


def derive_key(password: str) -> bytes:
    """Build the 8-byte key from the password.

    egctl.c: consume_key()
        "Key should be padded with trailing spaces."
        memset(key.octets, 0x20, KEY_LEN); memcpy(key.octets, tok, keylen);
    Passwords longer than KEY_LEN are truncated to the first KEY_LEN chars.
    """
    raw = password.encode("ascii", errors="strict")
    if len(raw) > KEY_LEN:
        raw = raw[:KEY_LEN]
    # Pad with spaces (0x20) up to KEY_LEN.
    return raw.ljust(KEY_LEN, b"\x20")


def solve_task(task: bytes, key: bytes) -> bytes:
    """Compute the 4-byte challenge response from the 4-byte task and key.

    egctl.c: authorize()
        res.loword = ((task[0] ^ key[2]) * key[0])
                     ^ (key[6] | (key[4] << 8)) ^ task[2];
        res.loword = htole16(res.loword);
        res.hiword = ((task[1] ^ key[3]) * key[1])
                     ^ (key[7] | (key[5] << 8)) ^ task[3];
        res.hiword = htole16(res.hiword);
    The Res struct is packed {uint16 loword; uint16 hiword;} and the protocol is
    little-endian, so the 4 bytes on the wire are loword(LE) then hiword(LE).
    """
    if len(task) != 4:
        raise ValueError("task must be exactly 4 bytes")

    loword = (
        ((task[0] ^ key[2]) * key[0]) ^ (key[6] | (key[4] << 8)) ^ task[2]
    ) & 0xFFFF
    hiword = (
        ((task[1] ^ key[3]) * key[1]) ^ (key[7] | (key[5] << 8)) ^ task[3]
    ) & 0xFFFF

    # Little-endian 16-bit words, matching the packed Res struct + htole16().
    return bytes(
        (
            loword & 0xFF,
            (loword >> 8) & 0xFF,
            hiword & 0xFF,
            (hiword >> 8) & 0xFF,
        )
    )


def decrypt_status_raw(statcryp: bytes, key: bytes, task: bytes) -> list[int]:
    """Decrypt the 4-byte encrypted status into 4 raw state bytes.

    egctl.c: decrypt_status()
        for (i = 0; i < SOCKET_COUNT; i++)
            st.socket[i] =
                (((statcryp[3-i] - key[1]) ^ key[0]) - task[3]) ^ task[2];
    Result indexed by socket: index 0 == socket 1 ... index 3 == socket 4.

    C does the arithmetic in `int` and truncates to uint8_t on assignment.
    Python uses arbitrary-precision two's-complement, so masking the final
    result with 0xFF reproduces the C low-8-bits exactly (including the
    intermediate negative subtraction / XOR).
    """
    if len(statcryp) != SOCKET_COUNT:
        raise ValueError("statcryp must be exactly 4 bytes")

    out: list[int] = []
    for i in range(SOCKET_COUNT):
        val = ((((statcryp[3 - i] - key[1]) ^ key[0]) - task[3]) ^ task[2]) & 0xFF
        out.append(val)
    return out


def encrypt_controls(controls: list[int], key: bytes, task: bytes) -> bytes:
    """Encrypt the 4 control opcodes into the 4-byte control frame.

    egctl.c: send_controls()
        for (i = 0; i < SOCKET_COUNT; i++)
            ctrlcryp[i] =
                (((ctrl.socket[3-i] ^ task[2]) + task[3]) ^ key[0]) + key[1];
    `controls` is indexed by socket (index 0 == socket 1).
    """
    if len(controls) != SOCKET_COUNT:
        raise ValueError("controls must have exactly 4 entries")

    out = bytearray(SOCKET_COUNT)
    for i in range(SOCKET_COUNT):
        out[i] = (
            (((controls[3 - i] ^ task[2]) + task[3]) ^ key[0]) + key[1]
        ) & 0xFF
    return bytes(out)


# --- State interpretation ----------------------------------------------------
#
# egctl maps every protocol variant onto the v2.0 STATE_* constants and then
# decides on/off from those. We do the same, but keep the mapping per-variant so
# we can implement the pms21 -> pms20 fallback (CLAUDE.md requirement).

_V21_MAP = {V21_STATE_ON: STATE_ON, V21_STATE_OFF: STATE_OFF}
_WLAN_MAP = {WLAN_STATE_ON: STATE_ON, WLAN_STATE_OFF: STATE_OFF}
# v2.0 states are already "canonical".
_V20_VALID = {STATE_ON, STATE_ON_NO_VOLTAGE, STATE_OFF, STATE_OFF_VOLTAGE}

_ON_STATES = {STATE_ON, STATE_ON_NO_VOLTAGE}
_OFF_STATES = {STATE_OFF, STATE_OFF_VOLTAGE}


def _canonicalize(raw_state: int, proto: str) -> int:
    """Map a raw decrypted byte to a canonical v2.0 STATE_* value.

    egctl.c: convert_v21_state() / convert_wlan_state() / convert_status().
    Returns STATE_INVALID if the raw byte does not belong to `proto`.
    """
    if proto == "pms21":
        return _V21_MAP.get(raw_state, STATE_INVALID)
    if proto == "pmswlan":
        return _WLAN_MAP.get(raw_state, STATE_INVALID)
    # pms20: raw byte is already canonical.
    return raw_state if raw_state in _V20_VALID else STATE_INVALID


def interpret_states(raw_states: list[int], proto: str) -> list[int] | None:
    """Map 4 raw decrypted bytes to canonical v2.0 states for `proto`.

    Returns None if ANY socket is invalid for this protocol variant (used to
    detect the wrong protocol and trigger the fallback).
    """
    canonical = [_canonicalize(s, proto) for s in raw_states]
    if any(c == STATE_INVALID for c in canonical):
        return None
    return canonical


def states_to_bools(canonical: list[int]) -> list[bool]:
    """Convert canonical v2.0 STATE_* values to a simple on/off boolean list.

    A socket counts as "on" when the relay is closed (STATE_ON or
    STATE_ON_NO_VOLTAGE); see egctl.c get_state_str().
    """
    result: list[bool] = []
    for state in canonical:
        if state in _ON_STATES:
            result.append(True)
        elif state in _OFF_STATES:
            result.append(False)
        else:  # pragma: no cover - guarded by interpret_states()
            raise ValueError(f"invalid socket state 0x{state:02X}")
    return result


def build_controls(states: list[bool | None]) -> list[int]:
    """Build the control opcode list from desired states.

    egctl.c: construct_controls() — but explicit (no toggle): True -> SWITCH_ON,
    False -> SWITCH_OFF, None -> DONT_SWITCH (leave the socket untouched).
    """
    if len(states) != SOCKET_COUNT:
        raise ValueError("states must have exactly 4 entries")

    controls: list[int] = []
    for state in states:
        if state is None:
            controls.append(DONT_SWITCH)
        elif state:
            controls.append(SWITCH_ON)
        else:
            controls.append(SWITCH_OFF)
    return controls
