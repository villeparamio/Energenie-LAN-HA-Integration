"""Best-effort helpers for the EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

_ARP_TABLE = "/proc/net/arp"


def get_mac_from_arp(host: str) -> str | None:
    """Resolve the device MAC from the kernel ARP cache (pure Python).

    Reads /proc/net/arp directly — no subprocess, no external binary (CLAUDE.md
    hard constraint). Returns a lowercase ``aa:bb:cc:dd:ee:ff`` string, or None
    if the entry is not present.

    Note: ARP is link-local. This only works when Home Assistant shares an L2
    segment with the device (host networking / macvlan). With a NAT bridge the
    entry won't be there and we fall back to a host-based identity. This is a
    deliberate best-effort: never block setup on it.
    """
    try:
        with open(_ARP_TABLE, encoding="ascii") as fh:
            lines = fh.readlines()
    except OSError as err:
        _LOGGER.debug("Could not read %s: %s", _ARP_TABLE, err)
        return None

    # Skip the header row. Columns: IP, HW type, Flags, HW address, Mask, Device
    for line in lines[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[0] == host:
            mac = fields[3].lower()
            if mac and mac != "00:00:00:00:00:00":
                return mac
    return None
