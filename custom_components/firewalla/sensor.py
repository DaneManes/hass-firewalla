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
from homeassistant.helpers import entity_registry as EntityRegistry

from .const import (
    DOMAIN,
    CONF_ENABLE_FLOWS,
    CONF_ENABLE_TRAFFIC,
    CONF_ENABLE_ALARMS,
    CONF_ENABLE_RULES,
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
        
        # Bandwidth Sensors
        if enable_traffic:
            if "totalDownload" in device:
                entities.append(FirewallaTotalDownloadSensor(coordinator, device))
            if "totalUpload" in device:
                entities.append(FirewallaTotalUploadSensor(coordinator, device))

    # --- Section 3: Flows ---
    if enable_flows and "flows" in coordinator.data:
        from .const import CONF_FLOW_COUNT, DEFAULT_FLOW_COUNT
        # Use a unique variable name for flows
        user_flow_limit = opts.get(CONF_FLOW_COUNT, data_src.get(CONF_FLOW_COUNT, DEFAULT_FLOW_COUNT))
        
        flow_device_ids = {
            f.get("device", {}).get("id") or f.get("source", {}).get("id") 
            for f in coordinator.data["flows"]
            if isinstance(f, dict)
        }
    
        for dev_id in flow_device_ids:
            if not dev_id: continue
            device = next((d for d in devices_list if d.get("id") == dev_id), None)
            # FIX: Pass the limit here
            entities.append(FirewallaDeviceFlowsSensor(coordinator, dev_id, user_flow_limit, device))

    # --- Section 4: Alarms ---
    if enable_alarms and "alarms" in coordinator.data:
        from .const import CONF_ALARM_COUNT, DEFAULT_ALARM_COUNT
        user_alarm_limit = opts.get(CONF_ALARM_COUNT, data_src.get(CONF_ALARM_COUNT, DEFAULT_ALARM_COUNT))
        entities.append(FirewallaRecentAlarmsSensor(coordinator, user_alarm_limit))
    
    # 5. Process Rules (Summary Sensor)
    if enable_rules and "rules" in coordinator.data:
        entities.append(FirewallaRulesSummarySensor(coordinator))

    # 6. Finally add entities to the database
    if entities:
        async_add_entities(entities)
        
    # 7. Cleanup orphaned entities
    ent_reg = EntityRegistry.async_get(hass)
    
    # Get all entities currently registered under this config entry
    registered_entities = EntityRegistry.async_entries_for_config_entry(ent_reg, entry.entry_id)
    
    for entity_entry in registered_entities:
        # Check unique_id to identify which feature the entity belongs to
        unique_id = entity_entry.unique_id
        
        # Cleanup Flows
        if "recent_flows" in unique_id and not enable_flows:
            ent_reg.async_remove(entity_entry.entity_id)
            _LOGGER.info("Removed orphaned flow entity: %s", entity_entry.entity_id)
            
        # Cleanup Alarms
        elif "recent_alarms" in unique_id and not enable_alarms:
            ent_reg.async_remove(entity_entry.entity_id)
            _LOGGER.info("Removed orphaned alarm entity: %s", entity_entry.entity_id)

        # Cleanup Rules
        elif "rules_summary" in unique_id and not enable_rules:
            ent_reg.async_remove(entity_entry.entity_id)
            _LOGGER.info("Removed orphaned rules entity: %s", entity_entry.entity_id)
            
        # Cleanup Upload Traffic
        elif "total_upload" in unique_id and not enable_traffic:
            ent_reg.async_remove(entity_entry.entity_id)
            _LOGGER.info("Removed orphaned rules entity: %s", entity_entry.entity_id)

        # Cleanup Download Traffic
        elif "total_download" in unique_id and not enable_traffic:
            ent_reg.async_remove(entity_entry.entity_id)
            _LOGGER.info("Removed orphaned rules entity: %s", entity_entry.entity_id)

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
    
    def __init__(self, coordinator, alarm_limit):
        """Initialize the summary sensor."""
        super().__init__(coordinator)

        self.alarm_limit = alarm_limit
        self._attr_name = "Firewalla Recent Alarms"
        self._attr_unique_id = f"{DOMAIN}_recent_alarms_summary"
        self._attr_icon = "mdi:shield-alert"
        self._attr_native_unit_of_measurement = "alarms"
        
        subdomain = getattr(coordinator, 'subdomain', 'my')
        
        # Inside FirewallaRecentAlarmsSensor and FirewallaRulesSummarySensor __init__
        if coordinator.data.get("boxes") and coordinator.data["boxes"]:
            box = coordinator.data["boxes"][0]
            box_model = box.get("model", "Box").title() # Capitalize here too
            box_id = box.get("id")
            
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"box_{box_id}")},
                name=f"Firewalla {box_model}", # Match binary_sensor.py
                manufacturer="Firewalla",
                configuration_url=f"https://{subdomain}.firewalla.net",
            )

    @property
    def native_value(self):
        """Return the NUMBER of alarms so the unit 'alarms' is valid."""
        return len(self.coordinator.data.get("alarms", []))

    @property
    def extra_state_attributes(self):
        alarms = self.coordinator.data.get("alarms", [])
        
        processed_alarms = []
        for a in alarms[-self.alarm_limit:]:  # Keep the 20 most recent
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

class FirewallaDeviceFlowsSensor(FirewallaBaseSensor):
    """A sensor that summarizes the most recent flows for a specific device."""
    
    def __init__(self, coordinator, device_id, flow_limit, device=None):
        self.device_id = device_id
        self.flow_limit = flow_limit
        # We reuse the base init but give it a generic suffix
        super().__init__(coordinator, device or {"id": device_id, "name": "Unknown"}, "Recent Flows")
        self._attr_icon = "mdi:transfer"
        self._attr_native_unit_of_measurement = "flows"

    @property
    def native_value(self):
        """State is the count of active flows for this device."""
        flows = self.coordinator.data.get("flows", [])
        return len([
            f for f in flows 
            if isinstance(f, dict) and (
                f.get("device", {}).get("id") == self.device_id or 
                f.get("source", {}).get("id") == self.device_id
            )
        ])

    @property
    def extra_state_attributes(self):
        """Limit to the most recent flows."""
        all_flows = self.coordinator.data.get("flows", [])
        # Filter flows belonging to this device
        device_flows = [f for f in all_flows if (f.get("device", {}).get("id") == self.device_id or 
                                                f.get("source", {}).get("id") == self.device_id)]
        
        # Sort by timestamp (if available) and take the last 20 if not otherwise configured
        # Assuming higher index or timestamp means newer
        recent_flows = device_flows[-self.flow_limit:] 
        
        processed_entries = []
        for f in recent_flows:
            dst = f.get("destination", {}).get("name") or f.get("destination", {}).get("ip", "unknown")
            processed_entries.append({
                "blocked": f.get("block"),
                "destination": dst,
                "download_kb": round(f.get("download", 0) / 1024, 2),
                "upload_kb": round(f.get("upload", 0) / 1024, 2),
                "protocol": f.get("protocol"),
                "port": f.get("device", {}).get("port", "unknown")
            })

        return {
            "recent_flows": processed_entries,
            "total_device_flows": len(device_flows)
        }


class FirewallaRulesSummarySensor(CoordinatorEntity, SensorEntity):
    """A single sensor that collects and summarizes all Firewalla rules."""

    def __init__(self, coordinator):
        """Initialize the summary sensor."""
        super().__init__(coordinator)
        self._attr_name = "Firewalla Rules"
        self._attr_unique_id = f"{DOMAIN}_rules_summary"
        self._attr_icon = "mdi:shield-edit"
        self._attr_native_unit_of_measurement = "rules"
        
        subdomain = getattr(coordinator, 'subdomain', 'my')
        
        # This links the sensor to the Firewalla Box device in the UI
        if coordinator.data.get("boxes"):
            box_id = coordinator.data["boxes"][0].get("id")
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"box_{box_id}")},
                configuration_url=f"https://{subdomain}.firewalla.net",
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