import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools import web


def _fake_urlopen(payload):
    if isinstance(payload, bytes):
        body = payload
    elif isinstance(payload, str):
        body = payload.encode()
    else:
        body = json.dumps(payload).encode()
    ctx = mock.MagicMock()
    ctx.read.return_value = body
    cm = mock.MagicMock()
    cm.__enter__ = mock.MagicMock(return_value=ctx)
    cm.__exit__ = mock.MagicMock(return_value=False)
    return cm


class TestWeather(unittest.TestCase):
    def test_weather_formats_reply(self):
        geo = {"results": [{"name": "Москва", "latitude": 55.75, "longitude": 37.62}]}
        forecast = {"current": {"temperature_2m": 20, "apparent_temperature": 19,
                                "wind_speed_10m": 3.5, "relative_humidity_2m": 40,
                                "weather_code": 0}}
        with mock.patch("urllib.request.urlopen",
                        side_effect=[_fake_urlopen(geo), _fake_urlopen(forecast)]):
            out = web.weather("Москва")
        self.assertIn("Москва", out)
        self.assertIn("20", out)
        self.assertIn("ясно", out)

    def test_unknown_city_raises(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_fake_urlopen({"results": []})):
            with self.assertRaises(ValueError):
                web.weather("НеСуществует12345")

    def test_empty_city_raises(self):
        with self.assertRaises(ValueError):
            web.weather("   ")


class TestWebSearch(unittest.TestCase):
    def test_parses_google_results(self):
        page = ('<html><body>'
                '<a href="/url?q=https://ru.wikipedia.org/wiki/Python&amp;sa=x">'
                'Python \u2014 \u044f\u0437\u044b\u043a \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f</a>'
                '</body></html>')
        with mock.patch("urllib.request.urlopen", return_value=_fake_urlopen(page)):
            out = web.web_search("python")
        self.assertIn("язык программирования", out)
        self.assertIn("https://ru.wikipedia.org/wiki/Python", out)

    def test_fallback_when_markup_unknown(self):
        with mock.patch("urllib.request.urlopen", return_value=_fake_urlopen("<html></html>")):
            out = web.web_search("python")
        self.assertIn("Результаты поиска для «python»", out)

    def test_empty_query_raises(self):
        with self.assertRaises(ValueError):
            web.web_search("  ")

    def test_network_error_is_runtime(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=OSError("no network")):
            with self.assertRaises(RuntimeError):
                web.web_search("тест")


class TestWebRegistered(unittest.TestCase):
    def test_tools_in_runtime(self):
        from agent.runtime import build_agent
        agent = build_agent()
        for name in ("web_search", "weather"):
            self.assertIn(name, agent.tools.names())
        spec = agent.tools.spec("weather")
        self.assertIn("city", spec["function"]["parameters"]["properties"])


if __name__ == "__main__":
    unittest.main()
