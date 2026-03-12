"""Sensor platform for Firewalla integration."""
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

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
    CONF_ENABLE_ALARMS,
    CONF_ENABLE_RULES
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
    enable_rules = opts.get(CONF_ENABLE_RULES, data_src.get(CONF_ENABLE_RULES, False))
    
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
        entities.append(FirewallaLastActiveSensor(coordinator, device))
        entities.append(FirewallaIpReservationSensor(coordinator, device))
        entities.append(FirewallaNetworkNameSensor(coordinator, device))
        entities.append(FirewallaGroupNameSensor(coordinator, device))
        
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
    if enable_alarms and "alarms" in coordinator.data:
        entities.append(FirewallaRecentAlarmsSensor(coordinator))

    # 5. Process Rules (Summary Sensor)
    if enable_rules and "rules" in coordinator.data:
        entities.append(FirewallaRulesSummarySensor(coordinator))

    # 6. Finally add entities to the database
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
        self._attr_icon = "mdi:fingerprint"

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        mac = device.get("mac", self.device_id)
        return mac[4:] if mac.startswith("mac:") else mac

class FirewallaIpAddressSensor(FirewallaBaseSensor):
    """Sensor for IP Address."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "IP Address")
        self._attr_icon = "mdi:ip-network"

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        return device.get("ip")

class FirewallaIpReservationSensor(FirewallaBaseSensor):
    """Sensor for IP Address."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "IP Reservation")
        self._attr_icon = "mdi:ip"

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        is_reserved = device.get("ipReserved")
        if is_reserved is True:
            return "Reserved"
        
        return "DHCP"

class FirewallaLastActiveSensor(FirewallaBaseSensor):
    """Sensor for device last seen time."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "Last Active")

    @property
    def native_value(self):
        """Return the timestamp as a datetime object."""
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        last_active = device.get("lastSeen")
        if not last_active:
            return None

        try:
            # Firewalla gives us a float Unix epoch
            timestamp = float(last_active)
            # We return a timezone-aware UTC datetime
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, TypeError):
            return None

class FirewallaNetworkNameSensor(FirewallaBaseSensor):
    """Sensor for Network Name."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "Network Name")
        self._attr_icon = "mdi:account-network"

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        network_info = device.get("network")
        if network_info:
            return network_info.get("name", "No name")
        
        return "None"

class FirewallaGroupNameSensor(FirewallaBaseSensor):
    """Sensor for Group Name."""
    def __init__(self, coordinator, device):
        super().__init__(coordinator, device, "Group Name")
        self._attr_icon = "mdi:account-group"

    @property
    def native_value(self):
        device = next((d for d in self.coordinator.data.get("devices", []) if d.get("id") == self.device_id), None)
        if not device:
            return None
            
        group_info = device.get("group")
        if group_info:
            return group_info.get("name", "Ungrouped")
        
        return "None"

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
        devices = self.coordinator.data.get("devices", [])
        device = next((d for d in devices if d.get("id") == self.device_id), None)
        
        if not device:
            return None
            
        # Convert bytes to kilobytes
        upload_bytes = device.get("totalUpload", 0)
        return round(upload_bytes / 1024, 2)

class FirewallaRecentAlarmsSensor(CoordinatorEntity, SensorEntity):
    """Summary sensor for security events."""
    _attr_icon = "mdi:shield-alert"
    
    def __init__(self, coordinator):
        """Initialize the summary sensor."""
        super().__init__(coordinator)

        self._attr_name = "Firewalla Recent Alarms"
        self._attr_unique_id = f"{DOMAIN}_recent_alarms_summary"
        self._attr_icon = "mdi:shield-alert"
        self._attr_native_unit_of_measurement = "alarms"
        
        # Link it to the Firewalla Box Device Card
        if coordinator.data.get("boxes") and coordinator.data["boxes"]:
            box_id = coordinator.data["boxes"][0].get("id")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"box_{box_id}")},
                name="Firewalla Box",
                manufacturer="Firewalla",
            )

    @property
    def native_value(self):
        """Return the NUMBER of alarms so the unit 'alarms' is valid."""
        return len(self.coordinator.data.get("alarms", []))

    @property
    def extra_state_attributes(self):
        alarms = self.coordinator.data.get("alarms", [])
        
        processed_alarms = []
        for a in alarms[:20]:  # Keep the 20 most recent
            raw_ts = a.get("ts") or a.get("activeTs") or a.get("updatedAt")
            processed_alarms.append({
                "message": a.get("message"),
                "type": a.get("_type", "Unknown"),
                "device": a.get("device", {}).get("name", "Unknown Device"),
                "dest": a.get("remote", {}).get("domain") or a.get("remote", {}).get("ip", "N/A"),
                "time": raw_ts if raw_ts else 0
            })
            
        return {
            "total_alarms": len(alarms),
            "recent_events": processed_alarms
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

class FirewallaRulesSummarySensor(CoordinatorEntity, SensorEntity):
    """A single sensor that collects and summarizes all Firewalla rules."""

    def __init__(self, coordinator):
        """Initialize the summary sensor."""
        super().__init__(coordinator)
        self._attr_name = "Firewalla Rules"
        self._attr_unique_id = f"{DOMAIN}_rules_summary"
        self._attr_icon = "mdi:shield-edit"
        self._attr_native_unit_of_measurement = "rules"

        # This links the sensor to the Firewalla Box device in the UI
        if coordinator.data.get("boxes"):
            box_id = coordinator.data["boxes"][0].get("id")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"box_{box_id}")},
            )

    @property
    def native_value(self):
        """The state is the total count of rules."""
        return len(self.coordinator.data.get("rules", []))

    @property
    def extra_state_attributes(self):
        """Build a meaningful dictionary of rules using Device and Group names."""
        raw_rules = self.coordinator.data.get("rules", [])
        devices_data = self.coordinator.data.get("devices", [])
        
        # 1. Build Lookup Maps from the devices list
        name_map = {}
        for d in devices_data:
            d_id = d.get("id")
            d_name = d.get("name") or d.get("ip")
            
            # Map the Device ID to its Name
            if d_id:
                name_map[str(d_id)] = d_name
            
            # Map the Group ID to its Name (found inside the device object)
            group_info = d.get("group")
            if group_info and group_info.get("id"):
                name_map[str(group_info["id"])] = group_info.get("name")

        processed_rules = []
        for rule in raw_rules:
            scope_obj = rule.get("scope", {})
            scope_id = str(scope_obj.get("value", ""))
            
            # Resolve Scope Name
            resolved_scope = name_map.get(scope_id) or scope_id or "All Devices"
            
            target_obj = rule.get("target", {})
            target_val = target_obj.get("value") or "System"
            # RE-ADDED: Get the target type (e.g., domain, ip, region)
            target_type = target_obj.get("type", "unknown").upper() 

            processed_rules.append({
                "name": rule.get("notes") or f"{rule.get('action').capitalize()} {target_val}",
                "action": rule.get("action"),
                "scope": resolved_scope,
                "target": target_val,
                "target_type": target_type, # <--- Back in the mix!
                "active": rule.get("status") == "active",
                "time": rule.get("ts")
            })

        return {
            "rules_list": processed_rules,
            "total_rules": len(processed_rules),
            "active_rules": sum(1 for r in processed_rules if r.get("active"))
        }
