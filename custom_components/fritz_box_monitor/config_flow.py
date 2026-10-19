"""Config flow to set up the FRITZ!Box Monitor integration."""

import logging
from typing import Any, override

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import probatio

from .client import FritzBoxMonitorClient, FritzBoxMonitorError
from .const import DEFAULT_HOST, DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)

# TODO: extend the schema once it is clear what the client needs
# (credentials for the web UI login, polling interval, ...).
STEP_USER_DATA_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_HOST, default=DEFAULT_HOST): str}
)


class FritzBoxMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FRITZ!Box Monitor."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: ask for the modem address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client = FritzBoxMonitorClient(
                user_input[CONF_HOST],
                session=async_get_clientsession(self.hass),
            )

            # Test before configure: verify the modem answers before the
            # entry is created. Map the client exceptions to the error
            # keys of strings.json.
            try:
                # TODO: the status will be needed below for the unique id.
                await client.get_status()
            except FritzBoxMonitorError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # TODO: use a stable hardware identifier (serial number)
                # as the unique id and abort when this modem is already
                # set up (unique-config-entry rule). Never use the IP
                # address: it can change.
                # await self.async_set_unique_id(status.serial_number)
                # self._abort_if_unique_id_configured()

                return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
