"""Sensor platform for the Last Chat integration."""
from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Last Chat sensor."""
    _LOGGER.info("Setting up Last Chat sensor.")
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
        _LOGGER.info("Initializing Last Chat sensor.")
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

    async def async_added_to_hass(self) -> None:
        """Subscribe to chat log events."""
        _LOGGER.info("Subscribing to chat log events.")
        self.async_on_remove(
            async_subscribe_chat_logs(self.hass, self._handle_chat_log_event)
        )

    @callback
    def _handle_chat_log_event(
        self, conversation_id: str, event_type: ChatLogEventType, data: dict[str, Any]
    ) -> None:
        """Handle chat log events from the conversation component."""
        _LOGGER.info("Event received: type=%s, data=%s", event_type, data)
        if event_type != ChatLogEventType.CONTENT_ADDED:
            return

        content_data = data.get("content", {})
        role = content_data.get("role")

        if role == "user":
            user_text = content_data.get("content")
            _LOGGER.info("User request received: '%s'", user_text)
            self._user_requests[conversation_id] = user_text
            return

        # The final spoken response can come from a tool_result or a final assistant event
        if role == "tool_result" or (role == "assistant" and "content" in content_data):
            _LOGGER.info("Agent response event received, scheduling async task.")
            self.hass.async_create_task(
                self._async_process_agent_response(conversation_id, content_data)
            )

    async def _async_process_agent_response(
        self, conversation_id: str, content_data: dict[str, Any]
    ) -> None:
        """Process the agent's response asynchronously."""
        _LOGGER.info("Processing agent response for conversation_id=%s, content_data=%s", conversation_id, content_data)
        if conversation_id not in self._user_requests:
            _LOGGER.warning("No matching user request for conversation_id=%s", conversation_id)
            return

        role = content_data.get("role")
        response_text = None

        if role == "tool_result":
            tool_result = content_data.get("tool_result", {})
            speech = tool_result.get("speech", {}).get("plain", {})
            response_text = speech.get("speech")
        elif role == "assistant":
            response_text = content_data.get("content")

        # Only update if we have a definitive text response
        if response_text:
            _LOGGER.info("Found definitive response: '%s'", response_text)
            self._attr_user_request = self._user_requests.pop(conversation_id)
            self._attr_agent_response = response_text
            
            # Agent ID might be in different places
            agent_id = content_data.get("agent_id")
            if agent_id:
                self._attr_agent_id = agent_id
            
            self._attr_agent_name = None
            if self._attr_agent_id:
                _LOGGER.info("Fetching agent info for: %s", self._attr_agent_id)
                agent_info = async_get_agent_info(self.hass, self._attr_agent_id)
                self._attr_agent_name = agent_info.name if agent_info else None
                _LOGGER.info("Agent name: %s", self._attr_agent_name)
            
            self._attr_native_value = dt_util.utcnow()
            self.async_write_ha_state()
            _LOGGER.info("Sensor state updated.")
        else:
            _LOGGER.info("No definitive response text found in this event, waiting for next event.")
