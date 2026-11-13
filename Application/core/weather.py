import json
from urllib.parse import urlencode
from urllib.request import urlopen


def _get_json(url):
    with urlopen(url, timeout=10) as response:
        return json.load(response)


def fetch_current_weather(city, country, temperature_unit="Celsius"):
    city = city.strip()
    country = country.strip()
    if not city or not country:
        raise ValueError("Both a city and country are required to look up weather.")

    geocoding_url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode({
        "name": city,
        "count": 10,
        "language": "en",
        "format": "json",
    })
    locations = _get_json(geocoding_url).get("results", [])
    location = next(
        (
            result for result in locations
            if result.get("country", "").casefold() == country.casefold()
        ),
        None,
    )
    if location is None:
        raise ValueError(f"Could not find {city} in {country}. Check the location in General settings.")

    use_fahrenheit = temperature_unit == "Fahrenheit"
    forecast_url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code",
        "temperature_unit": "fahrenheit" if use_fahrenheit else "celsius",
        "timezone": "auto",
    })
    current = _get_json(forecast_url).get("current")
    if not current or "temperature_2m" not in current or "weather_code" not in current:
        raise ValueError("The weather service returned no current conditions.")

    code = current["weather_code"]
    conditions = {
        0: ("☀", "Clear"),
        1: ("🌤", "Mainly clear"),
        2: ("⛅", "Partly cloudy"),
        3: ("☁", "Overcast"),
        45: ("🌫", "Fog"),
        48: ("🌫", "Rime fog"),
        51: ("🌦", "Light drizzle"),
        53: ("🌦", "Drizzle"),
        55: ("🌧", "Heavy drizzle"),
        56: ("🌧", "Freezing drizzle"),
        57: ("🌧", "Heavy freezing drizzle"),
        61: ("🌧", "Light rain"),
        63: ("🌧", "Rain"),
        65: ("🌧", "Heavy rain"),
        66: ("🌧", "Freezing rain"),
        67: ("🌧", "Heavy freezing rain"),
        71: ("🌨", "Light snow"),
        73: ("🌨", "Snow"),
        75: ("❄", "Heavy snow"),
        77: ("🌨", "Snow grains"),
        80: ("🌦", "Light rain showers"),
        81: ("🌧", "Rain showers"),
        82: ("🌧", "Heavy rain showers"),
        85: ("🌨", "Snow showers"),
        86: ("🌨", "Heavy snow showers"),
        95: ("⛈", "Thunderstorm"),
        96: ("⛈", "Thunderstorm with hail"),
        99: ("⛈", "Heavy thunderstorm with hail"),
    }
    icon, description = conditions.get(code, ("", "Current conditions"))
    unit_symbol = "°F" if use_fahrenheit else "°C"
    return {
        "city": location.get("name", city),
        "country": location.get("country", country),
        "temperature": round(current["temperature_2m"]),
        "feels_like": round(current["apparent_temperature"])
        if "apparent_temperature" in current else None,
        "unit": unit_symbol,
        "icon": icon,
        "description": description,
    }
