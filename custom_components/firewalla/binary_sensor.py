"""Binary sensor platform for Firewalla integration."""
import logging
from datetime import datetime
from typing import Any, Dict

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_DEVICE_ID
    )

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up Firewalla binary sensors based on runtime data."""
    coordinator = entry.runtime_data.coordinator
    
    if not coordinator or not coordinator.data:
        return
    
    entities = []
    
    # 1. Device Connectivity Sensors (Always Enabled)
    if "devices" in coordinator.data:
        for device in coordinator.data["devices"]:
            if isinstance(device, dict) and "id" in device:
                entities.append(FirewallaOnlineSensor(coordinator, device))
    
    # 2. Box Status Sensors (Always Enabled)
    if "boxes" in coordinator.data:
        for box in coordinator.data["boxes"]:
            if isinstance(box, dict) and "id" in box:
                entities.append(FirewallaBoxOnlineSensor(coordinator, box))
    
    async_add_entities(entities)


class FirewallaBaseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Common base for all Firewalla binary sensors."""
    
    @property
    def entity_registry_enabled_default(self) -> bool:
        """Force entities to be enabled by default."""
        return True


class FirewallaOnlineSensor(FirewallaBaseBinarySensor):
    """Binary sensor for Firewalla device online status."""

    def __init__(self, coordinator, device):
        super().__init__(coordinator)
        self.device_id = device["id"]
        self._attr_name = f"{device.get('name', 'Unknown')} Online"
        self._attr_unique_id = f"{DOMAIN}_online_{self.device_id}"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

        # Group with the specific device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=device.get("name", f"Firewalla Device {self.device_id}"),
            manufacturer="Firewalla",
        )
        self._update_attributes(device)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state from coordinator data."""
        device = next((d for d in self.coordinator.data.get("devices", []) 
                      if d.get("id") == self.device_id), None)
        if device:
            self._update_attributes(device)
            self.async_write_ha_state()

    def _update_attributes(self, device):
        self._attr_is_on = device.get("online", False)
        
        self._attr_extra_state_attributes = {
            "ip_address": device.get("ip"),
            "mac_address": device.get("mac"),
            "network": device.get("network", {}).get("name"),
        }


class FirewallaBoxOnlineSensor(FirewallaBaseBinarySensor):
    """Binary sensor for Firewalla box online status."""

    def __init__(self, coordinator, box):
        super().__init__(coordinator)
        self.box_id = box["id"]
        self._attr_name = f"Firewalla Box {box.get('name', 'Unknown')} Online"
        self._attr_unique_id = f"{DOMAIN}_box_online_{self.box_id}"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"box_{self.box_id}")},
            name=f"Firewalla Box {box.get('name', self.box_id)}",
            manufacturer="Firewalla",
            model=box.get("model", "Firewalla Box"),
        )
        self._update_attributes(box)

    @callback
    def _handle_coordinator_update(self) -> None:
        box = next((b for b in self.coordinator.data.get("boxes", []) 
                   if b.get("id") == self.box_id), None)
        if box:
            self._update_attributes(box)
            self.async_write_ha_state()

    def _update_attributes(self, box):
        self._attr_is_on = box.get("online", False)
        self._attr_extra_state_attributes = {
            "version": box.get("version"),
            "last_seen": box.get("lastActiveTimestamp"),
        }
