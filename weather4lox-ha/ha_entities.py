"""Publish normalized Weather4Lox values to Home Assistant via MQTT discovery.

Home Assistant does not expose a public API for an add-on to register arbitrary
native entities directly. MQTT discovery is therefore optional: when the MQTT
integration is available, this module creates durable HA sensor entities from
the same normalized cache used by Loxone. Loxone operation never depends on
MQTT being installed.
"""
import json
import logging

log = logging.getLogger("weather4lox-ha.entities")

SENSORS = {
    "temperature": ("Temperature", "°C", "temperature"),
    "feels_like": ("Feels like", "°C", "temperature"),
    "humidity": ("Humidity", "%", "humidity"),
    "pressure": ("Pressure", "hPa", "pressure"),
    "wind_speed": ("Wind speed", "km/h", "speed"),
    "wind_gust": ("Wind gust", "km/h", "speed"),
    "wind_direction": ("Wind direction", "°", "direction"),
    "clouds": ("Cloud coverage", "%", "clouds"),
    "precipitation": ("Precipitation", "mm", "precipitation"),
    "precipitation_probability": ("Precipitation probability", "%", "precipitation"),
    "radiation": ("Radiation", "W/m²", "irradiance"),
    "cape": ("CAPE", "J/kg", "energy"),
}


def _topic(options, key):
    prefix = options.get("mqtt_discovery_prefix", "homeassistant").strip("/")
    base = "weather4lox"
    object_id = f"weather4lox_{key}"
    return f"{prefix}/sensor/{base}/{key}/config", f"weather4lox/{key}/state", object_id


def publish(mqtt_publish, options, values, diagnostics):
    """Publish MQTT discovery configs and states.

    mqtt_publish is a small callback supplied by the app so this module has no
    MQTT implementation dependency. Returns False if publishing is disabled.
    """
    if not options.get("mqtt_entities", False):
        return False
    device = {
        "identifiers": ["weather4lox-ha"],
        "name": "Weather4Lox HA",
        "manufacturer": "Weather4Lox HA",
        "model": "Loxone Gen 1 Weather Service emulator",
    }
    for key, (name, unit, device_class) in SENSORS.items():
        config_topic, state_topic, object_id = _topic(options, key)
        config = {
            "name": name,
            "unique_id": object_id,
            "state_topic": state_topic,
            "unit_of_measurement": unit,
            "device_class": device_class,
            "state_class": "measurement",
            "device": device,
        }
        mqtt_publish(config_topic, json.dumps(config), retain=True)
        value = values.get(key)
        if value is not None:
            mqtt_publish(state_topic, str(value), retain=True)

    status_topic = _topic(options, "status")[1]
    mqtt_publish(
        _topic(options, "status")[0],
        json.dumps({
            "name": "Status",
            "unique_id": "weather4lox_status",
            "state_topic": status_topic,
            "device": device,
        }),
        retain=True,
    )
    mqtt_publish(status_topic, diagnostics.get("status", "unknown"), retain=True)
    return True
