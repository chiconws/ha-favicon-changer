# Agent Notes: Favicon Changer

Standard: ha-standards v0.5.2

Language: README in **English**; code, logs and `strings.json` in English; translations en + pt-BR.

## Overview

Calculated integration (no device, no entities) that changes the Home Assistant browser title,
favicon and web app icons by patching the frontend at runtime. Fork of thomasloven/hass-favicon.
Single config entry.

## Code structure

All code in `custom_components/favicon_changer/`.

- `__init__.py`: saves the pristine `frontend.IndexView.get_template` and manifest keys in `hass.data[DOMAIN]`, wraps the template to inject title/icons, restores everything on unload; `find_icons` maps icon files to URLs.
- `panel.py`: sidebar panel registration, admin-only config and upload views, custom icon files; panel JS and presets served as static paths.
- `custom_icons.py`: upload validation (format, size, square) and atomic save via a staging dir.
- `preset_catalog.py` + `presets/`: shipped icon presets, discovered from folders.
- `config_flow.py`: title + preset; `diagnostics.py`: config and current custom icon.
- `frontend/`: the panel JS.

## Key concepts

- Frontend internals used: `IndexView.get_template`, `_async_render_index_cached`, `add_manifest_json_key`. Check them on every HA release bump.
- The panel writes options; the update listener re-applies them without a reload.

## Local validation (before push)

The pre-commit hook (`.githooks/pre-commit`) runs ruff, mypy, Pyright and pytest. By hand:

```bash
python -m ruff check custom_components/favicon_changer tests
python -m coverage run -m pytest -q && python -m coverage report
```

Deploy to ha-test: VS Code tasks in `.vscode/`.

## Deviations from standard

- No `coordinator.py`, `entity.py` or entities: the integration only patches the frontend.
- `hass.data[DOMAIN]` instead of `entry.runtime_data`: the pristine frontend hooks are process-wide and must outlive entry reloads.
