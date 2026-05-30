"""Data models for Gardena Smart System."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class GardenaLocation:
    """Represents a Gardena location."""
    
    id: str
    name: str
    devices: Dict[str, GardenaDevice] = None
    
    def __post_init__(self):
        if self.devices is None:
            self.devices = {}


@dataclass
class GardenaDevice:
    """Representation of a Gardena device."""
    id: str
    name: str
    model_type: str
    serial: str
    services: Dict[str, List[Any]]  # Changed from Dict[str, Any] to Dict[str, List[Any]]
    location_id: str
    
    def __post_init__(self):
        if self.services is None:
            self.services = {}


@dataclass
class GardenaService:
    """Base class for Gardena services."""
    
    id: str
    type: str
    device_id: str
    state: Optional[str] = None
    last_error_code: Optional[str] = None


@dataclass
class GardenaCommonService(GardenaService):
    """Common service properties shared across all devices."""
    
    name: Optional[str] = None
    battery_level: Optional[int] = None
    battery_state: Optional[str] = None
    rf_link_level: Optional[int] = None
    rf_link_state: Optional[str] = None
    model_type: Optional[str] = None
    serial: Optional[str] = None


@dataclass
class GardenaMowerService(GardenaService):
    """Mower service."""
    
    activity: Optional[str] = None
    operating_hours: Optional[int] = None


@dataclass
class GardenaPowerSocketService(GardenaService):
    """Power socket service."""
    
    activity: Optional[str] = None
    duration: Optional[int] = None


@dataclass
class GardenaValveService(GardenaService):
    """Valve service."""

    name: Optional[str] = None
    activity: Optional[str] = None
    duration: Optional[int] = None
    duration_timestamp: Optional[str] = None


@dataclass
class GardenaValveSetService(GardenaService):
    """Valve set service."""

    pass


@dataclass
class GardenaPumpBFFData:
    """Pump-specific telemetry fetched from the Gardena BFF API.

    All fields map 1-to-1 to ability properties returned by
    GET /v1/devices/{id}?locationId={lid}.
    """

    device_id: str
    # pump ability (type: "pressure_pump")
    pump_on_off: Optional[str] = None          # "on" / "off"
    pump_state: Optional[int] = None
    turn_on_pressure: Optional[float] = None   # Bar — Einschaltdruck
    mode: Optional[str] = None                 # "auto" / "manual"
    # outlet_pressure ability
    outlet_pressure: Optional[float] = None    # Bar — aktueller Betriebsdruck
    outlet_pressure_max: Optional[float] = None
    # flow ability
    flow_rate: Optional[float] = None          # l/h — aktuelle Durchflussrate
    flow_total: Optional[float] = None         # m³ — Gesamt-Fördermenge
    flow_since_last_reset: Optional[float] = None  # m³
    dripping_alert: Optional[str] = None       # Leckageerkennungs-Schwellwert
    # outlet_temperature ability
    temperature: Optional[float] = None        # °C — Auslasstemperatur
    frost_warning: Optional[str] = None        # "no_frost" / "frost"
    # settings
    leakage_detection: Optional[str] = None    # "watering" / …
    turn_on_pressure_setting_id: Optional[str] = None  # UUID for PUT /settings/{id}


@dataclass
class GardenaSensorService(GardenaService):
    """Sensor service."""
    
    soil_humidity: Optional[int] = None
    soil_temperature: Optional[float] = None
    ambient_temperature: Optional[float] = None
    light_intensity: Optional[int] = None


class GardenaDataParser:
    """Parser for Gardena API responses."""
    
    @staticmethod
    def parse_locations_response(data: Dict[str, Any]) -> List[GardenaLocation]:
        """Parse locations response from API."""
        locations = []
        
        for location_data in data.get("data", []):
            location = GardenaLocation(
                id=location_data["id"],
                name=location_data["attributes"]["name"]
            )
            locations.append(location)
        
        return locations
    
    @staticmethod
    def parse_location_response(data: Dict[str, Any]) -> GardenaLocation:
        """Parse location response with devices from API."""
        location_data = data["data"]
        location = GardenaLocation(
            id=location_data["id"],
            name=location_data["attributes"]["name"]
        )
        
        # Parse devices and services from included data
        devices = {}
        services = {}
        
        # First pass: create devices and collect service data
        for item in data.get("included", []):
            if item["type"] == "DEVICE":
                device = GardenaDevice(
                    id=item["id"],
                    name="",  # Will be filled from COMMON service
                    model_type="",  # Will be filled from COMMON service
                    serial="",  # Will be filled from COMMON service
                    services={},  # Will be filled with lists of services
                    location_id=location.id
                )
                devices[item["id"]] = device
            elif item["type"] in ["MOWER", "POWER_SOCKET", "VALVE", "VALVE_SET", "SENSOR", "COMMON"]:
                # Store service data for later processing
                service_type = item["type"]
                if service_type not in services:
                    services[service_type] = []
                services[service_type].append(item)
        
        # Second pass: associate services with devices
        for service_type, service_list in services.items():
            for service_data in service_list:
                relationships = service_data.get("relationships")
                if not relationships:
                    continue
                device_ref = relationships.get("device", {}).get("data", {})
                device_id = device_ref.get("id")
                if not device_id or device_id not in devices:
                    continue
                device = devices[device_id]
                if service_type not in device.services:
                    device.services[service_type] = []
                device.services[service_type].append(
                    GardenaDataParser._create_service(service_type, service_data)
                )

                # Update device info from COMMON service
                if service_type == "COMMON":
                    attrs = service_data.get("attributes", {})
                    device.name = attrs.get("name", {}).get("value", device.name)
                    device.model_type = attrs.get("modelType", {}).get("value", device.model_type)
                    device.serial = attrs.get("serial", {}).get("value", device.serial)
        
        location.devices = devices
        return location

    @staticmethod
    def _create_service(service_type: str, service_data: Dict[str, Any]) -> Any:
        """Create a service object based on the service type."""
        service_id = service_data["id"]
        device_id = service_data.get("relationships", {}).get("device", {}).get("data", {}).get("id", "")
        attrs = service_data.get("attributes", {})
        
        if service_type == "COMMON":
            return GardenaCommonService(
                id=service_id,
                type="COMMON",
                device_id=device_id,
                name=attrs.get("name", {}).get("value"),
                battery_level=attrs.get("batteryLevel", {}).get("value"),
                battery_state=attrs.get("batteryState", {}).get("value"),
                rf_link_level=attrs.get("rfLinkLevel", {}).get("value"),
                rf_link_state=attrs.get("rfLinkState", {}).get("value"),
                model_type=attrs.get("modelType", {}).get("value"),
                serial=attrs.get("serial", {}).get("value")
            )
        elif service_type == "MOWER":
            return GardenaMowerService(
                id=service_id,
                type="MOWER",
                device_id=device_id,
                state=attrs.get("state", {}).get("value"),
                activity=attrs.get("activity", {}).get("value"),
                operating_hours=attrs.get("operatingHours", {}).get("value"),
                last_error_code=attrs.get("lastErrorCode", {}).get("value")
            )
        elif service_type == "POWER_SOCKET":
            return GardenaPowerSocketService(
                id=service_id,
                type="POWER_SOCKET",
                device_id=device_id,
                state=attrs.get("state", {}).get("value"),
                activity=attrs.get("activity", {}).get("value"),
                duration=attrs.get("duration", {}).get("value"),
                last_error_code=attrs.get("lastErrorCode", {}).get("value")
            )
        elif service_type == "VALVE":
            return GardenaValveService(
                id=service_id,
                type="VALVE",
                device_id=device_id,
                name=attrs.get("name", {}).get("value"),
                state=attrs.get("state", {}).get("value"),
                activity=attrs.get("activity", {}).get("value"),
                duration=attrs.get("duration", {}).get("value"),
                duration_timestamp=attrs.get("duration", {}).get("timestamp"),
                last_error_code=attrs.get("lastErrorCode", {}).get("value")
            )
        elif service_type == "VALVE_SET":
            return GardenaValveSetService(
                id=service_id,
                type="VALVE_SET",
                device_id=device_id,
                state=attrs.get("state", {}).get("value"),
                last_error_code=attrs.get("lastErrorCode", {}).get("value")
            )
        elif service_type == "SENSOR":
            return GardenaSensorService(
                id=service_id,
                type="SENSOR",
                device_id=device_id,
                soil_humidity=attrs.get("soilHumidity", {}).get("value"),
                soil_temperature=attrs.get("soilTemperature", {}).get("value"),
                ambient_temperature=attrs.get("ambientTemperature", {}).get("value"),
                light_intensity=attrs.get("lightIntensity", {}).get("value")
            )
        else:
            # Fallback for unknown service types
            return GardenaService(
                id=service_id,
                type=service_type,
                device_id=device_id
            )

    @staticmethod
    def parse_bff_device(data: Dict[str, Any]) -> GardenaPumpBFFData:
        """Parse a GET /v1/devices/{id} BFF response into GardenaPumpBFFData."""
        device_data = data.get("devices", {})
        result = GardenaPumpBFFData(device_id=device_data.get("id", ""))

        for ability in device_data.get("abilities", []):
            ability_name = ability.get("name")
            # Build a flat name→value dict for this ability's properties
            props = {p["name"]: p.get("value") for p in ability.get("properties", [])}

            if ability_name == "pump":
                result.pump_on_off = props.get("pump_on_off")
                result.pump_state = props.get("pump_state")
                result.turn_on_pressure = props.get("turn_on_pressure")
                result.mode = props.get("mode")
            elif ability_name == "outlet_pressure":
                result.outlet_pressure = props.get("outlet_pressure")
                result.outlet_pressure_max = props.get("outlet_pressure_max")
            elif ability_name == "flow":
                result.flow_rate = props.get("flow_rate")
                result.flow_total = props.get("flow_total")
                result.flow_since_last_reset = props.get("flow_since_last_reset")
                result.dripping_alert = props.get("dripping_alert")
            elif ability_name == "outlet_temperature":
                result.temperature = props.get("temperature")
                result.frost_warning = props.get("frost_warning")

        for setting in device_data.get("settings", []):
            if setting.get("name") == "leakage_detection":
                result.leakage_detection = setting.get("value")
            elif setting.get("name") == "turn_on_pressure":
                result.turn_on_pressure_setting_id = setting.get("id")

        return result