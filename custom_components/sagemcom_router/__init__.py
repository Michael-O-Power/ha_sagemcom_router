import asyncio
import logging
import random
from datetime import timedelta

import aiohttp
from yarl import URL

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, PLATFORMS
from .crypto import calculate_auth_key

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Sagemcom Router component (Legacy Hook)."""
    return True

class SagemcomDataCoordinator(DataUpdateCoordinator):
    """Class to manage continuous authentication and data fetching."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, host, username, password):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"Sagemcom {host}",
            update_interval=timedelta(seconds=60),
        )
        self.host = host
        self.username = username
        self.password = password
        self.base_url = f"http://{host}/api/v1"
        self.session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(unsafe=True))
        
        self._logged_in = False
        self._active_cookie = ""
        self._base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": f"http://{self.host}",
            "Referer": f"http://{self.host}/",
            "Connection": "keep-alive"
        }
        
        self.endpoints = {
            "device": f"{self.base_url}/device",
            "network_type": f"{self.base_url}/cellular/network_type",
            "sim_status": f"{self.base_url}/cellular/interface/usim/status_extended",
            "provider": f"{self.base_url}/cellular/provider",
            "session": f"{self.base_url}/cellular/session",
            "wan": f"{self.base_url}/wan/status",
            "interface_5g": f"{self.base_url}/cellular/interface_5g",
            "interface_4g": f"{self.base_url}/cellular/interface",
            "lan_stats": f"{self.base_url}/lan/stats",
            "hosts": f"{self.base_url}/hosts",
            "wifi_24": f"{self.base_url}/wireless/24",
            "wifi_5": f"{self.base_url}/wireless/5",
            "wifi_guest24": f"{self.base_url}/wireless/guest24",
            "wifi_guest5": f"{self.base_url}/wireless/guest5"
        }

    async def _async_login(self):
        """Perform the Javascript login handshake to get fresh cookies."""
        try:
            async with asyncio.timeout(10):
                async with self.session.get(f"http://{self.host}/", headers=self._base_headers):
                    pass
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"Connection error connecting to router: {err}") from err

        jar_init = {k: m.value for k, m in self.session.cookie_jar.filter_cookies(URL(f"http://{self.host}/")).items()}
        init_salt = jar_init.get("salt", "7UHqMkAHM8PNvh/O")
        init_nonce = jar_init.get("nonce", str(random.randint(1000000000, 9999999999)))

        params_url = f"{self.base_url}/login-params"
        headers_params = self._base_headers.copy()
        c_params = ["modeSelected=admin", f"salt={init_salt}", "backgroundColor=restgui-tpg-theme", "currentLanguage=EN", f"nonce={init_nonce}"]
        headers_params["Cookie"] = "; ".join(c_params)

        salt, nonce, bbox_id = None, None, None
        try:
            async with asyncio.timeout(5):
                async with self.session.post(params_url, data={"login": self.username}, headers=headers_params, skip_auto_headers={"Cookie"}) as resp:
                    if resp.status in (401, 403):
                        self._logged_in = False
                        raise ConfigEntryAuthFailed(
                            f"Router rejected login parameters: {resp.status}"
                        )
                    resp.raise_for_status()
                    if "salt" in resp.cookies: salt = resp.cookies["salt"].value
                    if "nonce" in resp.cookies: nonce = resp.cookies["nonce"].value
                    if "BBOX_ID" in resp.cookies: bbox_id = resp.cookies["BBOX_ID"].value
        except ConfigEntryAuthFailed:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"Connection error during parameter retrieval: {err}") from err

        jar_cookies = {k: m.value for k, m in self.session.cookie_jar.filter_cookies(URL(f"http://{self.host}/")).items()}
        if not salt: salt = jar_cookies.get("salt")
        if not nonce: nonce = jar_cookies.get("nonce")
        if not bbox_id: bbox_id = jar_cookies.get("BBOX_ID")

        if not salt or not nonce:
            raise UpdateFailed("Failed to retrieve salt/nonce during initialization")

        cnonce = f"{random.randint(1000000000000000, 9999999999999999)}000"
        auth_key = await self.hass.async_add_executor_job(
            calculate_auth_key, self.username, self.password, salt, nonce, cnonce
        )

        login_url = f"{self.base_url}/login"
        payload_dict = {"login": self.username, "auth_key": auth_key, "cnonce": cnonce}
        cookie_parts = ["modeSelected=admin", f"salt={salt}", "backgroundColor=restgui-tpg-theme", "currentLanguage=EN", f"nonce={nonce}"]
        if bbox_id: cookie_parts.append(f"BBOX_ID={bbox_id}")

        headers_login = self._base_headers.copy()
        headers_login["Cookie"] = "; ".join(cookie_parts)

        try:
            async with asyncio.timeout(10):
                async with self.session.post(login_url, data=payload_dict, headers=headers_login, skip_auto_headers={"Cookie"}) as login_resp:
                    if 400 <= login_resp.status < 500:
                        self._logged_in = False
                        raise ConfigEntryAuthFailed(
                            f"Router rejected authentication: {login_resp.status}"
                        )
                    if login_resp.status not in (200, 201):
                        self._logged_in = False
                        raise UpdateFailed(
                            f"Unexpected HTTP status during login: {login_resp.status}"
                        )

                    if "BBOX_ID" in login_resp.cookies:
                        final_bbox = login_resp.cookies["BBOX_ID"].value
                        cookie_parts = [c for c in cookie_parts if not c.startswith("BBOX_ID=")]
                        cookie_parts.append(f"BBOX_ID={final_bbox}")

                    self._active_cookie = "; ".join(cookie_parts)
                    self._logged_in = True
        except ConfigEntryAuthFailed:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            raise UpdateFailed(f"Connection error during login: {err}") from err

    async def async_post_command(self, url_path: str, payload: dict):
        """Execute a state modification action against the router API."""
        if not self._logged_in:
            await self._async_login()

        headers = self._base_headers.copy()
        headers["Cookie"] = self._active_cookie
        full_url = f"{self.base_url}/{url_path.lstrip('/')}"

        async with self.session.post(full_url, json=payload, headers=headers, skip_auto_headers={"Cookie"}) as resp:
            if resp.status in (401, 403):
                self._logged_in = False
                await self._async_login()
                headers["Cookie"] = self._active_cookie
                async with self.session.post(full_url, json=payload, headers=headers, skip_auto_headers={"Cookie"}) as retry_resp:
                    retry_resp.raise_for_status()
            else:
                resp.raise_for_status()

    async def _async_update_data(self):
        """Fetch data from API endpoints."""
        if not self._logged_in:
            await self._async_login()

        try:
            results = {}
            for key, url in self.endpoints.items():
                headers = self._base_headers.copy()
                headers["Cookie"] = self._active_cookie

                async with self.session.get(url, headers=headers, skip_auto_headers={"Cookie"}) as response:
                    if response.status in (401, 403):
                        self._logged_in = False
                        await self._async_login()
                        headers["Cookie"] = self._active_cookie
                        async with self.session.get(url, headers=headers, skip_auto_headers={"Cookie"}) as retry_resp:
                            if retry_resp.status in (401, 403):
                                self._logged_in = False
                                raise ConfigEntryAuthFailed(
                                    f"Authentication rejected after re-login: {retry_resp.status}"
                                )
                            retry_resp.raise_for_status()
                            text = await retry_resp.text()
                            results[key] = await retry_resp.json() if text else {}
                    else:
                        response.raise_for_status()
                        text = await response.text()
                        results[key] = await response.json() if text else {}

            return results

        except ConfigEntryAuthFailed:
            self._logged_in = False
            raise
        except UpdateFailed:
            raise
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise UpdateFailed(f"API Error: {err}") from err

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sagemcom Router from a config entry."""
    host = entry.data.get("host")
    username = entry.data.get("username")
    password = entry.data.get("password")

    coordinator = SagemcomDataCoordinator(hass, entry, host, username, password)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "host": host,
    }

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ADD THIS: Listen for option changes and reload
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if PLATFORMS:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    else:
        unload_ok = True
        
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)