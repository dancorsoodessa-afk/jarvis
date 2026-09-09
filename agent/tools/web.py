"""Web tools: DuckDuckGo instant answers + open-meteo weather.

Both work without API keys. Use only stdlib. Network failures raise
RuntimeError with a readable message (the agent turns them into text).
"""

import json
import urllib.parse
import urllib.request

USER_AGENT = "JarvisAgent/0.1"
TIMEOUT = 15


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — network layer, report as text
        raise RuntimeError(f"Сеть недоступна: {exc}") from exc


def web_search(query: str) -> str:
    """DuckDuckGo instant answer API: abstract + related topics."""
    query = " ".join(query.split())[:300]
    if not query:
        raise ValueError("Пустой поисковый запрос")
    data = _get_json(
        "https://api.duckduckgo.com/?"
        + urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1}))
    parts = []
    if data.get("AbstractText"):
        parts.append(data["AbstractText"])
        if data.get("AbstractURL"):
            parts.append(f"({data['AbstractURL']})")
    for topic in data.get("RelatedTopics", [])[:5]:
        text = topic.get("Text") if isinstance(topic, dict) else None
        if text:
            parts.append(f"• {text}")
    if not parts:
        # Instant answer API is limited; fall back to the HTML lite page.
        return _search_lite(query)
    return "\n".join(parts)


def _search_lite(query: str) -> str:
    req = urllib.request.Request(
        "https://lite.duckduckgo.com/lite/?"
        + urllib.parse.urlencode({"q": query}),
        headers={"User-Agent": USER_AGENT})
    try:
        html = urllib.request.urlopen(req, timeout=TIMEOUT).read().decode(
            "utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Поиск недоступен: {exc}") from exc
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text[:1500].strip() or "Ничего не найдено."


def weather(city: str) -> str:
    """Current weather via open-meteo geocoding + forecast (no key)."""
    city = " ".join(city.split())[:100]
    if not city:
        raise ValueError("Укажите город")
    geo = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urllib.parse.urlencode({"name": city, "count": 1, "language": "ru"}))
    results = geo.get("results") or []
    if not results:
        raise ValueError(f"Город не найден: {city}")
    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    data = _get_json(
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,wind_speed_10m,"
                       "relative_humidity_2m,weather_code",
        }))
    cur = data.get("current", {})
    codes = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность",
             3: "пасмурно", 45: "туман", 48: "изморозь",
             51: "морось", 53: "морось", 55: "сильная морось",
             61: "дождь", 63: "дождь", 65: "сильный дождь",
             71: "снег", 73: "снег", 75: "сильный снег",
             80: "ливни", 81: "ливни", 82: "сильные ливни",
             95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
    desc = codes.get(cur.get("weather_code"), "неизвестно")
    return (f"Погода в {place['name']}: {desc}, "
            f"{cur.get('temperature_2m')}°C "
            f"(ощущается {cur.get('apparent_temperature')}°C), "
            f"ветер {cur.get('wind_speed_10m')} км/ч, "
            f"влажность {cur.get('relative_humidity_2m')}%.")
