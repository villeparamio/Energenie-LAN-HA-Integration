"""Config flow for the EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_HOST,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_PROTO,
    DEFAULT_PORT,
    DEFAULT_PROTO,
    DOMAIN,
)
from .pyegpm import (
    EnergenieAuthError,
    EnergenieClient,
    EnergenieConnectionError,
    EnergenieError,
)

_LOGGER = logging.getLogger(__name__)

_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        # Optional, only for a nicer device card. The label on the strip is
        # 88:B6:27:xx:xx:xx. Identity does NOT depend on this (we use entry_id).
        vol.Optional(CONF_MAC, default=""): str,
    }
)


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the connection with a REAL handshake + status read."""
    client = EnergenieClient(
        host=data[CONF_HOST],
        password=data[CONF_PASSWORD],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        proto=data.get(CONF_PROTO, DEFAULT_PROTO),
    )
    # Blocking client -> run in executor, never on the event loop.
    await hass.async_add_executor_job(client.get_status)


class EnergenieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnerGenie EG-PM2-LAN."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (host + password + optional port/MAC)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac_raw = (user_input.get(CONF_MAC) or "").strip()
            if mac_raw and not _MAC_RE.match(mac_raw):
                errors[CONF_MAC] = "invalid_mac"

            if not errors:
                # Prevent adding the same strip twice: it only accepts ONE TCP
                # session, so two entries (two coordinators) would fight over it.
                unique_id = (
                    f"{user_input[CONF_HOST]}:"
                    f"{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                try:
                    await _validate(self.hass, user_input)
                except EnergenieAuthError:
                    errors["base"] = "invalid_auth"
                except EnergenieConnectionError:
                    errors["base"] = "cannot_connect"
                except EnergenieError:
                    # Decoded nothing / unexpected protocol response.
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001 - surface unknowns cleanly
                    _LOGGER.exception("Unexpected error validating EnerGenie device")
                    errors["base"] = "unknown"
                else:
                    # Normalize the (optional) MAC; store None when absent.
                    user_input[CONF_MAC] = format_mac(mac_raw) if mac_raw else None
                    return self.async_create_entry(
                        title=f"EnerGenie ({user_input[CONF_HOST]})",
                        data=user_input,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
