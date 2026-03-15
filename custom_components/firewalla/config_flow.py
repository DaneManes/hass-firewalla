"""Config flow for Firewalla integration."""
import logging
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_SCAN_INTERVAL

from .api import FirewallaApiClient
from .const import (
    DOMAIN, 
    CONF_API_TOKEN, 
    CONF_SUBDOMAIN, 
    DEFAULT_SUBDOMAIN,
    DEFAULT_SCAN_INTERVAL,
    CONF_ENABLE_ALARMS,
    DEFAULT_ALARM_COUNT,
    CONF_ALARM_COUNT,
    CONF_ENABLE_RULES,
    CONF_ENABLE_FLOWS,
    DEFAULT_FLOW_COUNT,
    CONF_FLOW_COUNT,
    CONF_ENABLE_TRAFFIC,
    CONF_TRACK_DEVICES,
    CONF_TOTAL_FLOW_COUNT,
    DEFAULT_TOTAL_FLOW_COUNT,
)

_LOGGER = logging.getLogger(__name__)

class FirewallaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Firewalla."""

    VERSION = 1

    # Class attribute to persist data across steps without using __init__
    _init_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial setup step."""
        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            
            api_client = FirewallaApiClient(
                session=session,
                api_token=user_input.get(CONF_API_TOKEN),
                subdomain=user_input.get(CONF_SUBDOMAIN),
            )

            try:
                auth_success = await api_client.async_check_credentials()
                
                if auth_success:
                    # Store data for the next step
                    self._init_data = user_input
                    
                    # Branch to Step 2 if "Heavy" features are enabled
                    if user_input.get(CONF_ENABLE_ALARMS) or user_input.get(CONF_ENABLE_FLOWS):
                        return await self.async_step_counts()
                    
                    # Direct finish if no counts are needed
                    return await self._async_create_firewalla_entry()
                
                errors["base"] = "auth"
            except Exception as ex:
                _LOGGER.error("Error during authentication: %s", ex)
                errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBDOMAIN, default=DEFAULT_SUBDOMAIN): str,
                    vol.Required(CONF_API_TOKEN): str,
                    vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                    vol.Optional(CONF_ENABLE_ALARMS, default=False): bool,
                    vol.Optional(CONF_ENABLE_RULES, default=False): bool,
                    vol.Optional(CONF_ENABLE_FLOWS, default=False): bool,
                    vol.Optional(CONF_ENABLE_TRAFFIC, default=False): bool,
                    vol.Optional(CONF_TRACK_DEVICES, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_counts(self, user_input: dict[str, Any] | None = None):
        """Step 2: Force limits to prevent 16k attribute crash."""
        if user_input is not None:
            self._init_data.update(user_input)
            return await self._async_create_firewalla_entry()

        fields = {}
        # Only show fields that were enabled in Step 1
        if self._init_data.get(CONF_ENABLE_FLOWS):
            fields[vol.Optional(CONF_FLOW_COUNT, default=DEFAULT_FLOW_COUNT)] = cv.positive_int
            fields[vol.Optional(CONF_TOTAL_FLOW_COUNT, default=DEFAULT_TOTAL_FLOW_COUNT)] = cv.positive_int
        
        if self._init_data.get(CONF_ENABLE_ALARMS):
            fields[vol.Optional(CONF_ALARM_COUNT, default=DEFAULT_ALARM_COUNT)] = cv.positive_int

        return self.async_show_form(
            step_id="counts",
            data_schema=vol.Schema(fields)
        )

    async def _async_create_firewalla_entry(self):
        """Finalize the config entry."""
        unique_id = f"{self._init_data[CONF_SUBDOMAIN]}_{self._init_data.get(CONF_API_TOKEN, '')}"
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        
        return self.async_create_entry(
            title=f"Firewalla ({self._init_data[CONF_SUBDOMAIN]})",
            data=self._init_data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return FirewallaOptionsFlowHandler(config_entry)


class FirewallaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options via the config wheel."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize with private attribute to avoid read-only conflicts."""
        self._config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Options Step 1: Toggles."""
        if user_input is not None:
            self.options.update(user_input)
            
            if user_input.get(CONF_ENABLE_FLOWS) or user_input.get(CONF_ENABLE_ALARMS):
                return await self.async_step_counts()
            
            return self.async_create_entry(title="", data=self.options)
            
        def get_val(key, default=False):
            # Fallback chain: Current Options -> Original Install Data -> Global Default
            return self._config_entry.options.get(key, self._config_entry.data.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=get_val(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
                vol.Optional(CONF_ENABLE_FLOWS, default=get_val(CONF_ENABLE_FLOWS)): bool,
                vol.Optional(CONF_ENABLE_ALARMS, default=get_val(CONF_ENABLE_ALARMS)): bool,
                vol.Optional(CONF_ENABLE_TRAFFIC, default=get_val(CONF_ENABLE_TRAFFIC)): bool,
                vol.Optional(CONF_ENABLE_RULES, default=get_val(CONF_ENABLE_RULES)): bool,
                vol.Optional(CONF_TRACK_DEVICES, default=get_val(CONF_TRACK_DEVICES)): bool,
            }),
        )

    async def async_step_counts(self, user_input: dict[str, Any] | None = None):
        """Options Step 2: Limits."""
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)

        fields = {}
        def get_count_val(key, default):
            return self._config_entry.options.get(key, self._config_entry.data.get(key, default))
        
        if self.options.get(CONF_ENABLE_FLOWS):
            fields[vol.Optional(CONF_FLOW_COUNT, default=get_count_val(CONF_FLOW_COUNT, DEFAULT_FLOW_COUNT))] = cv.positive_int
            fields[vol.Optional(CONF_TOTAL_FLOW_COUNT, default=get_count_val(CONF_TOTAL_FLOW_COUNT, DEFAULT_TOTAL_FLOW_COUNT))] = cv.positive_int
        
        if self.options.get(CONF_ENABLE_ALARMS):
            fields[vol.Optional(CONF_ALARM_COUNT, default=get_count_val(CONF_ALARM_COUNT, DEFAULT_ALARM_COUNT))] = cv.positive_int

        return self.async_show_form(step_id="counts", data_schema=vol.Schema(fields))