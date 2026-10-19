"""Config flow to set up the FRITZ!Box Monitor integration."""

import logging
from typing import Any, override

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import probatio

from .client import (
    FritzBoxMonitorAuthError,
    FritzBoxMonitorClient,
    FritzBoxMonitorConnectionError,
    FritzBoxMonitorLoginBlockedError,
)
from .const import DEFAULT_HOST, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Username is optional: boxes configured for password-only login are
# supported with an empty username.
STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST, default=DEFAULT_HOST): str,
        probatio.Optional(CONF_USERNAME, default=""): str,
        probatio.Required(CONF_PASSWORD): str,
    }
)


class FritzBoxMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FRITZ!Box Monitor."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: verify the modem answers, then store."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] | None = None

        if user_input is not None:
            client = FritzBoxMonitorClient(
                user_input[CONF_HOST],
                session=async_get_clientsession(self.hass),
                username=user_input.get(CONF_USERNAME, ""),
                password=user_input[CONF_PASSWORD],
            )

            # Test before configure: verify the modem answers and the
            # login works before the entry is created. Map the client
            # exceptions to the error keys of strings.json.
            try:
                status = await client.get_status()
            except FritzBoxMonitorLoginBlockedError as err:
                errors["base"] = "login_blocked"
                description_placeholders = {"block_time": str(err.block_time)}
            except FritzBoxMonitorAuthError:
                errors["base"] = "invalid_auth"
            except FritzBoxMonitorConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # The CM MAC address is the stable hardware identity; it
                # is the only hardware identifier the web UI exposes.
                await self.async_set_unique_id(status.mac)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=status.model, data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )
