"""DataUpdateCoordinator for the EnerGenie EG-PM2-LAN integration.

The device accepts roughly one TCP session at a time and drops idle ones, so
ALL access (polls and commands) is serialized through a single asyncio.Lock and
executed in the executor (the client is blocking — never run it on the event
loop). See CLAUDE.md hard constraints.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .pyegpm import EnergenieClient, EnergenieError

_LOGGER = logging.getLogger(__name__)


class EnergenieDataUpdateCoordinator(DataUpdateCoordinator[list[bool]]):
    """Polls socket status and serializes every device access."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EnergenieClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
            config_entry=entry,
        )
        self.client = client
        # One lock for the whole device: never two overlapping sessions.
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> list[bool]:
        """Fetch the 4 socket states (serialized, in executor)."""
        async with self._lock:
            try:
                return await self.hass.async_add_executor_job(
                    self.client.get_status
                )
            except EnergenieError as err:
                # Marks entities unavailable; recovers automatically next poll.
                raise UpdateFailed(str(err)) from err

    async def async_set_socket(self, index: int, state: bool) -> None:
        """Switch one socket, then refresh — serialized with polling."""
        async with self._lock:
            try:
                new_states = await self.hass.async_add_executor_job(
                    self.client.set_socket, index, state
                )
            except EnergenieError as err:
                raise UpdateFailed(str(err)) from err
        # Push the authoritative post-command status to entities immediately.
        self.async_set_updated_data(new_states)
