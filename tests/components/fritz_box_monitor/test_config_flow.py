"""Tests for the FRITZ!Box Monitor config flow.

The flow talks to the faked FRITZ!Box (see conftest.py); these tests
pin the schema, the error mapping and the serial-number unique id.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fritz_box_monitor.const import DOMAIN

from .const import (
    FAKE_BASE_URL,
    FAKE_HOST,
    FAKE_MAC,
    FAKE_PASSWORD,
    FAKE_USERNAME,
)


def _user_input() -> dict[str, str]:
    """Return the data a user submits in the flow."""
    return {
        CONF_HOST: FAKE_HOST,
        CONF_USERNAME: FAKE_USERNAME,
        CONF_PASSWORD: FAKE_PASSWORD,
    }


async def _start_flow(hass: HomeAssistant) -> Any:
    """Start the config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _submit(hass: HomeAssistant, user_input: dict[str, str]) -> Any:
    """Start the flow and submit the given user data."""
    result = await _start_flow(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )


async def test_form_shown(hass: HomeAssistant) -> None:
    """The user step asks for host, username and password."""
    result = await _start_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_setup_creates_entry(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """A successful flow stores the credentials and the serial number."""
    result = await _start_flow(hass)

    with patch(
        "custom_components.fritz_box_monitor.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _user_input()
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "FRITZ!Box 6660 Cable"
    assert result["data"] == _user_input()

    entry = hass.config_entries.async_entries()[0]
    assert entry.unique_id == FAKE_MAC


async def test_duplicate_serial_aborts(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """A modem that is already set up aborts the flow."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=FAKE_MAC)
    entry.add_to_hass(hass)

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_connection_error_shows_cannot_connect(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Connection problems during the flow map to cannot_connect."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2", exc=TimeoutError()
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_auth_failure_shows_invalid_auth(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A rejected login maps to invalid_auth."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_denied.xml"),
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_blocked_shows_login_blocked_with_time(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A blocked login maps to login_blocked with the remaining time."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge_blocked.xml"),
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "login_blocked"}
    assert result["description_placeholders"] == {"block_time": "60"}


async def test_unexpected_error_shows_unknown(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """Errors outside the client contract map to unknown."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    aioclient_mock.post(f"{FAKE_BASE_URL}/data.lua", text="<not json>")

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}
