"""Switch platform for the EnerGenie EG-PM2-LAN integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EnergenieConfigEntry
from .const import (
    CONF_HOST,
    CONF_MAC,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SOCKET_COUNT,
)
from .coordinator import EnergenieDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergenieConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the 4 socket switches from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        EnergenieSocketSwitch(coordinator, entry, index)
        for index in range(SOCKET_COUNT)
    )


class EnergenieSocketSwitch(
    CoordinatorEntity[EnergenieDataUpdateCoordinator], SwitchEntity
):
    """A single switchable socket on the EnerGenie strip."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnergenieDataUpdateCoordinator,
        entry: EnergenieConfigEntry,
        index: int,
    ) -> None:
        super().__init__(coordinator)
        self._index = index

        # Identity is the config entry's UUID: stable across restarts and IP
        # changes, deterministic, and independent of the network. The native
        # protocol exposes no hardware id, so this is the standard HA approach.
        self._attr_unique_id = f"{entry.entry_id}_{index}"
        self._attr_translation_key = "socket"
        self._attr_translation_placeholders = {"number": str(index + 1)}

        # MAC is optional and purely cosmetic (a nicer device card / connection).
        mac = entry.data.get(CONF_MAC)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=f"EnerGenie ({entry.data[CONF_HOST]})",
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the socket is on, None if status is unknown."""
        data = self.coordinator.data
        if data is None or self._index >= len(data):
            return None
        return data[self._index]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the socket on (optimistic update + authoritative refresh)."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the socket off (optimistic update + authoritative refresh)."""
        await self._async_set(False)

    async def _async_set(self, state: bool) -> None:
        # Optimistic UI: reflect intent immediately...
        if self.coordinator.data is not None:
            optimistic = list(self.coordinator.data)
            optimistic[self._index] = state
            self.coordinator.async_set_updated_data(optimistic)
        # ...then send the command; the coordinator pushes the real status back.
        await self.coordinator.async_set_socket(self._index, state)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
