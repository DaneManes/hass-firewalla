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
        
        # Link to the Box ID if available for the 'via_device' relationship
        box_id = None
        if coordinator.data.get("boxes"):
            box_id = coordinator.data["boxes"][0].get("id")

        # Identity Fix: Use identifiers={(DOMAIN, self.device_id)} 
        # to match your sensors exactly.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            via_device=(DOMAIN, f"box_{box_id}") if box_id else None,
            name=device.get("name", f"Firewalla Device {self.device_id}"),
            manufacturer="Firewalla",
            model="Network Device",
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
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
        devices = self.coordinator.data.get("devices", []) if self.coordinator.data else []
        return next((d for d in devices if d.get("id") == self.device_id), {})

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update state on coordinator refresh."""
        self.async_write_ha_state()
