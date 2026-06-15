"""pyegpm - pure-Python client for EnerGenie EG-PM(S)2-LAN power strips.

Native LAN protocol (TCP/5000), 100% local. No cloud, no external binaries.

Protocol ported 1:1 from egctl (MIT, Vitaly Sinilin):
https://github.com/unterwulf/egctl
"""

from __future__ import annotations

from .client import (
    EnergenieAuthError,
    EnergenieClient,
    EnergenieConnectionError,
    EnergenieError,
    EnergenieProtocolError,
)
from .const import DEFAULT_PORT, PROTO_V20, PROTO_V21, PROTO_WLAN, SOCKET_COUNT

__all__ = [
    "EnergenieClient",
    "EnergenieError",
    "EnergenieConnectionError",
    "EnergenieAuthError",
    "EnergenieProtocolError",
    "DEFAULT_PORT",
    "SOCKET_COUNT",
    "PROTO_V20",
    "PROTO_V21",
    "PROTO_WLAN",
]

__version__ = "0.1.0"
