"""The Last Chat integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

# Minimal __init__.py for debugging the loading issue.

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Last Chat component."""
    # This is the first function HA calls. Returning True tells HA the component is ready.
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Last Chat from a config entry."""
    # This function is called after the user successfully adds the integration via the UI.
    # For now, we do nothing but signal success. The sensor setup will be added back later.
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # This is called when the user removes the integration.
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])