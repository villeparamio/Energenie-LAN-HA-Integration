"""Protocol constants for the EnerGenie EG-PM(S)2-LAN native LAN protocol.

All values are ported 1:1 from egctl (egctl.c) by Vitaly Sinilin (MIT license):
https://github.com/unterwulf/egctl
Cross-checked against asig/energenie (native.go).

DO NOT change these magic numbers: they are part of the wire protocol.
"""

from __future__ import annotations

# egctl.c: SOCKET_COUNT
SOCKET_COUNT = 4

# Lengths of the fixed-size frames (egctl.c: TASK_LEN/STATCRYP_LEN/CTRLCRYP_LEN/KEY_LEN)
TASK_LEN = 4
STATCRYP_LEN = 4
CTRLCRYP_LEN = 4
KEY_LEN = 8

# Protocol v2.0 decrypted socket states (egctl.c: STATE_*)
STATE_ON = 0x11
STATE_ON_NO_VOLTAGE = 0x12
STATE_OFF = 0x22
STATE_OFF_VOLTAGE = 0x21
STATE_INVALID = 0xFF  # internal use only (egctl.c: STATE_INVALID)

# Protocol v2.1 decrypted socket states (egctl.c: V21_STATE_*)
V21_STATE_ON = 0x41
V21_STATE_OFF = 0x82

# WLAN variant decrypted socket states (egctl.c: WLAN_STATE_*)
WLAN_STATE_ON = 0x51
WLAN_STATE_OFF = 0x92

# Control opcodes (egctl.c: SWITCH_ON/SWITCH_OFF/DONT_SWITCH)
SWITCH_ON = 0x01
SWITCH_OFF = 0x02
DONT_SWITCH = 0x04

# "Start condition" byte sent to open / close a session (egctl.c: establish_connection / close_session)
START_BYTE = b"\x11"

# Default device TCP port (the native protocol lives on 5000, NOT the :80 web server).
DEFAULT_PORT = 5000

# Supported protocol identifiers (match egctl egtab "type" column).
PROTO_V20 = "pms20"
PROTO_V21 = "pms21"
PROTO_WLAN = "pmswlan"

SUPPORTED_PROTOCOLS = (PROTO_V21, PROTO_V20, PROTO_WLAN)
