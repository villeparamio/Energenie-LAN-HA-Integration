"""The EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_PROTO, DEFAULT_PORT, DEFAULT_PROTO
from .coordinator import EnergenieDataUpdateCoordinator
from .pyegpm import EnergenieClient

PLATFORMS: list[Platform] = [Platform.SWITCH]

EnergenieConfigEntry = ConfigEntry[EnergenieDataUpdateCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: EnergenieConfigEntry
) -> bool:
    """Set up EnerGenie EG-PM2-LAN from a config entry."""
    client = EnergenieClient(
        host=entry.data[CONF_HOST],
        password=entry.data[CONF_PASSWORD],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        proto=entry.data.get(CONF_PROTO, DEFAULT_PROTO),
    )

    coordinator = EnergenieDataUpdateCoordinator(hass, entry, client)
    # Validate connectivity now; raises ConfigEntryNotReady on failure.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: EnergenieConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
