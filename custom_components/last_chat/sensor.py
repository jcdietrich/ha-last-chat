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
        self._pending_requests: dict[str, str] = {}
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
        _LOGGER.debug("Event received: type=%s, data=%s", event_type, data)

        if event_type == ChatLogEventType.CONTENT_ADDED:
            content_data = data.get("content", {})
            role = content_data.get("role")

            if role == "user":
                user_text = content_data.get("content")
                _LOGGER.info("User request received (ID: %s): '%s'", conversation_id, user_text)
                self._pending_requests[conversation_id] = user_text
                return

            if role in ("assistant", "tool_result"):
                _LOGGER.info("Potential agent response event (ID: %s, role: %s), scheduling async task.", conversation_id, role)
                self.hass.async_create_task(
                    self._async_process_agent_response(conversation_id, content_data)
                )

        elif event_type == ChatLogEventType.UPDATED:
            chat_log_data = data.get("chat_log", {})
            if chat_log_data.get("continue_conversation") is False:
                _LOGGER.info("Conversation ended event received for ID: %s. Scheduling cleanup.", conversation_id)
                self.hass.async_create_task(
                    self._async_handle_conversation_end(conversation_id)
                )

    async def _async_process_agent_response(
        self, conversation_id: str, content_data: dict[str, Any]
    ) -> None:
        """Process a potential agent response, only updating if it contains spoken text."""
        _LOGGER.debug("Processing agent response (ID: %s): content_data=%s", conversation_id, content_data)
        
        user_request = self._pending_requests.get(conversation_id)
        if not user_request:
            _LOGGER.warning("No pending user request for conversation_id=%s. This is a follow-up, not updating sensor.", conversation_id)
            return

        role = content_data.get("role")
        response_text = None

        if role == "tool_result":
            tool_result = content_data.get("tool_result", {})
            speech_data = tool_result.get("speech", {}).get("plain", {})
            response_text = speech_data.get("speech")
        elif role == "assistant":
            response_text = content_data.get("content")

        if response_text:
            _LOGGER.info("Definitive response found for ID=%s: '%s'", conversation_id, response_text)
            self._pending_requests.pop(conversation_id, None)
            await self._update_sensor_state(conversation_id, user_request, response_text, content_data.get("agent_id"))

    async def _async_handle_conversation_end(self, conversation_id: str) -> None:
        """Handle the end of a conversation, cleaning up hanging requests."""
        if conversation_id in self._pending_requests:
            _LOGGER.info("Conversation ended (ID: %s) without a spoken response. Updating sensor to reflect action.", conversation_id)
            user_request = self._pending_requests.pop(conversation_id)
            await self._update_sensor_state(conversation_id, user_request, "Action Performed (no verbal response)", "conversation.home_assistant")

    async def _update_sensor_state(self, conversation_id: str, user_request: str, agent_response: str, agent_id: str | None) -> None:
        """Update the sensor's state attributes and write the state."""
        self._attr_user_request = user_request
        self._attr_agent_response = agent_response
        self._attr_agent_id = agent_id
        
        self._attr_agent_name = None
        if self._attr_agent_id:
            _LOGGER.info("Fetching agent info for: %s", self._attr_agent_id)
            agent_info = async_get_agent_info(self.hass, self._attr_agent_id)
            self._attr_agent_name = agent_info.name if agent_info else None
            _LOGGER.info("Agent name: %s", self._attr_agent_name)
        
        self._attr_native_value = dt_util.utcnow()
        self.async_write_ha_state()
        _LOGGER.info("Sensor state updated for ID=%s.", conversation_id)