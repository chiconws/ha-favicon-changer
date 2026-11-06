# Favicon Changer

[![Marketplace][badge-marketplace]][link-marketplace]
[![GitHub Release][badge-release]][link-release]
[![Home Assistant][badge-ha]][link-ha]
[![GitHub Commit Activity][badge-commit-activity]][link-commits]
[![HACS Validation][badge-hacs-validation]][link-hacs-validation]
[![Hassfest][badge-hassfest]][link-hassfest]
[![Tests][badge-tests]][link-tests]
[![License][badge-license]][link-license]

Change the browser title, favicon and web app icons of your Home Assistant, from built-in presets or your own icon.

![Favicon Changer](docs/images/favicon-panel.png)

## Features

- Custom page title for every Home Assistant tab
- Browser favicon, Apple touch icon and web app (PWA) icons replaced together
- Built-in presets, discovered from the `presets/` folder
- Sidebar panel to preview and apply presets or upload one custom icon

## Requirements

- Home Assistant 2024.7 or newer
- An admin user (the panel and its upload endpoint are admin-only)

## Installation

### Marketplace (recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace.][badge-my-marketplace]][link-my-marketplace]

1. Click the button above. If Home Assistant asks, confirm adding the repository.
2. Download **Favicon Changer** in **Settings → Marketplace**.
3. Restart Home Assistant.

On Home Assistant 2026.10 or older, install [HACS](https://hacs.xyz/) first, then use:
[![Open your Home Assistant instance and open this repository in HACS.][badge-my-hacs]][link-my-hacs]
Then download **Favicon Changer** in HACS and restart Home Assistant.

### Manual

1. Download the latest [release][link-release].
2. Copy `custom_components/favicon_changer` into the `custom_components` folder of your
   Home Assistant configuration.
3. Restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up Favicon Changer.][badge-my-config]][link-my-config]

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Favicon Changer** and add it. Nothing changes until you pick a title or icon.

Set the page title and icon from the **Favicon Changer** sidebar panel. Refresh the browser after saving.

## Favicon Panel

After setup, open `Favicon Changer` from the Home Assistant sidebar.

- Select a preset to preview it before applying.
- Upload a custom icon and preview it before applying.
- Custom uploads accept square PNG, ICO, WebP, GIF, or JPEG files up to 1 MiB.
- PNG, WebP, GIF, and JPEG uploads must be at least 64x64 and no larger than 1024x1024.
- ICO uploads must include a square icon at least 16x16.

## Troubleshooting

- **Diagnostics:** Settings → Devices & services → Favicon Changer → ⋮ →
  **Download diagnostics** (credentials are redacted). Attach the file to bug reports.
- **Debug logging:**

```yaml
logger:
  logs:
    custom_components.favicon_changer: debug
```

## Known limitations

- Browsers cache favicons aggressively; do a hard refresh if the icon does not change.
- The integration patches Home Assistant's frontend at runtime, so a frontend change in a new HA release can break it until it is updated.
- Upgrading from 2.0.x: the folder is now `custom_components/favicon_changer/`. Delete the old `ha-favicon-changer` folder, restart, delete the old entry and add Favicon Changer again; an uploaded icon is kept.

## Removal

1. Go to **Settings → Devices & services → Favicon Changer**, open ⋮ and select **Delete**.
2. Remove it in **Settings → Marketplace** (or HACS), or delete
   `custom_components/favicon_changer` if you installed it manually.
3. Restart Home Assistant.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and tests, and [AGENTS.md](AGENTS.md) for the code structure.

## Credits

Maintained fork of [hass-favicon](https://github.com/thomasloven/hass-favicon) by **Thomas Lovén**.

## License

MIT, see [LICENSE](LICENSE).

[badge-marketplace]: https://img.shields.io/badge/Marketplace-Custom-41BDF5.svg
[badge-release]: https://img.shields.io/github/v/release/chiconws/ha-favicon-changer
[badge-ha]: https://img.shields.io/badge/Home%20Assistant-2024.7%2B-41BDF5?logo=home-assistant
[badge-commit-activity]: https://img.shields.io/github/commit-activity/m/chiconws/ha-favicon-changer
[badge-hacs-validation]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/hacs.yaml/badge.svg
[badge-hassfest]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/hassfest.yaml/badge.svg
[badge-tests]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/tests.yaml/badge.svg
[badge-license]: https://img.shields.io/github/license/chiconws/ha-favicon-changer
[badge-my-marketplace]: https://my.home-assistant.io/badges/marketplace_repository.svg
[badge-my-hacs]: https://my.home-assistant.io/badges/hacs_repository.svg
[badge-my-config]: https://my.home-assistant.io/badges/config_flow_start.svg

[link-marketplace]: https://www.home-assistant.io/integrations/marketplace/
[link-release]: https://github.com/chiconws/ha-favicon-changer/releases/latest
[link-ha]: https://www.home-assistant.io/
[link-commits]: https://github.com/chiconws/ha-favicon-changer/commits/main
[link-hacs-validation]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/hacs.yaml
[link-hassfest]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/hassfest.yaml
[link-tests]: https://github.com/chiconws/ha-favicon-changer/actions/workflows/tests.yaml
[link-license]: LICENSE
[link-my-marketplace]: https://my.home-assistant.io/redirect/marketplace_repository/?owner=chiconws&repository=ha-favicon-changer&category=integration
[link-my-hacs]: https://my.home-assistant.io/redirect/hacs_repository/?owner=chiconws&repository=ha-favicon-changer&category=integration
[link-my-config]: https://my.home-assistant.io/redirect/config_flow_start/?domain=favicon_changer
