"""Device tracker platform for Firewalla."""
import logging
from homeassistant.components.device_tracker import SourceType, ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COORDINATOR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up Firewalla device trackers."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get(COORDINATOR)
    if not coordinator or "devices" not in coordinator.data:
        return

    entities = []
    for device in coordinator.data["devices"]:
        if isinstance(device, dict) and "id" in device:
            entities.append(FirewallaDeviceTracker(coordinator, device))
    
    async_add_entities(entities)

class FirewallaDeviceTracker(CoordinatorEntity, ScannerEntity):
    """Firewalla Device Tracker entity."""

    def __init__(self, coordinator, device):
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.device_id = device["id"]
        self._attr_name = device.get("name", f"Firewalla Device {self.device_id}")
        
        # Get the Box ID from the coordinator data
        # We use a fallback 'firewalla_hub' if the boxes list is missing
        box_id = "firewalla_hub"
        if coordinator.data.get("boxes"):
            box_id = coordinator.data["boxes"][0].get("id")

        # This DeviceInfo block must be IDENTICAL for all entities 
        # you want grouped into one single Device card.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"box_{box_id}")},
            name="Firewalla Box",
            manufacturer="Firewalla",
            model="Firewalla Purple", # Optional: can pull from API
            configuration_url="https://my.firewalla.com",
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID to enable UI management."""
        return f"{DOMAIN}_tracker_{self.device_id}"

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.ROUTER

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the network."""
        device = self._get_device_data()
        return device.get("online", False)

    @property
    def ip_address(self) -> str:
        """Return the primary IP address."""
        device = self._get_device_data()
        return device.get("ip")

    @property
    def mac_address(self) -> str:
        """Return the MAC address."""
        device = self._get_device_data()
        return device.get("mac")

    def _get_device_data(self) -> dict:
        """Helper to find this device in the latest coordinator data."""
        devices = self.coordinator.data.get("devices", [])
        return next((d for d in devices if d.get("id") == self.device_id), {})

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state on coordinator refresh."""
        # This signals the UI to re-read the properties (is_connected, etc)
        self.async_write_ha_state()
