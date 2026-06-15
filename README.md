# EnerGenie EG-PM2-LAN — Home Assistant integration (local LAN)

Custom Home Assistant integration to control the 4 switchable sockets of a
**Gembird/EnerGenie EG-PM2-LAN** power strip over its **native LAN protocol**
(TCP port 5000). 100% local — the EnerGenie.com cloud is never used.

The protocol crypto/framing is a 1:1 port of [egctl](https://github.com/unterwulf/egctl)
(MIT). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Layout

```
pyegpm/                       Standalone client library (no HA dependency)
  const.py                    Protocol constants (ported from egctl)
  protocol.py                 Crypto/framing: key, challenge, status, controls
  client.py                   Synchronous TCP client (handshake, sessions, I/O)
custom_components/
  energenie_lan/              Home Assistant integration (Phase 2)
scripts/probe.py              CLI to validate the library against the real strip
tests/                        Unit tests incl. byte-exact check vs egctl C
reference/                    egctl + asig/energenie sources (porting only)
```

## Status

- **Phase 1 — protocol client: complete.** Byte-exact vs egctl (2000 random
  vectors), and `probe.py status` matches `egctl` against the real device.
- **Phase 2 — HA integration:** pending GATE 1 approval.

## Library usage

```python
from pyegpm import EnergenieClient

with EnergenieClient("192.168.1.3", "password", port=5000, proto="pms21") as c:
    print(c.get_status())     # [False, False, True, True]
    c.set_socket(0, True)     # turn socket 1 on
    c.set_all([True, True, False, False])
```

`proto` defaults to `pms21`; the client automatically falls back to `pms20`
(and `pmswlan`) when decoding status if the configured variant doesn't match.

## probe.py

```bash
# Read status (compare with: egctl regleta)
python3 scripts/probe.py --host 192.168.1.3 --password <pass> status

# Or pull host/password from an egtab file
python3 scripts/probe.py --egtab ~/.egtab --name regleta status

# Switch socket 1 (1-based, like the physical label)
python3 scripts/probe.py --host 192.168.1.3 --password <pass> on 1
python3 scripts/probe.py --host 192.168.1.3 --password <pass> off 1

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

## Notes / constraints

- Pure Python, no external binaries, no `subprocess` in the integration.
- The device accepts ~one TCP session at a time and drops idle connections, so
  every operation opens a fresh session (exactly like egctl).
- The password is never logged. Protocol debug logs are hex, without secrets.
