# FRITZ!Box Monitor for Home Assistant

[![Test](https://github.com/m4rcs/hass-fritz-box-monitor/actions/workflows/test.yml/badge.svg)](https://github.com/m4rcs/hass-fritz-box-monitor/actions/workflows/test.yml)
[![Validate](https://github.com/m4rcs/hass-fritz-box-monitor/actions/workflows/validate.yml/badge.svg)](https://github.com/m4rcs/hass-fritz-box-monitor/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://github.com/hacs/integration)

Monitors an AVM FRITZ!Box **cable** modem through its web UI and
exposes aggregate and per-channel DOCSIS line statistics as Home
Assistant sensors.

## Features

- Aggregate sensors: connection status, downstream/upstream channel
  counts, downstream/upstream power min/max, downstream SNR min/max,
  downstream correctable/uncorrectable error totals, downstream/
  upstream link rates
- Per-channel diagnostic sensors: power, SNR and error counters for
  every DOCSIS channel, with the complete AVM column set as attributes
  (modulation, frequency, MSE/MER, latency, PLC, FFT size, active
  subcarriers, multiplexing method)
- FRITZ!OS version reported as the device software version
- Config flow with test-before-save, reconfigure flow, automatic
  reauthentication when the password changes, and an options flow for
  the poll interval
- PBKDF2 (v2) login, session reuse with one automatic re-login, and
  graceful handling of temporary login blocks
- Future-proof parsing: channel fields the firmware adds that have no
  dedicated slot are exposed verbatim as attributes

## Requirements

- AVM FRITZ!Box **cable** modem (6590, 6591, 6660, 6690, ...).
  DSL boxes are not supported: the integration reads the cable
  information pages of the web UI.
- Home Assistant 2026.10 or newer.
- Login credentials: a user account with access to the cable
  information pages, or the device password for boxes configured for
  password-only login (leave the username empty).

## Installation

### HACS (recommended)

1. Add this repository to HACS as a custom repository
   (category: *integration*).
2. Install **FRITZ!Box Monitor**.
3. Restart Home Assistant. A reload is not enough - the integration
   only becomes active after a restart.

### Manual

Copy `custom_components/fritz_box_monitor/` into the
`custom_components/` directory of your Home Assistant configuration
and restart Home Assistant.

## Configuration

1. Go to *Settings -> Devices & Services* and click **Add Integration**.
2. Search for **FRITZ!Box Monitor**.
3. Enter the address of your modem (default: `fritz.box`), your
   username (leave empty for password-only login) and the password.

The integration verifies the credentials by fetching the modem status
before the entry is created. A wrong password shows *Incorrect
username or password*, an unreachable modem shows *Failed to connect*.
The cable modem MAC address is stored as the entry's unique id, so the
same box cannot be added twice.

### Options

The gear icon on the entry offers the **poll interval** in seconds
(default: 30, minimum: 10). Saving automatically reloads the entry.

### Reconfigure and reauthenticate

- The **reconfigure** flow (gear icon) changes host, username or
  password. The modem is verified first; if a different box answers,
  the flow aborts instead of silently re-pointing the entry.
- When the password changes on the box, polling fails and Home
  Assistant starts a **reauthentication** flow automatically - enter
  the new password once and the entry reloads.

## Entities

### Aggregate sensors

| Sensor | Description |
| ------ | ----------- |
| Verbindungsstatus / Connection status | Modem link state (e.g. `ready`) |
| Downstream/Upstream channels | Number of channels per direction |
| Downstream/Upstream power (min/max) | Power level extremes per direction |
| Downstream SNR (min/max) | Signal-to-noise ratio extremes |
| Downstream correctable errors | Sum of correctable errors |
| Downstream uncorrectable errors | Sum of uncorrectable errors |
| Downstream/Upstream rate | Current link rate in Mbit/s |

### Per-channel sensors

Every DOCSIS channel gets diagnostic sensors under the device's
diagnostic section. The channel power is the sensor state; SNR and the
error counters get their own sensors where the box reports them. The
full channel data is available as attributes.

Fields per DOCSIS version (as reported by the web UI):

| Field | DS 3.0 | DS 3.1 | US 3.0 | US 3.1 |
| ----- | ------ | ------ | ------ | ------ |
| Power level (dBmV, state) | x | x | x | x |
| Modulation | x | x | x | x |
| Frequency (MHz) | x | x | x | x |
| SNR / MER (dB, sensor + attribute) | x | x | | |
| MSE (dB) | x | | | |
| Latency (ms) | x | | | |
| Correctable errors (sensor + attribute) | x | | | |
| Uncorrectable errors (sensor + attribute) | x | x | | |
| PLC (MHz) | | x | | |
| FFT size | | x | | x |
| Active subcarriers | | | | x |
| Multiplexing | | | x | |

## Troubleshooting

- **Sensors are unknown after an update**: restart Home Assistant
  completely. Removing and re-adding the integration (or reloading it)
  does not reload the Python code.
- **Incorrect username or password after changing it on the box**:
  open the entry and follow the reauthenticate prompt.
- **Failed to connect**: check the address; note that the integration
  always talks HTTPS and ignores the self-signed certificate.
- **Login temporarily blocked**: too many failed attempts make the box
  refuse logins for a while. The integration keeps retrying in the
  background - no action needed.
- **Modem is connecting**: while the cable registration runs, the
  connection status is unknown and some channels may be missing.

## How it works

The integration talks to the same endpoints as the web UI: the PBKDF2
challenge-response login (`login_sid.lua?version=2`) and the JSON data
endpoints (`data.lua` pages `docOv` and `docInfo`), plus
`/api/v0/generic/uimodlogic` for the FRITZ!OS version. All requests run
over HTTPS with certificate verification disabled, since the box uses a
self-signed certificate.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

The test suite runs against a faked FRITZ!Box web UI built from real,
sanitized captures. `wheels/` contains prebuilt wheels for the two
test dependencies (`mock-open`, `pyric`) that publish no wheels of
their own. CI (`.github/workflows/`) runs the tests and linters on
every push and pull request.

## License

[MIT](LICENSE)
