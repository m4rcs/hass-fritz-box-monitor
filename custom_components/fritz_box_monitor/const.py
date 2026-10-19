"""Constants for the FRITZ!Box Monitor integration."""

DOMAIN = "fritz_box_monitor"
NAME = "FRITZ!Box Monitor"

# Default address of the cable modem. "fritz.box" is the factory default
# hostname of AVM devices.
DEFAULT_HOST = "fritz.box"

# Key of the user-configurable poll interval (in seconds) in the config
# entry options.
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL_SECONDS = 30
MIN_UPDATE_INTERVAL_SECONDS = 10
