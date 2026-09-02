"""Sensor platform for the Sagemcom F@st 5866T 5G Modem integration."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfTime,
    UnitOfInformation,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def safe_get(data, path, default=None):
    """Safely travel down highly nested list/dict structures from the Sagemcom API."""
    current = data
    for key in path:
        if isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return default
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return default
            
        if current is None:
            return default
            
    return current


# ==========================================
# SENSOR DEFINITIONS
# ==========================================

SENSOR_TYPES = (
    # --- CORE SYSTEM INFO ---
    {"key": "model_name", "name": "Model Name", "path": ["device", 0, "device", "modelname"], "icon": "mdi:router"},
    {"key": "software_version", "name": "Firmware Version", "path": ["device", 0, "device", "main", "version"], "icon": "mdi:package-up"},
    {"key": "uptime", "name": "System Uptime (s)", "path": ["device", 0, "device", "uptime"], "device_class": SensorDeviceClass.DURATION, "native_unit_of_measurement": UnitOfTime.SECONDS, "state_class": SensorStateClass.TOTAL_INCREASING},
    {"key": "uptime_formatted", "name": "System Uptime", "path": ["device", 0, "device", "uptime"], "icon": "mdi:clock-check-outline"},
    {"key": "boot_count", "name": "Boot Counter", "path": ["device", 0, "device", "numberofboots"], "state_class": SensorStateClass.TOTAL_INCREASING, "icon": "mdi:counter"},
    
    # --- WAN & NETWORK IDENTIFIERS ---
    {"key": "wan_status", "name": "WAN Link Status", "path": ["wan", "status"], "icon": "mdi:wan"},
    {"key": "network_type", "name": "Cellular Generation", "path": ["network_type", "cellular", "network_type"], "icon": "mdi:signal-cellular-5g"},
    {"key": "provider", "name": "Network Carrier", "path": ["provider", "cellular", "provider"], "icon": "mdi:antenna"},
    {"key": "sim_status", "name": "SIM Status", "path": ["sim_status", 0, "cellular", "sim_status_extended"], "icon": "mdi:sim"},
    
    # --- NETWORK CLIENT COUNTERS ---
    {"key": "clients_ethernet", "name": "Active Ethernet Clients", "path": ["hosts", 0, "hosts", "list"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:lan-connect"},
    {"key": "clients_wifi", "name": "Active Wi-Fi Clients", "path": ["hosts", 0, "hosts", "list"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:wifi-star"},
    
    # --- CELLULAR DATA TRAFFIC METERING ---
    {"key": "session_duration", "name": "Cellular Session Duration", "path": ["session", 0, "cellular", "session", "duration"], "device_class": SensorDeviceClass.DURATION, "native_unit_of_measurement": UnitOfTime.HOURS, "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:clock-outline"},
    {"key": "bytes_received", "name": "Mobile Data Downloaded", "path": ["session", 0, "cellular", "session", "data", "received"], "device_class": SensorDeviceClass.DATA_SIZE, "native_unit_of_measurement": UnitOfInformation.BYTES, "state_class": SensorStateClass.TOTAL_INCREASING, "icon": "mdi:download"},
    {"key": "data_received_gb", "name": "Data Received", "path": ["session", 0, "cellular", "session", "data", "received"], "device_class": SensorDeviceClass.DATA_SIZE, "native_unit_of_measurement": UnitOfInformation.GIGABYTES, "state_class": SensorStateClass.TOTAL_INCREASING, "icon": "mdi:download-network"},
    {"key": "bytes_sent", "name": "Mobile Data Uploaded", "path": ["session", 0, "cellular", "session", "data", "sent"], "device_class": SensorDeviceClass.DATA_SIZE, "native_unit_of_measurement": UnitOfInformation.BYTES, "state_class": SensorStateClass.TOTAL_INCREASING, "icon": "mdi:upload"},
    {"key": "data_sent_gb", "name": "Data Sent", "path": ["session", 0, "cellular", "session", "data", "sent"], "device_class": SensorDeviceClass.DATA_SIZE, "native_unit_of_measurement": UnitOfInformation.GIGABYTES, "state_class": SensorStateClass.TOTAL_INCREASING, "icon": "mdi:upload-network"},
    
    # --- 4G LTE TELEMETRY ---
    {"key": "4g_rsrp", "name": "4G Signal Strength (RSRP)", "path": ["interface_4g", 0, "cellular", "interfaces", 0, "rsrp"], "device_class": SensorDeviceClass.SIGNAL_STRENGTH, "native_unit_of_measurement": SIGNAL_STRENGTH_DECIBELS_MILLIWATT, "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-3"},
    {"key": "4g_rsrq", "name": "4G Signal Quality (RSRQ)", "path": ["interface_4g", 0, "cellular", "interfaces", 0, "rsrq"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-outline"},
    {"key": "4g_sinr", "name": "4G Signal:Noise Ratio (SINR)", "path": ["interface_4g", 0, "cellular", "interfaces", 0, "connect_info", "sinr"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-outline"},
    
    # --- 5G TELEMETRY ---
    {"key": "5g_rsrp", "name": "5G Signal Strength (RSRP)", "path": ["interface_5g", 0, "cellular", "interfaces", 0, "rsrp"], "device_class": SensorDeviceClass.SIGNAL_STRENGTH, "native_unit_of_measurement": SIGNAL_STRENGTH_DECIBELS_MILLIWATT, "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-3"},
    {"key": "5g_rsrq", "name": "5G Signal Quality (RSRQ)", "path": ["interface_5g", 0, "cellular", "interfaces", 0, "rsrq"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-outline"},
    {"key": "5g_sinr", "name": "5G Signal:Noise Ratio (SINR)", "path": ["interface_5g", 0, "cellular", "interfaces", 0, "connect_info", "sinr"], "state_class": SensorStateClass.MEASUREMENT, "icon": "mdi:signal-cellular-outline"},
    {"key": "5g_band", "name": "5G Band", "path": ["interface_5g", 0, "cellular", "interfaces", 0, "bandinfo"], "icon": "mdi:radio-tower"},
)

PORT_METRIC_DEFINITIONS = [
    {"key": "status", "suffix": "Connection Status", "icon": "mdi:ethernet-cable"},
    {"key": "curbitrate", "suffix": "Link Speed", "icon": "mdi:speedometer", "unit": "Mbps"},
    {"dir": "tx", "key": "packets", "suffix": "Packets Sent", "icon": "mdi:upload", "unit": "packets"},
    {"dir": "rx", "key": "packets", "suffix": "Packets Received", "icon": "mdi:download", "unit": "packets"},
    {"dir": "tx", "key": "bytes", "suffix": "Bytes Sent", "icon": "mdi:upload", "class": SensorDeviceClass.DATA_SIZE, "unit": UnitOfInformation.BYTES},
    {"dir": "rx", "key": "bytes", "suffix": "Bytes Received", "icon": "mdi:download", "class": SensorDeviceClass.DATA_SIZE, "unit": UnitOfInformation.BYTES},
    {"dir": "tx", "key": "packetserrors", "suffix": "Errors Sent", "icon": "mdi:alert-outline", "unit": "errors"},
    {"dir": "rx", "key": "packetserrors", "suffix": "Errors Received", "icon": "mdi:alert-outline", "unit": "errors"},
    {"dir": "tx", "key": "packetsdiscards", "suffix": "Discarded Packets Sent", "icon": "mdi:delete-empty", "unit": "packets"},
    {"dir": "rx", "key": "packetsdiscards", "suffix": "Discarded Packets Received", "icon": "mdi:delete-empty", "unit": "packets"},
    {"dir": "tx", "key": "unicastpackets", "suffix": "Unicast Packets Sent", "icon": "mdi:arrow-up-bold", "unit": "packets"},
    {"dir": "rx", "key": "unicastpackets", "suffix": "Unicast Packets Received", "icon": "mdi:arrow-down-bold", "unit": "packets"},
    {"dir": "tx", "key": "multicastpackets", "suffix": "Multicast Packets Sent", "icon": "mdi:groups", "unit": "packets"},
    {"dir": "rx", "key": "multicastpackets", "suffix": "Multicast Packets Received", "icon": "mdi:groups", "unit": "packets"},
    {"dir": "tx", "key": "broadcastpackets", "suffix": "Broadcast Packets Sent", "icon": "mdi:bullhorn-variant", "unit": "packets"},
    {"dir": "rx", "key": "broadcastpackets", "suffix": "Broadcast Packets Received", "icon": "mdi:bullhorn-variant", "unit": "packets"},
]

WIFI_PRIMARY_DEFS = [
    {"key": "ssid", "name": "SSID Name", "icon": "mdi:wifi-marker", "path_end": ["wireless", "ssid", "#BAND#", "id"]},
    {"key": "passphrase", "name": "Passphrase", "icon": "mdi:key-variant", "path_end": ["wireless", "ssid", "#BAND#", "security", "passphrase"]},
    {"key": "security", "name": "Security Type", "icon": "mdi:shield-lock-outline", "path_end": ["wireless", "ssid", "#BAND#", "security", "protocol"]},
    {"key": "status", "name": "Status", "icon": "mdi:check-circle-outline", "path_end": ["wireless", "ssid", "#BAND#", "ssid_status"]},
    {"key": "channel", "name": "Current Channel", "icon": "mdi:ray-start-arrow", "path_end": ["wireless", "radio", "channel"]},
    {"key": "bandwidth", "name": "Bandwidth", "icon": "mdi:arrow-expand-horizontal", "path_end": ["wireless", "radio", "curr_oper_chan_bw"]},
    {"key": "standard", "name": "Wireless Mode", "icon": "mdi:wifi-cog", "path_end": ["wireless", "radio", "standard"]},
]

WIFI_GUEST_DEFS = [
    {"key": "ssid", "name": "SSID Name", "icon": "mdi:wifi-marker", "path_end": ["guest#BAND#", "ssid"]},
    {"key": "passphrase", "name": "Passphrase", "icon": "mdi:key-variant", "path_end": ["guest#BAND#", "passphrase"]},
    {"key": "security", "name": "Security Type", "icon": "mdi:shield-lock-outline", "path_end": ["guest#BAND#", "security"]},
    {"key": "status", "name": "Status", "icon": "mdi:check-circle-outline", "path_end": ["guest#BAND#", "ssid_status"]},
]


# ==========================================
# SETUP PLATFORM
# ==========================================

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up platform entities based on parsed layout descriptors."""
    domain_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = domain_data["coordinator"]
    host = domain_data["host"]
    
    # Retrieve both preferences from the config entry options (defaulting to False)
    expose_main = entry.options.get("expose_main_wifi_passphrase", False)
    expose_guest = entry.options.get("expose_guest_wifi_passphrase", False)
    
    entities = []

    # 1. Spawn Core Router Sensors
    for description in SENSOR_TYPES:
        entities.append(SagemcomRouterSensor(coordinator, description, entry.entry_id, host))

    # 2. Spawn ETH0, ETH1, ETH2
    if coordinator.data and "lan_stats" in coordinator.data:
        interfaces = safe_get(coordinator.data, ["lan_stats", 0, "lan", "interfaces"], [])
        for idx, iface in enumerate(interfaces):
            port_label = iface.get("name", f"eth{idx}")
            for metric in PORT_METRIC_DEFINITIONS:
                entities.append(SagemcomEthernetPortSensor(coordinator, entry.entry_id, host, idx, port_label, metric))

    # 3. Add Primary and Guest Wifi Networks
    networks_map = [
        {
            "device_id": "primary", 
            "name": "Primary Wi-Fi Network", 
            "defs": WIFI_PRIMARY_DEFS,
            "bands": [("wifi_24", "24", "2.4GHz"), ("wifi_5", "5", "5GHz")]
        },
        {
            "device_id": "guest", 
            "name": "Guest Wi-Fi Network", 
            "defs": WIFI_GUEST_DEFS,
            "bands": [("wifi_guest24", "24", "2.4GHz"), ("wifi_guest5", "5", "5GHz")]
        }
    ]

    for net in networks_map:
        # Determine which toggle applies to the current network group
        expose_passphrase = expose_main if net["device_id"] == "primary" else expose_guest

        for coord_key, band_id, label in net["bands"]:
            for definition in net["defs"]:
                # Gate the passphrase sensors behind the relevant configuration option
                if definition["key"] == "passphrase" and not expose_passphrase:
                    continue
                entities.append(SagemcomWiFiSensor(coordinator, entry.entry_id, net["device_id"], net["name"], coord_key, band_id, label, definition))

    # 4. Spawn Connected Clients
    if coordinator.data and "hosts" in coordinator.data:
        clients = safe_get(coordinator.data, ["hosts", 0, "hosts", "list"], [])
        for client in clients:
            mac = client.get("macaddress")
            if not mac or mac == "unknown": 
                continue
                
            hostname = client.get("hostname") or f"Device-{mac[-5:].replace(':', '')}"
            
            entities.append(SagemcomClientSensor(coordinator, entry.entry_id, mac, hostname, "status", "Connection Status", "mdi:lan-pending"))
            entities.append(SagemcomClientSensor(coordinator, entry.entry_id, mac, hostname, "ipaddress", "IP Address", "mdi:ip"))
            entities.append(SagemcomClientSensor(coordinator, entry.entry_id, mac, hostname, "macaddress", "MAC Address", "mdi:network-outline"))
            
            if client.get("link") == "Ethernet":
                entities.append(SagemcomClientSensor(coordinator, entry.entry_id, mac, hostname, "speed", "Link Speed", "mdi:speedometer", "Mbps"))
            else:
                entities.append(SagemcomClientSensor(coordinator, entry.entry_id, mac, hostname, "rssi", "Signal Strength", "mdi:wifi", "dBm"))

    async_add_entities(entities)


# ==========================================
# ENTITY CLASSES
# ==========================================

class SagemcomRouterSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, description, entry_id, host):
        super().__init__(coordinator)
        self._description = description
        self._attr_unique_id = f"sagemcom_{host}_{description['key']}"
        self._attr_name = f"{description['name']}"
        self._attr_device_class = description.get("device_class")
        self._attr_native_unit_of_measurement = description.get("native_unit_of_measurement")
        self._attr_state_class = description.get("state_class")
        self._attr_icon = description.get("icon")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)}, 
            "name": "Sagemcom F@st 5866T 5G Modem", 
            "manufacturer": "Sagemcom", 
            "model": "F@st 5866T", 
            "configuration_url": f"http://{host}"
        }

    @property
    def native_value(self):
        if not self.coordinator.data: 
            return None
            
        raw_val = safe_get(self.coordinator.data, self._description["path"])
            
        if self._description["key"] == "clients_ethernet" and isinstance(raw_val, list):
            return sum(1 for c in raw_val if c.get("active") and c.get("link") == "Ethernet")
            
        if self._description["key"] == "clients_wifi" and isinstance(raw_val, list):
            return sum(1 for c in raw_val if c.get("active") and c.get("link") != "Ethernet")
            
        if raw_val is None or raw_val == "": 
            return None
            
        if self._description["key"] == "uptime_formatted":
            seconds = int(raw_val)
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            return f"{h}h {m}m {s}s"
            
        if self._description["key"] in ["data_received_gb", "data_sent_gb"]:
            return round(int(raw_val) / (1024 ** 3), 2)
            
        if self._description["key"] == "session_duration":
            return round(int(raw_val) / 3600, 2)
            
        if self._attr_device_class in [SensorDeviceClass.DATA_SIZE, SensorDeviceClass.SIGNAL_STRENGTH, SensorDeviceClass.DURATION]:
            return int(raw_val)
            
        return raw_val


class SagemcomEthernetPortSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id, host, index, port_name, metric_def):
        super().__init__(coordinator)
        self._index = index
        self._port_name = port_name
        self._metric_key = metric_def["key"]
        self._metric_def = metric_def
        dir_key = metric_def.get("dir", "")
        uid_suffix = f"{dir_key}_{self._metric_key}" if dir_key else self._metric_key
        self._attr_unique_id = f"sagemcom_{host}_lan_{port_name}_{uid_suffix}"
        self._attr_name = f"LAN Port {port_name.upper()} {metric_def['suffix']}"
        self._attr_icon = metric_def["icon"]
        if "class" in metric_def: 
            self._attr_device_class = metric_def["class"]
        if "unit" in metric_def: 
            self._attr_native_unit_of_measurement = metric_def["unit"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_lan_{port_name}")},
            name=f"LAN Port {port_name.upper()}",
            manufacturer="Sagemcom Interface",
            via_device=(DOMAIN, entry_id)
        )

    @property
    def native_value(self):
        if not self.coordinator.data: 
            return None
            
        base_path = ["lan_stats", 0, "lan", "interfaces", self._index]
        status_val = safe_get(self.coordinator.data, base_path + ["status"])
        
        # 1. Connection Status text output
        if self._metric_key == "status":
            return "Connected" if status_val == "Up" else "Disconnected"
            
        # 2. Prevent numerical graphs from crashing when unplugged
        if status_val != "Up":
            return None
            
        if self._metric_key == "curbitrate":
            speed = safe_get(self.coordinator.data, base_path + ["curbitrate"])
            return int(speed) if speed else 0
            
        dir_key = self._metric_def.get("dir")
        if dir_key:
            val = safe_get(self.coordinator.data, base_path + [dir_key, self._metric_key])
            if val is not None and str(val).strip() != "": 
                return abs(int(val))
                
        return 0


class SagemcomWiFiSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id, device_id, device_name, coord_key, band_id, band_label, definition):
        super().__init__(coordinator)
        self._coord_key = coord_key
        self._definition = definition
        self._band_id = band_id
        self._clean_path = [coord_key, 0] + [p.replace("#BAND#", str(band_id)) for p in definition["path_end"]]
        self._attr_unique_id = f"sagemcom_{entry_id}_wifi_{device_id}_{band_label}_{definition['key']}"
        self._attr_name = f"{band_label} {definition['name']}"
        self._attr_icon = definition["icon"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_wifi_{device_id}")}, 
            name=device_name, 
            manufacturer="Sagemcom Network", 
            via_device=(DOMAIN, entry_id)
        )
        
        # Set passphrase sensors to be disabled by default in the entity registry
        if definition["key"] == "passphrase":
            self._attr_entity_registry_enabled_default = False
            
    @property
    def native_value(self):
        if not self.coordinator.data: 
            return None
            
        val = safe_get(self.coordinator.data, self._clean_path)
        
        if val is True or str(val).lower() == "true": 
            return "Enabled"
        if val is False or str(val).lower() == "false": 
            return "Disabled"
            
        return val


class SagemcomClientSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id, mac, hostname, metric_key, metric_name, icon, unit=None):
        super().__init__(coordinator)
        self._mac = mac
        self._metric_key = metric_key
        self._attr_unique_id = f"sagemcom_client_{mac}_{metric_key}"
        self._attr_name = metric_name
        self._attr_icon = icon
        if unit:
            self._attr_native_unit_of_measurement = unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))},
            name=hostname,
            manufacturer="Network Client",
            via_device=(DOMAIN, entry_id)
        )

    @property
    def native_value(self):
        if not self.coordinator.data: 
            return None
            
        clients = safe_get(self.coordinator.data, ["hosts", 0, "hosts", "list"], [])
        
        for client in clients:
            if client.get("macaddress") == self._mac:
                if self._metric_key == "status":
                    return "Connected" if client.get("active") else "Disconnected"
                    
                if not client.get("active"):
                    return None
                    
                if self._metric_key == "ipaddress":
                    return client.get("ipaddress")
                if self._metric_key == "macaddress":
                    return self._mac
                if self._metric_key == "speed":
                    return safe_get(client, ["ethernet", "speed"]) or 0
                if self._metric_key == "rssi":
                    rssi_val = safe_get(client, ["wireless", "rssi0"]) or client.get("rssi")
                    return int(rssi_val) if rssi_val else 0
                    
        return "Disconnected" if self._metric_key == "status" else None
