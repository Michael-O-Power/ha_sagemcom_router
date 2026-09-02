import asyncio
import logging
import random
import voluptuous as vol
import aiohttp
from yarl import URL
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN
from .crypto import calculate_auth_key

_LOGGER = logging.getLogger(__name__)

class SagemcomConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a UI setup config flow for the Sagemcom 5G Router."""
    VERSION = 1
    
    def __init__(self):
        # Keep minimal runtime info for logging only; do NOT capture sensitive values.
        self.debug_info = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step when a user adds the integration."""
        errors = {}
        dump_text = ""

        if user_input is not None:
            host = user_input.get("host", "192.168.1.1").strip()
            username = user_input.get("username", "admin").strip()
            password = user_input.get("password", "").strip()

            try:
                base_url = URL(f"http://{host}/")
                cookie_jar = aiohttp.CookieJar(unsafe=True)
                
                async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
                    base_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "en-AU,en-US;q=0.9,en-GB;q=0.8,en;q=0.7",
                        "Origin": f"http://{host}",
                        "Referer": f"http://{host}/",
                        "Connection": "keep-alive"
                    }

                    # Step 1: Initialize baseline session
                    await session.get(base_url, headers=base_headers)
                    
                    jar_init = {k: m.value for k, m in session.cookie_jar.filter_cookies(base_url).items()}
                    init_salt = jar_init.get("salt", "7UHqMkAHM8PNvh/O") 
                    init_nonce = jar_init.get("nonce", str(random.randint(1000000000, 9999999999)))

                    # Step 2: POST to login-params
                    params_url = f"http://{host}/api/v1/login-params"
                    headers_params = base_headers.copy()
                    
                    c_params = ["modeSelected=admin", f"salt={init_salt}", "backgroundColor=restgui-tpg-theme", "currentLanguage=EN", f"nonce={init_nonce}"]
                    headers_params["Cookie"] = "; ".join(c_params)

                    salt = None
                    nonce = None
                    bbox_id = None

                    # Do NOT store request headers (may contain sensitive tokens)
                    self.debug_info["params_req_sent"] = True

                    async with asyncio.timeout(5):
                        async with session.post(
                            params_url, 
                            data={"login": username}, 
                            headers=headers_params,
                            skip_auto_headers={"Cookie"}
                        ) as resp:
                            # Only record non-sensitive status for diagnostics
                            self.debug_info["params_resp_status"] = str(resp.status)
                            
                            if "salt" in resp.cookies:
                                salt = resp.cookies["salt"].value
                            if "nonce" in resp.cookies:
                                nonce = resp.cookies["nonce"].value
                            if "BBOX_ID" in resp.cookies:
                                bbox_id = resp.cookies["BBOX_ID"].value

                    jar_cookies = {k: m.value for k, m in session.cookie_jar.filter_cookies(base_url).items()}
                    if not salt: salt = jar_cookies.get("salt")
                    if not nonce: nonce = jar_cookies.get("nonce")
                    if not bbox_id: bbox_id = jar_cookies.get("BBOX_ID")

                    if not salt or not nonce:
                        # Don't include cookie contents in error; log only minimal info
                        self.debug_info["error"] = "missing_tokens"
                        _LOGGER.debug("Missing tokens during setup. Available cookie names: %s", list(jar_cookies.keys()))
                        errors["base"] = "cannot_connect"
                    else:
                        # Step 3: Cryptographic Signature Generation
                        cnonce = f"{random.randint(1000000000000000, 9999999999999999)}000"
                        auth_key = calculate_auth_key(username, password, salt, nonce, cnonce)

                        # Step 4: Final Authenticated Challenge Setup
                        login_url = f"http://{host}/api/v1/login"
                        
                        payload_dict = {
                            "login": username,
                            "auth_key": auth_key,
                            "cnonce": cnonce
                        }
                        
                        cookie_parts = [
                            "modeSelected=admin",
                            f"salt={salt}",
                            "backgroundColor=restgui-tpg-theme",
                            "currentLanguage=EN",
                            f"nonce={nonce}"
                        ]
                        if bbox_id:
                            cookie_parts.append(f"BBOX_ID={bbox_id}")
                        
                        headers_login = base_headers.copy()
                        headers_login["Cookie"] = "; ".join(cookie_parts)

                        # Do NOT store payloads or headers containing sensitive tokens
                        self.debug_info["login_req_sent"] = True

                        async with session.post(
                            login_url, 
                            data=payload_dict, 
                            headers=headers_login, 
                            skip_auto_headers={"Cookie"}
                        ) as login_resp:
                            # Only capture non-sensitive status code
                            self.debug_info["login_resp_status"] = str(login_resp.status)

                            if login_resp.status in [200, 201]:
                                _LOGGER.info("Successfully authenticated with Sagemcom Router!")
                                return self.async_create_entry(
                                    title=f"Sagemcom F@st 5866T ({host})", data=user_input
                                )
                            else:
                                _LOGGER.error("Auth rejected. Status: %s.", login_resp.status)
                                errors["base"] = "invalid_auth"

            except Exception as err:
                # Keep only a short marker in debug_info; log exception for developers
                self.debug_info["error"] = "exception_occurred"
                _LOGGER.debug("Exception during Sagemcom setup: %s", err)
                errors["base"] = "cannot_connect"

            # Render minimal, non-sensitive output back to the UI window on failure
            dump_text = (
                f"--- LOGIN PARAMS RESPONSE ---\n"
                f"Status: {self.debug_info.get('params_resp_status', '')}\n\n"
                f"--- LOGIN RESPONSE ---\n"
                f"Status: {self.debug_info.get('login_resp_status', '')}\n\n"
                f"--- EXCEPTIONS ---\n"
                f"{self.debug_info.get('error', 'None')}"
            )

        schema_dict = {
            vol.Required("host", default=user_input.get("host", "192.168.1.1") if user_input else "192.168.1.1"): str,
            vol.Required("username", default=user_input.get("username", "admin") if user_input else "admin"): str,
            vol.Required("password", default=user_input.get("password", "") if user_input else ""): str,
        }

        if dump_text:
            # Expose only the minimal non-sensitive status dump
            schema_dict[vol.Optional("debug_output", default=dump_text)] = selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
