"""Sensor platform for the Last Chat integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.conversation import async_get_agent_info
from homeassistant.components.conversation.chat_log import (
    ChatLogEventType,
    async_subscribe_chat_logs,
)
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Last Chat sensor."""
    async_add_entities([LastChatSensor(hass, entry)])


class LastChatSensor(SensorEntity):
    """Representation of a Last Chat sensor."""

    _attr_has_entity_name = True
    _attr_name = "Last Chat"
    _attr_should_poll = False
    _attr_unique_id = "last_chat_sensor"
    _attr_icon = "mdi:chat-processing"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._entry = entry
        self._user_requests = hass.data[DOMAIN][entry.entry_id]["user_requests"]
        self._attr_user_request: str | None = None
        self._attr_agent_response: str | None = None
        self._attr_agent_id: str | None = None
        self._attr_agent_name: str | None = None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        return {
            "user_request": self._attr_user_request,
            "agent_response": self._attr_agent_response,
            "agent_id": self._attr_agent_id,
            "agent_name": self._attr_agent_name,
        }

    @callback
    def _handle_pipeline_run(
        self, conversation_id: str, event_type: ChatLogEventType, data: dict[str, Any]
    ) -> None:
        """Handle chat log events."""
        # This is the only event type we need to listen for.
        # It contains both the user's transcribed input and the agent's final response.
        if event_type != ChatLogEventType.PIPELINE_RUN:
            return

        # Extract user input
        user_input = data.get("intent_input")
        if user_input:
            self._attr_user_request = user_input

        # Extract agent response
        agent_response = data.get("intent_output", {}).get("response", {})
        speech = agent_response.get("speech", {}).get("plain", {})
        if speech:
            self._attr_agent_response = speech.get("speech")

        # Extract agent details
        agent_id = agent_response.get("details", {}).get("agent_id")
        if agent_id:
            self._attr_agent_id = agent_id
            agent_info = async_get_agent_info(self.hass, self._attr_agent_id)
            self._attr_agent_name = agent_info.name if agent_info else "Unknown Agent"
        
        self._attr_native_value = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to chat log events."""
        self.async_on_remove(
            async_subscribe_chat_logs(self.hass, self._handle_pipeline_run)
        )
