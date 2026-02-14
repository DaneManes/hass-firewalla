"""Device tracker platform for Firewalla."""
import logging
from homeassistant.components.device_tracker import SourceType, ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN 

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up Firewalla device trackers."""
    # Modern runtime_data access
    coordinator = entry.runtime_data.coordinator
    
    if not coordinator or "devices" not in coordinator.data:
        return

    entities = [
        FirewallaDeviceTracker(coordinator, device)
        for device in coordinator.data["devices"]
        if isinstance(device, dict) and "id" in device
    ]
    
    async_add_entities(entities)

class FirewallaDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Firewalla Device Tracker entity."""

    def __init__(self, coordinator, device):
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.device_id = device["id"]
        
        # --- FIX: HARD-CODE THE MAC AT BIRTH ---
        # Get the MAC immediately from the 'device' dict passed in during setup
        mac = device.get("mac", self.device_id)
        self._mac = mac[4:] if mac.startswith("mac:") else mac
        # ----------------------------------------

        self._attr_name = device.get("name", f"Firewalla Device {self.device_id}")
        
        box_id = "firewalla_hub"
        if coordinator.data.get("boxes"):
            box_id = coordinator.data["boxes"][0].get("id")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"box_{box_id}")},
            name="Firewalla Box",
            manufacturer="Firewalla",
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Force trackers to be enabled by default on fresh install."""
        return True
    
    @property
    def unique_id(self) -> str:
        """Return a unique ID for the tracker."""
        return f"{DOMAIN}_tracker_{self.device_id}"

    @property
    def source_type(self) -> SourceType:
        """Identify as a router-based tracker."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if Firewalla reports the device online."""
        return self._get_device_data().get("online", False)

    @property
    def ip_address(self) -> str:
        """Return the current IP."""
        return self._get_device_data().get("ip")

    @property
    def mac_address(self) -> str:
        """Return the pre-stored MAC address."""
        return self._mac

    def _get_device_data(self) -> dict:
        """Helper to find this device in the latest coordinator data."""
        devices = self.coordinator.data.get("devices", [])
        return next((d for d in devices if d.get("id") == self.device_id), {})

    @callback
    def _handle_coordinator_update(self) -> None:
        """Signal HA to refresh the tracker state."""
        self.async_write_ha_state()
