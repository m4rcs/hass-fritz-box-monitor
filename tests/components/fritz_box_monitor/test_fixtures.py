"""Integrity checks for the canned FRITZ!Box fixtures.

These tests are green from the start; they pin the fixtures to the
constants in const.py so that typos surface here instead of as
confusing client test failures.
"""

import hashlib
import json
import xml.etree.ElementTree as ET

from .conftest import FIXTURES_DIR
from .const import (
    FAKE_BLOCK_TIME,
    FAKE_CHALLENGE,
    FAKE_LOGIN_RESPONSE,
    FAKE_MAC,
    FAKE_PASSWORD,
    FAKE_SID,
)


def _fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_challenge_fixture_matches_const() -> None:
    """The challenge served by the fake matches the documented constant."""
    root = ET.fromstring(_fixture("login_challenge.xml"))
    assert root.findtext("SID") == "0" * 16
    assert root.findtext("Challenge") == FAKE_CHALLENGE


def test_login_success_fixture_matches_const() -> None:
    """A successful login yields the SID the tests expect."""
    root = ET.fromstring(_fixture("login_success.xml"))
    assert root.findtext("SID") == FAKE_SID


def test_login_denied_fixture_keeps_zeroed_sid() -> None:
    """A rejected login leaves the SID zeroed."""
    root = ET.fromstring(_fixture("login_denied.xml"))
    assert root.findtext("SID") == "0" * 16


def test_blocked_challenge_fixture_reports_block_time() -> None:
    """A blocked challenge serves no challenge and a zeroed SID."""
    root = ET.fromstring(_fixture("login_challenge_blocked.xml"))
    assert root.findtext("SID") == "0" * 16
    assert root.findtext("Challenge") == ""
    assert int(root.findtext("BlockTime") or 0) == FAKE_BLOCK_TIME


def test_blocked_login_fixture_reports_block_time() -> None:
    """A blocked login keeps the SID zeroed and reports the block."""
    root = ET.fromstring(_fixture("login_blocked.xml"))
    assert root.findtext("SID") == "0" * 16
    assert int(root.findtext("BlockTime") or 0) == FAKE_BLOCK_TIME


def test_pbkdf2_response_matches_const() -> None:
    """The golden login response is the correct PBKDF2 answer.

    AVM v2 login: response = salt2$hash2 with
    hash2 = PBKDF2-HMAC-SHA256(PBKDF2-HMAC-SHA256(password, salt1, it1), salt2, it2).
    """
    _, it1, salt1, it2, salt2 = FAKE_CHALLENGE.split("$")
    hash1 = hashlib.pbkdf2_hmac(
        "sha256", FAKE_PASSWORD.encode(), bytes.fromhex(salt1), int(it1)
    )
    hash2 = hashlib.pbkdf2_hmac(
        "sha256", hash1, bytes.fromhex(salt2), int(it2)
    )
    assert f"{salt2}${hash2.hex()}" == FAKE_LOGIN_RESPONSE


def test_doc_info_fixture_contains_real_channels() -> None:
    """The captured docInfo page carries the channel lists as arrays."""
    doc = json.loads(_fixture("doc_info.json"))["data"]

    assert len(doc["channelDs"]["docsis30"]) == 24
    assert len(doc["channelDs"]["docsis31"]) == 2
    assert len(doc["channelUs"]["docsis30"]) == 4
    assert len(doc["channelUs"]["docsis31"]) == 1

    entry = doc["channelDs"]["docsis30"][0]
    assert isinstance(entry["powerLevel"], str)
    assert isinstance(entry["corrErrors"], int)
    assert "mse" in entry


def test_doc_ov_fixture_carries_identity_and_rates() -> None:
    """The captured docOv page carries identity, state and rates."""
    data = json.loads(_fixture("doc_ov.json"))["data"]["connectionData"]

    assert data["modell"] == "FRITZ!Box 6660 Cable"
    assert data["line"][0]["state"] == "ready"
    assert data["infoLeft"]["details"][1]["value"] == FAKE_MAC
    assert data["dsRate"] == "1126,4 Mbit/s"
    assert data["usRate"] == "52,5 Mbit/s"


def test_uimodlogic_fixture_carries_nspver() -> None:
    """The captured version endpoint carries the UI namespace version."""
    assert json.loads(_fixture("uimodlogic.json"))["nspver"] == "252.08.25"
