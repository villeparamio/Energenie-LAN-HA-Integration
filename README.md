# EnerGenie EG-PM2-LAN — Home Assistant integration (local LAN)

Custom Home Assistant integration to control the 4 switchable sockets of a
**Gembird/EnerGenie EG-PM2-LAN** power strip over its **native LAN protocol**
(TCP port 5000). 100% local — the EnerGenie.com cloud is never used.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/villeparamio/Energenie-LAN-HA-Integration/actions/workflows/validate.yml/badge.svg)](https://github.com/villeparamio/Energenie-LAN-HA-Integration/actions/workflows/validate.yml)

The protocol crypto/framing is a 1:1 port of [egctl](https://github.com/unterwulf/egctl)
(MIT). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=villeparamio&repository=Energenie-LAN-HA-Integration&category=integration)

## Layout

```
custom_components/energenie_lan/
  pyegpm/                     Standalone client library (no HA dependency)
    const.py                  Protocol constants (ported from egctl)
    protocol.py               Crypto/framing: key, challenge, status, controls
    client.py                 Synchronous TCP client (handshake, sessions, I/O)
  manifest.json               Integration manifest (config_flow, local_polling)
  const.py                    Integration constants
  __init__.py                 Setup + config entry wiring
  coordinator.py              DataUpdateCoordinator (serialized, in executor)
  config_flow.py              UI setup, validates with a real handshake
  switch.py                   4 SwitchEntity (one per socket)
  strings.json, translations/ en + es
scripts/probe.py              CLI to validate the library against the real strip
tests/                        Unit + fake-device tests, byte-exact check vs egctl C
reference/                    egctl + asig/energenie sources (porting only)
```

The standalone library lives inside the integration folder so the whole thing
ships as a single HACS package; it still has zero Home Assistant dependencies.

## Status

- **Phase 1 — protocol client: complete.** Byte-exact vs egctl (2000 random
  vectors), and `probe.py status` matches `egctl` against the real device.
- **Phase 2 — HA integration: complete.** Config flow, coordinator, 4 switches,
  en/es translations. Pending GATE 2 validation in real HA.

## Installation

**Requires Home Assistant ≥ 2024.6** (uses `entry.runtime_data`).

This is not (yet) in the HACS default store, so add it as a **custom repository**.

### Option A — HACS (recommended)

1. In Home Assistant go to **HACS**.
2. Top-right menu **⋮ → Custom repositories**.
3. **Repository:** `https://github.com/villeparamio/Energenie-LAN-HA-Integration`
   **Category:** `Integration` → **Add**.
4. Search for **"EnerGenie EG-PM2-LAN"** in HACS and **Download** it.
5. **Restart Home Assistant** (Settings → System → Restart).

### Option B — Manual

Copy the integration folder into your HA config directory and restart:

```bash
cp -r custom_components/energenie_lan /config/custom_components/
```

After restarting, `/config/custom_components/energenie_lan/` should exist.

## Configuration (UI)

1. **Settings → Devices & Services → + Add Integration**.
2. Search for **EnerGenie** and pick **"EnerGenie EG-PM2-LAN"**.
3. Fill in the form:
   - **IP address** — the strip's local IP.
   - **Password** — the device password.
   - **Port** — `5000` (default).
   - **MAC** — optional, only for a nicer device card (the `88:B6:27:…` on the label).
4. **Submit.**

On success you get one device with **4 switches** (Socket 1-4) that control the
strip locally. Form errors: *invalid auth* = wrong password; *cannot connect* =
wrong IP/port, strip powered off, or HA can't reach it (common when HA runs in a
Docker **bridge/NAT** network and the strip is on another subnet — use
`network_mode: host` / macvlan, or put both on the same network).

Entity/device identity is the config entry's UUID (`entry_id`): stable across
restarts and IP changes, deterministic, and independent of the network — the
native protocol exposes no hardware id. Adding the same `host:port` twice is
rejected, since the device only accepts one TCP session at a time.

## Library usage

```python
from pyegpm import EnergenieClient

with EnergenieClient("192.168.x.x", "password", port=5000, proto="pms21") as c:
    print(c.get_status())     # [False, False, True, True]
    c.set_socket(0, True)     # turn socket 1 on
    c.set_all([True, True, False, False])
```

`proto` defaults to `pms21`; the client automatically falls back to `pms20`
(and `pmswlan`) when decoding status if the configured variant doesn't match.

## probe.py

```bash
# Read status (compare with: egctl regleta)
python3 scripts/probe.py --host 192.168.x.x --password <pass> status

# Or pull host/password from an egtab file
python3 scripts/probe.py --egtab ~/.egtab --name regleta status

# Switch socket 1 (1-based, like the physical label)
python3 scripts/probe.py --host 192.168.x.x --password <pass> on 1
python3 scripts/probe.py --host 192.168.x.x --password <pass> off 1

# Show handshake hex (no secrets) for forensic comparison
python3 scripts/probe.py --egtab ~/.egtab --name regleta --debug status
```

## Tests

```bash
python3 -m pytest tests/ -q
```

The `test_byte_exact_vs_egctl_c` test compiles `tests/egctl_ref.c` (the exact C
arithmetic from egctl) and checks the Python port matches byte-for-byte. It is
skipped automatically if no C compiler is present.