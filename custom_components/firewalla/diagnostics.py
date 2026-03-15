"""Diagnostics support for Firewalla."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_API_TOKEN, CONF_SUBDOMAIN

# Fields to scrub for privacy
TO_REDACT = {
    CONF_API_TOKEN, 
    "publicIP",
    "hostName",
    "destination",
    "source"
}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    # Build the report using the official redaction utility
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coord_data_summary": {
            "boxes": len(coordinator.data.get("boxes", [])),
            "devices": len(coordinator.data.get("devices", [])),
            "rules": len(coordinator.data.get("rules", [])),
            "alarms": len(coordinator.data.get("alarms", [])),
            "flows": len(coordinator.data.get("flows", [])),
        },
        # Optional: Include full redacted data if you want "Everything"
        "raw_data": async_redact_data(coordinator.data, TO_REDACT),
    }

async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a specific device."""
    coordinator = entry.runtime_data.coordinator
    
    # Extract the device ID from HA's device registry identifiers
    # (DOMAIN, firewalla_device_id)
    firewalla_id = next(iter(device.identifiers))[1]

    # Find this specific device in our coordinator data
    device_data = next(
        (d for d in coordinator.data.get("devices", []) if d.get("id") == firewalla_id),
        None
    )

    # Find flows associated with this device
    device_flows = [
        f for f in coordinator.data.get("flows", [])
        if f.get("device", {}).get("id") == firewalla_id or f.get("source", {}).get("id") == firewalla_id
    ]

    return {
        "device_info": async_redact_data(device_data, TO_REDACT) if device_data else "Not Found",
        "recent_flows": async_redact_data(device_flows, TO_REDACT),
    }