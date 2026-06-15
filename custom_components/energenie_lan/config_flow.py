"""Config flow for the EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

import logging
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
from .helpers import get_mac_from_arp
from .pyegpm import (
    EnergenieAuthError,
    EnergenieClient,
    EnergenieConnectionError,
    EnergenieError,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> str | None:
    """Validate the connection with a REAL handshake + status read.

    Returns the resolved MAC (or None) on success; raises on failure.
    """
    client = EnergenieClient(
        host=data[CONF_HOST],
        password=data[CONF_PASSWORD],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        proto=data.get(CONF_PROTO, DEFAULT_PROTO),
    )
    # Blocking client -> run in executor, never on the event loop.
    await hass.async_add_executor_job(client.get_status)

    # Best-effort MAC (ARP cache populated by the connection we just made).
    return await hass.async_add_executor_job(get_mac_from_arp, data[CONF_HOST])


class EnergenieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnerGenie EG-PM2-LAN."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (host + password + optional port)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                mac = await _validate(self.hass, user_input)
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
                # Stable identity: MAC if we have it, else host:port.
                if mac:
                    unique_id = format_mac(mac)
                    user_input[CONF_MAC] = unique_id
                else:
                    unique_id = (
                        f"{user_input[CONF_HOST]}:"
                        f"{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                    )
                    user_input[CONF_MAC] = None

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input.get(CONF_PORT, DEFAULT_PORT),
                    }
                )

                return self.async_create_entry(
                    title=f"EnerGenie ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
