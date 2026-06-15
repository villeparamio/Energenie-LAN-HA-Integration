"""Unit tests for pyegpm.protocol.

The strong test is `test_byte_exact_vs_egctl_c`: it compiles the reference C
arithmetic (copied verbatim from egctl.c) and checks the Python port produces
identical bytes over many random inputs. This is the wire-level proof that the
port is correct; it is skipped automatically if no C compiler is available.
"""

from __future__ import annotations

import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyegpm import const  # noqa: E402
from pyegpm.protocol import (  # noqa: E402
    build_controls,
    decrypt_status_raw,
    derive_key,
    encrypt_controls,
    interpret_states,
    solve_task,
    states_to_bools,
)

HERE = Path(__file__).resolve().parent


# --- pure-Python sanity checks ----------------------------------------------


def test_derive_key_pads_with_spaces():
    assert derive_key("1") == b"1\x20\x20\x20\x20\x20\x20\x20"
    assert derive_key("testpass") == b"testpass"


def test_derive_key_truncates_long_password():
    assert derive_key("0123456789") == b"01234567"


def test_solve_task_endianness():
    # loword/hiword must be packed little-endian (4 bytes total).
    key = derive_key("testpass")
    task = bytes([0x12, 0x34, 0x56, 0x78])
    res = solve_task(task, key)
    assert len(res) == 4
    loword = ((task[0] ^ key[2]) * key[0]) ^ (key[6] | (key[4] << 8)) ^ task[2]
    hiword = ((task[1] ^ key[3]) * key[1]) ^ (key[7] | (key[5] << 8)) ^ task[3]
    assert res == struct.pack("<HH", loword & 0xFFFF, hiword & 0xFFFF)


def test_interpret_states_v21():
    raw = [const.V21_STATE_ON, const.V21_STATE_OFF, const.V21_STATE_ON, const.V21_STATE_OFF]
    canonical = interpret_states(raw, const.PROTO_V21)
    assert canonical is not None
    assert states_to_bools(canonical) == [True, False, True, False]


def test_interpret_states_v20():
    raw = [const.STATE_ON, const.STATE_OFF, const.STATE_ON_NO_VOLTAGE, const.STATE_OFF_VOLTAGE]
    canonical = interpret_states(raw, const.PROTO_V20)
    assert canonical is not None
    assert states_to_bools(canonical) == [True, False, True, False]


def test_interpret_states_wrong_proto_returns_none():
    # v2.1 bytes are invalid under the v2.0 interpreter.
    raw = [const.V21_STATE_ON] * 4
    assert interpret_states(raw, const.PROTO_V20) is None


def test_build_controls():
    assert build_controls([True, False, None, None]) == [
        const.SWITCH_ON,
        const.SWITCH_OFF,
        const.DONT_SWITCH,
        const.DONT_SWITCH,
    ]


def test_encrypt_decrypt_are_consistent():
    # decrypt(statcryp) and encrypt(controls) use mirrored arithmetic; verify
    # that a control frame round-trips through the decrypt math back to the
    # opcode (sanity, not a protocol requirement).
    key = derive_key("testpass")
    task = bytes([0xAA, 0xBB, 0xCC, 0xDD])
    controls = [0x01, 0x02, 0x04, 0x01]
    enc = encrypt_controls(controls, key, task)
    dec = decrypt_status_raw(enc, key, task)
    assert dec == controls


# --- byte-exact equivalence vs the C reference ------------------------------


@pytest.fixture(scope="module")
def egctl_ref(tmp_path_factory) -> Path:
    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        pytest.skip("no C compiler available to build the egctl reference")
    out = tmp_path_factory.mktemp("ref") / "egctl_ref"
    subprocess.run(
        [cc, "-O2", "-o", str(out), str(HERE / "egctl_ref.c")],
        check=True,
    )
    return out


def _ref(binary: Path, mode: str, key: bytes, task: bytes, data: bytes = b"") -> bytes:
    args = [str(binary), mode, key.hex(), task.hex(), data.hex() or "-"]
    res = subprocess.run(args, capture_output=True, text=True, check=True)
    return bytes.fromhex(res.stdout.strip())


def test_byte_exact_vs_egctl_c(egctl_ref):
    rng = random.Random(1234)
    for _ in range(2000):
        key = bytes(rng.randrange(256) for _ in range(8))
        task = bytes(rng.randrange(256) for _ in range(4))
        statcryp = bytes(rng.randrange(256) for _ in range(4))
        controls = [rng.choice([0x01, 0x02, 0x04]) for _ in range(4)]

        # solve_task
        assert solve_task(task, key) == _ref(egctl_ref, "solve", key, task)

        # decrypt_status_raw (C returns sockets 1..4 == python index 0..3)
        py_dec = bytes(decrypt_status_raw(statcryp, key, task))
        assert py_dec == _ref(egctl_ref, "decrypt", key, task, statcryp)

        # encrypt_controls
        py_enc = encrypt_controls(controls, key, task)
        assert py_enc == _ref(egctl_ref, "encrypt", key, task, bytes(controls))
