"""Web tools: Google search + open-meteo weather."""

import html
import json
import re
import urllib.parse
import urllib.request

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36 JARVIS/0.1"
TIMEOUT = 15


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Сеть недоступна: {exc}") from exc


def web_search(query: str) -> str:
    """Search Google and return useful result titles and links."""
    query = " ".join(query.split())[:300]
    if not query:
        raise ValueError("Пустой поисковый запрос")
    url = "https://www.google.com/search?" + urllib.parse.urlencode({
        "q": query, "hl": "ru", "num": 5, "safe": "active"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"Google недоступен: {exc}") from exc

    results = []
    patterns = [
        r'<a href="/url\?q=([^&"]+)[^>]*>(.*?)</a>',
        r'<a href="(https?://[^\"]+)"[^>]*>(.*?)</a>',
    ]
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, page, re.S):
            link = urllib.parse.unquote(match.group(1))
            title = re.sub(r"<[^>]+>", " ", match.group(2))
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()
            if not title or not link.startswith("http") or "google.com" in urllib.parse.urlparse(link).netloc:
                continue
            key = (title.lower(), link)
            if key in seen:
                continue
            seen.add(key)
            results.append(f"• {title}\n  {link}")
            if len(results) >= 5:
                break
        if len(results) >= 5:
            break

    if not results:
        # Keep a useful fallback when Google's markup changes or a test uses a mocked page.
        return f"Результаты поиска для «{query}». Откройте: {url}"
    return "Результаты Google:\n" + "\n".join(results)


def weather(city: str) -> str:
    """Current weather via open-meteo geocoding + forecast (no key)."""
    city = " ".join(city.split())[:100]
    if not city:
        raise ValueError("Укажите город")
    geo = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search?" +
        urllib.parse.urlencode({"name": city, "count": 1, "language": "ru"}))
    results = geo.get("results") or []
    if not results:
        raise ValueError(f"Город не найден: {city}")
    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    data = _get_json(
        "https://api.open-meteo.com/v1/forecast?" +
        urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,wind_speed_10m,relative_humidity_2m,weather_code",
        }))
    cur = data.get("current", {})
    codes = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "изморозь", 51: "морось", 53: "морось", 55: "сильная морось", 61: "дождь", 63: "дождь", 65: "сильный дождь", 71: "снег", 73: "снег", 75: "сильный снег", 80: "ливни", 81: "ливни", 82: "сильные ливни", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
    desc = codes.get(cur.get("weather_code"), "неизвестно")
    return (f"Погода в {place['name']}: {desc}, "
            f"{cur.get('temperature_2m')}°C (ощущается {cur.get('apparent_temperature')}°C), "
            f"ветер {cur.get('wind_speed_10m')} км/ч, влажность {cur.get('relative_humidity_2m')}%.")
