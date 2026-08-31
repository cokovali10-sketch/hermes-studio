"""
Hermes Plugin Example — Weather Tool

This plugin adds a weather lookup tool to Hermes.
Drop this file in plugins/ and reload.

Format:
  HERMES_TOOLS: list of dicts with keys: name, function, schema
  HERMES_INIT: optional init function
"""

import json
import urllib.request
import urllib.error


async def tool_get_weather(city: str = "Moscow") -> dict:
    """Get weather for a city using wttr.in (free, no API key)."""
    try:
        url = f"https://wttr.in/{city}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes/4.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current_condition", [{}])[0]
        return {
            "success": True,
            "city": city,
            "temp_c": current.get("temp_C", "?"),
            "feels_like_c": current.get("FeelsLikeC", "?"),
            "weather": current.get("weatherDesc", [{}])[0].get("value", "?"),
            "humidity": current.get("humidity", "?"),
            "wind_kmph": current.get("windspeedKmph", "?"),
            "visibility_km": current.get("visibility", "?"),
        }
    except Exception as e:
        return {"error": str(e), "success": False}


HERMES_TOOLS = [
    {
        "name": "get_weather",
        "function": tool_get_weather,
        "schema": {
            "description": "Get current weather for a city. Uses wttr.in (free, no API key needed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "default": "Moscow",
                        "description": "City name (e.g. 'Moscow', 'New York', 'Tokyo')"
                    }
                },
                "required": []
            }
        }
    }
]


def HERMES_INIT():
    print("  [Weather Plugin] Loaded. Use get_weather(city='...') to check weather.")
