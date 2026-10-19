"""Constants for the FRITZ!Box Monitor integration."""

from datetime import timedelta

DOMAIN = "fritz_box_monitor"
NAME = "FRITZ!Box Monitor"

# Default address of the cable modem. "fritz.box" is the factory default
# hostname of AVM devices.
DEFAULT_HOST = "fritz.box"

# Interval at which the coordinator polls the cable modem.
# TODO: revisit once it is clear how often the modem refreshes its
# DOCSIS counters, and whether the interval should be user configurable.
UPDATE_INTERVAL = timedelta(seconds=30)
