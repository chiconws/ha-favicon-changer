"""Shared fixtures: load the integration with a real http server but a stubbed frontend."""

import homeassistant.components.frontend as frontend
import pycares
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Claim the name before the harness imports its own testing_config/custom_components.
import custom_components  # noqa: F401

# pycares starts a process-wide daemon thread on first use; start it now so the
# harness's lingering-thread check doesn't blame whichever test runs first.
pycares._shutdown_manager.start()

DOMAIN = "favicon_changer"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load integrations from custom_components/."""


@pytest.fixture(autouse=True)
def restore_frontend():
    """The integration patches module-level frontend state; undo it after each test."""
    get_template = frontend.IndexView.get_template
    manifest = {key: frontend.MANIFEST_JSON[key] for key in ("icons", "name", "short_name")}
    yield
    setattr(frontend.IndexView, "get_template", get_template)  # noqa: B010
    for key, value in manifest.items():
        frontend.add_manifest_json_key(key, value)


@pytest.fixture
async def http(hass: HomeAssistant, tmp_path) -> None:
    """Set up http; mark frontend deps loaded since hass_frontend is not installed."""
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, "http", {})
    hass.config.components.update({"frontend", "panel_custom"})


@pytest.fixture
async def entry(hass: HomeAssistant, http) -> MockConfigEntry:
    """A loaded config entry using the beta preset."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Favicon Changer",
        data={"title": "My Home", "icon_preset": "beta", "custom_icon_path": ""},
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
