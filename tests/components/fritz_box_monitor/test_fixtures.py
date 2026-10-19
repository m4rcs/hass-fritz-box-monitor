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
    FAKE_CHALLENGE,
    FAKE_LOGIN_RESPONSE,
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


def test_doc_info_fixture_contains_channels() -> None:
    """The fake docInfo page carries the channels the client parses."""
    doc = json.loads(_fixture("doc_info.json"))["data"]
    assert set(doc["channelDs"]) == {"docsis30", "docsis31"}
    assert set(doc["channelUs"]) == {"docsis30", "docsis31"}
    assert len(doc["channelDs"]["docsis30"]) == 2
    assert len(doc["channelDs"]["docsis31"]) == 1
    assert len(doc["channelUs"]["docsis30"]) == 2
    assert len(doc["channelUs"]["docsis31"]) == 1
