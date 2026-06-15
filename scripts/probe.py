#!/usr/bin/env python3
"""probe.py - exercise the pyegpm client against a REAL EnerGenie LAN strip.

This is the Phase 1 validation tool. It performs a real handshake + status read
and, optionally, switches a socket — the output is meant to be diffed against
`egctl <name>`.

Examples:
    # Read status (compare with: egctl regleta)
    python3 scripts/probe.py --host 192.168.1.3 --password testpass status

    # Turn socket 1 on / off (1-based on the CLI, like egctl/the physical label)
    python3 scripts/probe.py --host 192.168.1.3 --password testpass on 1
    python3 scripts/probe.py --host 192.168.1.3 --password testpass off 1

    # Read the password from the egtab file instead of the command line
    python3 scripts/probe.py --egtab ~/.egtab --name regleta status

Never logs the password. Use --debug to see the hex of the handshake frames.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running straight from the repo without installing the package: the
# standalone library is vendored inside the integration folder so it ships via
# HACS. It has no Home Assistant dependency, so it imports fine on its own.
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "energenie_lan"
    ),
)

from pyegpm import (  # noqa: E402
    DEFAULT_PORT,
    EnergenieAuthError,
    EnergenieClient,
    EnergenieConnectionError,
    EnergenieError,
)
from pyegpm.const import SUPPORTED_PROTOCOLS  # noqa: E402


def _parse_egtab(path: Path, name: str) -> dict[str, str]:
    """Minimal egtab parser (same columns as egctl): name type ip port pass."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 5 and parts[0] == name:
            return {
                "proto": parts[1],
                "host": parts[2],
                "port": parts[3],
                "password": parts[4],
            }
    raise SystemExit(f"Device {name!r} not found in {path}")


def _print_status(states: list[bool]) -> None:
    # Same layout as `egctl`: "socket N - on/off".
    for i, on in enumerate(states, start=1):
        print(f"socket {i} - {'on' if on else 'off'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="device IP address")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"TCP port (default {DEFAULT_PORT})"
    )
    parser.add_argument("--password", help="device password")
    parser.add_argument(
        "--proto",
        default="pms21",
        choices=SUPPORTED_PROTOCOLS,
        help="protocol to try first (default pms21; falls back automatically)",
    )
    parser.add_argument("--timeout", type=float, default=4.0, help="socket timeout (s)")
    parser.add_argument("--egtab", type=Path, help="read host/port/password from an egtab file")
    parser.add_argument("--name", help="device name in the egtab file (with --egtab)")
    parser.add_argument("--debug", action="store_true", help="show handshake hex (no secrets)")

    parser.add_argument(
        "command",
        choices=["status", "on", "off", "toggle"],
        help="action to perform",
    )
    parser.add_argument(
        "socket",
        nargs="?",
        type=int,
        help="socket number 1-4 (required for on/off/toggle)",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    host = args.host
    port = args.port
    password = args.password
    proto = args.proto

    if args.egtab:
        if not args.name:
            parser.error("--egtab requires --name")
        entry = _parse_egtab(args.egtab, args.name)
        host = host or entry["host"]
        port = entry["port"] and int(entry["port"]) or port
        password = password or entry["password"]
        proto = entry["proto"] if args.proto == "pms21" else args.proto

    if not host or not password:
        parser.error("--host and --password are required (or use --egtab/--name)")

    client = EnergenieClient(
        host, password, port=port, proto=proto, timeout=args.timeout
    )

    try:
        if args.command == "status":
            _print_status(client.get_status())
            return 0

        if args.socket is None or not 1 <= args.socket <= 4:
            parser.error(f"{args.command} requires a socket number 1-4")
        index = args.socket - 1  # CLI is 1-based, library is 0-based.

        if args.command == "toggle":
            current = client.get_status()
            desired = not current[index]
        else:
            desired = args.command == "on"

        states = client.set_socket(index, desired)
        _print_status(states)
        return 0

    except EnergenieAuthError as err:
        print(f"AUTH ERROR: {err}", file=sys.stderr)
        return 2
    except EnergenieConnectionError as err:
        print(f"CONNECTION ERROR: {err}", file=sys.stderr)
        return 3
    except EnergenieError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
