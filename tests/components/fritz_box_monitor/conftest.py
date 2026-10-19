"""Fixtures that fake a FRITZ!Box for the FRITZ!Box Monitor tests.

The fake lives at the aiohttp layer: aioclient_mock replaces the shared
Home Assistant client session, so the real client code is exercised
against canned login_sid.lua and data.lua responses.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fritz_box_monitor.const import DOMAIN

from .const import FAKE_BASE_URL, FAKE_HOST, FAKE_PASSWORD, FAKE_USERNAME

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in all tests."""


@pytest.fixture
def load_fritz_fixture() -> Callable[[str], str]:
    """Load a canned FRITZ!Box response from the component fixtures."""

    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def mock_fritz_box(
    aioclient_mock: Any, load_fritz_fixture: Callable[[str], str]
) -> None:
    """Fake a healthy FRITZ!Box: v2 login flow plus the docInfo page."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/data.lua",
        text=load_fritz_fixture("doc_info.json"),
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry matching the data the config flow will store.

    The config flow does not collect credentials yet; the client already
    requires them, so entries in tests carry host, username and password.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title="FRITZ!Box Monitor",
        data={
            CONF_HOST: FAKE_HOST,
            CONF_USERNAME: FAKE_USERNAME,
            CONF_PASSWORD: FAKE_PASSWORD,
        },
    )
