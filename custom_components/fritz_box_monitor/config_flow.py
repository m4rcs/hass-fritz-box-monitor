"""Config flow to set up the FRITZ!Box Monitor integration."""

import logging
from typing import Any, override

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import probatio

from .client import (
    CableModemStatus,
    FritzBoxMonitorAuthError,
    FritzBoxMonitorClient,
    FritzBoxMonitorConnectionError,
    FritzBoxMonitorLoginBlockedError,
)
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    MIN_UPDATE_INTERVAL_SECONDS,
)
from .coordinator import FritzBoxMonitorConfigEntry

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

    @staticmethod
    @override
    def async_get_options_flow(
        config_entry: FritzBoxMonitorConfigEntry,
    ) -> FritzBoxMonitorOptionsFlowHandler:
        """Create the options flow handler."""
        return FritzBoxMonitorOptionsFlowHandler(config_entry)

    async def _async_check_credentials(
        self, user_input: dict[str, Any]
    ) -> tuple[CableModemStatus | None, str | None, dict[str, str] | None]:
        """Test the modem with the given input.

        Return the parsed status on success, or an error key plus
        description placeholders for the form.
        """
        client = FritzBoxMonitorClient(
            user_input[CONF_HOST],
            session=async_get_clientsession(self.hass),
            username=user_input.get(CONF_USERNAME, ""),
            password=user_input[CONF_PASSWORD],
        )

        # Test before save: verify the modem answers and the login works
        # before data is stored. Map the client exceptions to the error
        # keys of strings.json.
        try:
            return await client.get_status(), None, None
        except FritzBoxMonitorLoginBlockedError as err:
            return None, "login_blocked", {"block_time": str(err.block_time)}
        except FritzBoxMonitorAuthError:
            return None, "invalid_auth", None
        except FritzBoxMonitorConnectionError:
            return None, "cannot_connect", None
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return None, "unknown", None

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: verify the modem answers, then store."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] | None = None

        if user_input is not None:
            status, error, placeholders = await self._async_check_credentials(
                user_input
            )
            if error is None and status is not None:
                # The CM MAC address is the stable hardware identity; it
                # is the only hardware identifier the web UI exposes.
                await self.async_set_unique_id(status.mac)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=status.model, data=user_input
                )
            errors = {"base": error} if error else {}
            description_placeholders = placeholders

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reconfigure step: verify, then update the entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] | None = None

        data = entry.data
        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_HOST, default=data.get(CONF_HOST, DEFAULT_HOST)
                ): str,
                probatio.Optional(
                    CONF_USERNAME, default=data.get(CONF_USERNAME, "")
                ): str,
                probatio.Required(CONF_PASSWORD): str,
            }
        )

        if user_input is not None:
            status, error, placeholders = await self._async_check_credentials(
                user_input
            )
            if error is None and status is not None:
                # Re-pointing the entry to a different box would silently
                # change its identity; refuse instead.
                await self.async_set_unique_id(status.mac)
                self._abort_if_unique_id_mismatch()

                return self.async_update_reload_and_abort(
                    entry, data=user_input
                )
            errors = {"base": error} if error else {}
            description_placeholders = placeholders

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )


    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start the reauthentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the reauthentication with the new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] | None = None

        if user_input is not None:
            # Only the password is asked for; host and username come from
            # the stored entry data.
            check_input = {**entry.data, **user_input}
            status, error, placeholders = await self._async_check_credentials(
                check_input
            )
            if error is None and status is not None:
                await self.async_set_unique_id(status.mac)
                # Legacy entries may not carry a unique id yet; only a
                # real mismatch with a DIFFERENT box aborts.
                if entry.unique_id is not None:
                    self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data=check_input, unique_id=status.mac
                )
            errors = {"base": error} if error else {}
            description_placeholders = placeholders

        schema = probatio.Schema({probatio.Required(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )


class FritzBoxMonitorOptionsFlowHandler(
    OptionsFlowWithReload, OptionsFlowWithConfigEntry
):
    """Handle options for FRITZ!Box Monitor.

    Finishing the flow with changed options reloads the entry, so a new
    poll interval takes effect immediately.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval option."""
        errors: dict[str, str] = {}

        if user_input is not None:
            seconds = int(user_input[CONF_UPDATE_INTERVAL])
            if seconds < MIN_UPDATE_INTERVAL_SECONDS:
                errors["base"] = "interval_too_low"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
        )
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_UPDATE_INTERVAL, default=current): int,
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
