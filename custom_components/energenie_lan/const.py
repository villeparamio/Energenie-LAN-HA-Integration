"""Constants for the EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "energenie_lan"

# Config entry keys.
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_PASSWORD: Final = "password"
CONF_PROTO: Final = "proto"
CONF_MAC: Final = "mac"

# Defaults.
DEFAULT_PORT: Final = 5000
DEFAULT_PROTO: Final = "pms21"

# Polling interval (CLAUDE.md: 5-10 s). 7 s is a safe middle ground that keeps
# the single-session device responsive without hammering it.
DEFAULT_SCAN_INTERVAL: Final = 7

# Number of switchable AC sockets.
SOCKET_COUNT: Final = 4

MANUFACTURER: Final = "EnerGenie / Gembird"
MODEL: Final = "EG-PM2-LAN"
