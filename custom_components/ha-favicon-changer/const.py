"""Constants for the favicon integration."""

DOMAIN = "ha-favicon-changer"
INTEGRATION_TITLE = "Favicon Changer"

CONF_TITLE = "title"
CONF_ICON_PRESET = "icon_preset"
CONF_CUSTOM_ICON_PATH = "custom_icon_path"

PRESET_PUBLIC_ROOT = "/api/ha-favicon-changer/presets"
PRESET_STORAGE_ROOT = ("www", "favicon-presets")

CUSTOM_ICON_PUBLIC_ROOT = "/api/ha-favicon-changer/custom"
CUSTOM_ICON_STORAGE_ROOT = ("www", "favicon-changer-custom")
CUSTOM_ICON_SLOT = "current"
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_TITLE_LENGTH = 120

DEFAULT_MANIFEST_NAME = "Home Assistant"
DEFAULT_MANIFEST_SHORT_NAME = "Assistant"
