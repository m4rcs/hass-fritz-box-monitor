"""Shared constants for the FRITZ!Box Monitor tests.

The fake FRITZ!Box (see conftest.py) serves canned fixtures that match
these values, so expected request bodies are known constants.
"""

FAKE_HOST = "fritz.box"
FAKE_BASE_URL = f"http://{FAKE_HOST}"
FAKE_USERNAME = "test-user"
FAKE_PASSWORD = "test-password"

# SID of a logged-in session, as served by login_success.xml.
FAKE_SID = "88e33a10c8313b6f"

# Seconds the fake FRITZ!Box blocks login attempts in the blocked
# fixtures (login_challenge_blocked.xml, login_blocked.xml).
FAKE_BLOCK_TIME = 60

# A fixed v2 login challenge (version$iterations$salt1$iterations2$salt2),
# as served by login_challenge.xml.
FAKE_CHALLENGE = "2$60000$0a1b2c3d4e5f6a7b$1$7f6e5d4c3b2a1f0e"

# The PBKDF2-HMAC-SHA256 login response AVM expects for FAKE_CHALLENGE and
# FAKE_PASSWORD: "<salt2>$<pbkdf2(pbkdf2(password, salt1, iter1), salt2, iter2)>"
# (golden value computed once; see the AVM session id technical note).
FAKE_LOGIN_RESPONSE = (
    "7f6e5d4c3b2a1f0e"
    "$dba144127b07339497fbb105787cccbe65f9a177232fa6802cf19d04cd86107d"
)
