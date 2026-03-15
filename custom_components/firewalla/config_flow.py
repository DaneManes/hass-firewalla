"""Config flow for Firewalla integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import BooleanSelector
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
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            
            # Create API client with the provided credentials
            api_client = FirewallaApiClient(
                session=session,
                api_token=user_input.get(CONF_API_TOKEN),
                subdomain=user_input.get(CONF_SUBDOMAIN),
            )

            try:
                # Test the API connection
                auth_success = await api_client.async_check_credentials()
                
                if auth_success:
                    # Use a combination of subdomain and token as the unique ID
                    await self.async_set_unique_id(f"{user_input[CONF_SUBDOMAIN]}_{user_input.get(CONF_API_TOKEN, '')}")
                    self._abort_if_unique_id_configured()
                    
                    return self.async_create_entry(
                        title=f"Firewalla ({user_input[CONF_SUBDOMAIN]})",
                        data=user_input,
                    )
                else:
                    errors["base"] = "auth"
            except Exception as ex:
                _LOGGER.error("Error during authentication: %s", ex)
                errors["base"] = "auth"

        # Set default values
        default_values = {
            CONF_SUBDOMAIN: DEFAULT_SUBDOMAIN,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        }
        
        # If we have user input, use those values as defaults
        if user_input is not None:
            for key in default_values:
                if key in user_input:
                    default_values[key] = user_input[key]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SUBDOMAIN, default=default_values[CONF_SUBDOMAIN]): str,
                    vol.Required(CONF_API_TOKEN): str,
                    vol.Required(CONF_SCAN_INTERVAL, default=default_values[CONF_SCAN_INTERVAL]): int,
                    # Adding the toggles:
                    vol.Optional(CONF_ENABLE_ALARMS, default=False): bool,
                    vol.Optional(CONF_ALARM_COUNT, default=False): int,
                    vol.Optional(CONF_ENABLE_RULES, default=False): bool,
                    vol.Optional(CONF_ENABLE_FLOWS, default=False): bool,
                    vol.Optional(CONF_FLOW_COUNT, default=False): int,
                    vol.Optional(CONF_ENABLE_TRAFFIC, default=False): bool,
                    vol.Optional(CONF_TRACK_DEVICES, default=False): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return FirewallaOptionsFlowHandler()

class FirewallaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Firewalla options."""

    async def async_step_init(self, user_input=None):
        """First step: Toggles."""
        if user_input is not None:
            # Store the toggles in a temporary variable
            self.data = user_input
            # If flows or alarms are enabled, go to the counts step
            if user_input.get(CONF_ENABLE_FLOWS) or user_input.get(CONF_ENABLE_ALARMS):
                return await self.async_step_counts()
            
            # Otherwise, just save
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
                vol.Optional(CONF_ENABLE_FLOWS, default=self.config_entry.options.get(CONF_ENABLE_FLOWS, False)): bool,
                vol.Optional(CONF_ENABLE_ALARMS, default=self.config_entry.options.get(CONF_ENABLE_ALARMS, False)): bool,
                vol.Optional(CONF_ENABLE_TRAFFIC, default=self.config_entry.options.get(CONF_ENABLE_TRAFFIC, False)): bool,
                vol.Optional(CONF_ENABLE_RULES, default=self.config_entry.options.get(CONF_ENABLE_RULES, False)): bool,
                vol.Optional(CONF_TRACK_DEVICES, default=self.config_entry.options.get(CONF_TRACK_DEVICES, False)): bool,
            }),
        )

    async def async_step_counts(self, user_input=None):
        """Second step: Conditionally show counts."""
        if user_input is not None:
            # Merge the counts with the toggles from the previous step
            self.data.update(user_input)
            return self.async_create_entry(title="", data=self.data)

        fields = {}
        
        # Only add flow count if flows were enabled in step 1
        if self.data.get(CONF_ENABLE_FLOWS):
            flow_default = self.config_entry.options.get(
                CONF_FLOW_COUNT, 
                self.config_entry.data.get(CONF_FLOW_COUNT, DEFAULT_FLOW_COUNT)
            )
            fields[vol.Optional(CONF_FLOW_COUNT, default=flow_default)] = cv.positive_int
        
        if self.data.get(CONF_ENABLE_FLOWS):
            total_flow_default = self.config_entry.options.get(
                CONF_TOTAL_FLOW_COUNT, 
                self.config_entry.data.get(CONF_TOTAL_FLOW_COUNT, DEFAULT_TOTAL_FLOW_COUNT)
            )
            fields[vol.Optional(CONF_TOTAL_FLOW_COUNT, default=total_flow_default)] = cv.positive_int
        
        # Only add alarm count if alarms were enabled in step 1
        if self.data.get(CONF_ENABLE_ALARMS):
            alarm_default = self.config_entry.options.get(
                CONF_ALARM_COUNT, 
                self.config_entry.data.get(CONF_ALARM_COUNT, DEFAULT_ALARM_COUNT)
            )
            fields[vol.Optional(CONF_ALARM_COUNT, default=alarm_default)] = cv.positive_int

        return self.async_show_form(
            step_id="counts",
            data_schema=vol.Schema(fields),
            description_placeholders={"message": "Configure limits for the enabled features."}
        )
