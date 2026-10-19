# FRITZ!Box Monitor

A [Home Assistant](https://www.home-assistant.io) integration that
monitors an AVM FRITZ!Box cable modem. It reports the connection state
and cable (DOCSIS) line statistics as sensors, for example:

- Downstream / upstream signal-to-noise ratio
- Downstream / upstream power levels
- Correctable / uncorrectable errors
- Connection status

> This project is a skeleton / work in progress. The modem client is
> not implemented yet; see the TODOs in
> `custom_components/fritz_box_monitor/client.py`.

## Installation

### Via HACS (custom repository)

This integration is not (yet) in the default HACS catalog, so add it as
a custom repository:

1. Make sure [HACS](https://hacs.xyz) is installed.
2. In HACS, open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/m4rcs/hass-fritz-box-monitor`
   with the category **Integration**.
4. Install **FRITZ!Box Monitor** and restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings > Devices & services**.
2. Click **Add integration** and search for **FRITZ!Box Monitor**.
3. Enter the address of your FRITZ!Box (default: `fritz.box`).

<!-- TODO: document any modem preparation steps (for example enabling
TR-064 access or a local user account) and credentials once the client
is implemented. -->

## Removing the integration

Remove it under **Settings > Devices & services**. No extra steps are
required.

## Development

The integration follows the layout of the official
[Home Assistant integration tutorial](https://contributors.home-assistant.io/core/integrations/tutorial/),
adapted for a custom (HACS-distributed) integration:

```
custom_components/fritz_box_monitor/
|-- __init__.py      # config entry setup, platform forwarding
|-- client.py        # modem API client (stub, see TODOs)
|-- config_flow.py   # UI setup flow
|-- const.py
|-- coordinator.py   # polling DataUpdateCoordinator
|-- entity.py        # shared base entity
|-- manifest.json
|-- sensor.py        # sensor platform
|-- strings.json     # translation source
`-- translations/
    |-- de.json      # German translation
    `-- en.json      # must be committed for custom integrations
```

Validation runs on every push via GitHub Actions: hassfest and
[HACS validation](https://github.com/hacs/action). Lint and type check
locally with ruff and mypy (see `pyproject.toml`).

## License

[MIT](LICENSE)
