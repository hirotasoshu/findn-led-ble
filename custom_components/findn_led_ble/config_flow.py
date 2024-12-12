"""Adds config flow for Blueprint."""

from __future__ import annotations

import asyncio
from logging import Logger, getLogger
from typing import Any, override

import voluptuous as vol
from bleak_retry_connector import BLEAK_RETRY_EXCEPTIONS as BLEAK_EXCEPTIONS
from bluetooth_data_tools import human_readable_name
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, LOCAL_NAME
from .device import FindnLedDevice

logger: Logger = getLogger(__name__)


class FindnLedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yale Access Bluetooth."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)  # pyright: ignore [reportUnusedCallResult]
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": human_readable_name(
                None, discovery_info.name, discovery_info.address
            )
        }
        return await self.async_step_user()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address: Any = user_input[CONF_ADDRESS]  # pyright: ignore [reportAny]
            discovery_info = self._discovered_devices[address]
            local_name = discovery_info.name
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )  # pyright: ignore [reportUnusedCallResult]
            self._abort_if_unique_id_configured()
            device = FindnLedDevice(discovery_info.device)
            try:
                await device.update()
                await device.turn_on()
                await asyncio.sleep(0.2)
                await device.turn_off()
                await asyncio.sleep(0.2)
                await device.turn_on()
                await asyncio.sleep(0.2)
                await device.turn_off()
            except BLEAK_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:
                logger.exception("Unexpected error")
                errors["base"] = "unknown"
            else:
                await device.stop()
                return self.async_create_entry(
                    title=local_name,
                    data={
                        CONF_ADDRESS: discovery_info.address,
                    },
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
        else:
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or not discovery.name.startswith(LOCAL_NAME)
                ):
                    continue
                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: (
                            f"{service_info.name} ({service_info.address})"
                        )
                        for service_info in self._discovered_devices.values()
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
