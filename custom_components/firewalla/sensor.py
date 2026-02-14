"""Sensor platform for Firewalla integration."""
import logging
from typing import Any, Dict, Optional
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_DEVICE_ID,
    ATTR_DEVICE_NAME,
    ATTR_NETWORK_ID,
    CONF_ENABLE_FLOWS,
    CONF_ENABLE_TRAFFIC,
    CONF_ENABLE_ALARMS
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up sensors for Firewalla devices using runtime_data."""
    coordinator = entry.runtime_data.coordinator

    # 1. Retrieve flags (Consistent with options/data priority)
    opts = entry.options
    data_src = entry.data
    enable_flows = opts.get(CONF_ENABLE_FLOWS, data_src.get(CONF_ENABLE_FLOWS, False))
    enable_traffic = opts.get(CONF_ENABLE_TRAFFIC, data_src.get(CONF_ENABLE_TRAFFIC, False))
    enable_alarms = opts.get(CONF_ENABLE_ALARMS, data_src.get(CONF_ENABLE_ALARMS, False))
    
    if not coordinator or not coordinator.data:
        return
    
    entities = []
    # Cache devices list to avoid repeated dict lookups in loops
    devices_list = coordinator.data.get("devices", [])
    
    # 2. Process devices
    for device in devices_list:
        if not isinstance(device, dict) or "id" not in device:
            continue

        # Identity Sensors
        entities.append(FirewallaMacAddressSensor(coordinator, device))
        entities.append(FirewallaIpAddressSensor(coordinator, device))
        entities.append(FirewallaNetworkNameSensor(coordinator, device))
        
        # Bandwidth Sensors
        if enable_traffic:
            if "totalDownload" in device:
                entities.append(FirewallaTotalDownloadSensor(coordinator, device))
            if "totalUpload" in device:
                entities.append(FirewallaTotalUploadSensor(coordinator, device))

    # 3. Process Flows (Conditional)
    if enable_flows and "flows" in coordinator.data:
        for flow in coordinator.data["flows"]:
            # Find associated device
            device_id = flow.get("device", {}).get("id") or flow.get("source", {}).get("id")
            
            # Safe 'next' call with a default of None to prevent StopIteration crashes
            device = next((d for d in devices_list if d.get("id") == device_id), None)
            
            entities.append(FirewallaFlowSensor(coordinator, flow, device))

    # 4. Process Alarms (Summary Sensor)
    if enable_alarms:
        entities.append(FirewallaRecentAlarmsSensor(coordinator))
    
    if entities:
        async_add_entities(entities)

class FirewallaBaseSensor(CoordinatorEntity, SensorEntity):
    """Base sensor to ensure entities are enabled by default."""
    
    @property
    def entity_registry_enabled_default(self) -> bool:
        """Force sensors to be enabled on discovery."""
        return True

    def __init__(self, coordinator, device, suffix: str):
        super().__init__(coordinator)
        self.device_id = device["id"]
        self._attr_name = f"{device.get('name', 'Unknown')} {suffix}"
        self._attr_unique_id = f"{DOMAIN}_{suffix.lower().replace(' ', '_')}_{self.device_id}"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=device.get("name", f"Firewalla Device {self.device_id}"),
            manufacturer="Firewalla",
        )

class FirewallaMacAddressSensor(FirewallaBaseSensor):
    """Sensor for MAC Address."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "MAC Address")

    @property
    def native_value(self):
        # Find the device in latest data
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        mac = device.get("mac", self.device_id)
        return mac[4:] if mac.startswith("mac:") else mac

class FirewallaIpAddressSensor(FirewallaBaseSensor):
    """Sensor for IP Address."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "IP Address")

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        return device.get("ip")

class FirewallaNetworkNameSensor(FirewallaBaseSensor):
    """Sensor for Network Name."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "Network Name")

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        return device.get("network", {}).get("name")

class FirewallaTotalDownloadSensor(FirewallaBaseSensor):
    """Sensor for Total Download."""
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfInformation.KILOBYTES

    def __init__(self, coordinator, device):
        """Initialize the download sensor."""
        super().__init__(coordinator, device, "Total Download")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        # Find the device in the current coordinator data
        devices = self.coordinator.data.get("devices", [])
        device = next((d for d in devices if d.get("id") == self.device_id), None)
        
        if not device:
            return None
            
        # Convert bytes to kilobytes
        download_bytes = device.get("totalDownload", 0)
        return round(download_bytes / 1024, 2)

class FirewallaTotalUploadSensor(FirewallaBaseSensor):
    """Sensor for Total Upload."""
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfInformation.KILOBYTES

    def __init__(self, coordinator, device):
        """Initialize the upload sensor."""
        super().__init__(coordinator, device, "Total Upload")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        # Find the device in the current coordinator data
        devices = self.coordinator.data.get("devices", [])
        device = next((d for d in devices if d.get("id") == self.device_id), None)
        
        if not device:
            return None
            
        # Convert bytes to kilobytes
        upload_bytes = device.get("totalUpload", 0)
        return round(upload_bytes / 1024, 2)

class FirewallaRecentAlarmsSensor(FirewallaBaseSensor):
    """Summary sensor for security events."""
    _attr_icon = "mdi:shield-alert"
    
    def __init__(self, coordinator):
        """Initialize the summary sensor."""
        # 1. We create a 'fake' device dict to satisfy the Base Class requirements
        # This keeps the unique_id generation consistent.
        dummy_device = {"id": "global_alarms", "name": "Firewalla"}
        
        # 2. Call the base class with all 3 required arguments
        super().__init__(coordinator, dummy_device, "Recent Alarms")
        
        # 3. Explicitly set the unique_id (overriding the base class version if preferred)
        self._attr_unique_id = f"{DOMAIN}_recent_alarms_summary_v2"
        
        # 4. Link it to the Firewalla Box Device Card
        if coordinator.data.get("boxes") and coordinator.data["boxes"]:
            box_id = coordinator.data["boxes"][0].get("id")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"box_{box_id}")},
                name="Firewalla Box",
                manufacturer="Firewalla",
            )

    @property
    def native_value(self):
        """Return the message of the most recent alarm."""
        alarms = self.coordinator.data.get("alarms", []) if self.coordinator.data else []
        if not alarms:
            return "No Alarms"
        return alarms[0].get("message", "Unknown Event")

    @property
    def extra_state_attributes(self):
        """Store the list of recent alarms in attributes."""
        alarms = self.coordinator.data.get("alarms", []) if self.coordinator.data else []
        return {
            "total_alarms": len(alarms),
            "recent_events": alarms[:5]
        }

class FirewallaFlowSensor(FirewallaBaseSensor):
    """Individual flow sensor - inherits auto-enable property."""
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.KILOBYTES

    def __init__(self, coordinator, flow, device=None):
        """Initialize the flow sensor."""
        self.flow_id = flow["id"]
        
        # Determine the name based on destination
        dst = flow.get("destination", {}).get("name") or flow.get("destination", {}).get("ip", "unknown")
        suffix = f"Flow to {dst}"
        
        # Use provided device or a fallback ID for the base class unique_id generation
        dev_id = device["id"] if device else f"flow_{self.flow_id}"
        dev_name = device.get("name", "Unknown Device") if device else "Standalone Flow"
        
        # Initialize the base class
        super().__init__(coordinator, {"id": dev_id, "name": dev_name}, suffix)

        # OVERRIDE the DeviceInfo from the base class IF we have a real device.
        # This ensures the flow sensor is grouped under the phone/laptop it belongs to.
        if device:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, device["id"])},
            )
        else:
            # If no device, we link it to the Firewalla Box itself to avoid "orphaned" entities
            if coordinator.data.get("boxes"):
                box_id = coordinator.data["boxes"][0].get("id")
                self._attr_device_info = DeviceInfo(
                    identifiers={(DOMAIN, f"box_{box_id}")},
                )

    @property
    def native_value(self):
        # Look up the latest data for this specific flow from the coordinator
        flow = next((f for f in self.coordinator.data.get("flows", []) if f["id"] == self.flow_id), {})
        return round((flow.get("download", 0) + flow.get("upload", 0)) / 1024, 2)
