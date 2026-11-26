import asyncio
import logging
from typing import Any

import aiohttp
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    domain_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = domain_data["coordinator"]
    async_add_entities([SagemcomGuestWiFiSwitch(coordinator, entry.entry_id)])


class SagemcomGuestWiFiSwitch(CoordinatorEntity, SwitchEntity):
    """Switch tracking and driving the operational bounds of Guest broadcasts."""

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self.entry_id = entry_id
        self._attr_unique_id = f"sagemcom_{entry_id}_guest_wifi_toggle"
        self._attr_name = "Guest Wireless Access"
        self._attr_icon = "mdi:wifi-lock"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_wifi_guest")},
            name="Guest Wi-Fi Network",
            manufacturer="Sagemcom Network",
            via_device=(DOMAIN, entry_id),
        )

    def _get_guest_band_data(self, data_key: str, band_key: str) -> dict[str, Any]:
        """Safely extract the guest band dictionary from coordinator data."""
        if not self.coordinator.data:
            return {}
        entries = self.coordinator.data.get(data_key)
        if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
            return {}
        band_data = entries[0].get(band_key)
        return band_data if isinstance(band_data, dict) else {}

    def _get_guest_ssids(self) -> tuple[str, str]:
        """Return each guest band's current SSID or raise HomeAssistantError."""
        if not self.coordinator.data:
            raise HomeAssistantError("Guest Wi-Fi data is not available from the router")

        ssid_24 = self._get_guest_band_data("wifi_guest24", "guest24").get("ssid")
        if not isinstance(ssid_24, str) or not ssid_24:
            raise HomeAssistantError(
                "Cannot read current 2.4 GHz Guest Wi-Fi SSID from router data"
            )

        ssid_5 = self._get_guest_band_data("wifi_guest5", "guest5").get("ssid")
        if not isinstance(ssid_5, str) or not ssid_5:
            raise HomeAssistantError(
                "Cannot read current 5 GHz Guest Wi-Fi SSID from router data"
            )

        return ssid_24, ssid_5

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False

        # Check the flattened guest structure for activation flag
        g24_en = self._get_guest_band_data("wifi_guest24", "guest24").get("enable", "false")
        g5_en = self._get_guest_band_data("wifi_guest5", "guest5").get("enable", "false")

        return str(g24_en).lower() == "true" or str(g5_en).lower() == "true"

    async def _async_trigger_put(self, endpoint: str, ssid: str, enable_val: str) -> None:
        """Execute the strict PUT url-encoded form handshake the router demands."""
        if not self.coordinator._logged_in:
            await self.coordinator._async_login()

        headers = self.coordinator._base_headers.copy()
        headers["Cookie"] = self.coordinator._active_cookie
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        url = f"{self.coordinator.base_url}/{endpoint}"
        payload = {"ssid": ssid, "enable": enable_val}

        async with self.coordinator.session.put(
            url, data=payload, headers=headers, skip_auto_headers={"Cookie"}
        ) as resp:
            if resp.status in (401, 403):
                self.coordinator._logged_in = False
                await self.coordinator._async_login()
                headers["Cookie"] = self.coordinator._active_cookie
                async with self.coordinator.session.put(
                    url, data=payload, headers=headers, skip_auto_headers={"Cookie"}
                ) as retry_resp:
                    retry_resp.raise_for_status()
            else:
                resp.raise_for_status()

    async def async_turn_on(self, **kwargs: Any) -> None:
        ssid_24, ssid_5 = self._get_guest_ssids()
        try:
            await self._async_trigger_put("wireless/guest24", ssid_24, "1")
            await self._async_trigger_put("wireless/guest5", ssid_5, "1")
            await self.coordinator.async_request_refresh()
        except ConfigEntryAuthFailed:
            if self.coordinator.config_entry:
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, UpdateFailed) as err:
            raise HomeAssistantError(f"Failed to enable Guest Wireless Access: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        ssid_24, ssid_5 = self._get_guest_ssids()
        try:
            await self._async_trigger_put("wireless/guest24", ssid_24, "0")
            await self._async_trigger_put("wireless/guest5", ssid_5, "0")
            await self.coordinator.async_request_refresh()
        except ConfigEntryAuthFailed:
            if self.coordinator.config_entry:
                self.coordinator.config_entry.async_start_reauth(self.hass)
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, UpdateFailed) as err:
            raise HomeAssistantError(f"Failed to disable Guest Wireless Access: {err}") from err
