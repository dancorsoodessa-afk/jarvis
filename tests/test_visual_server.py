import json
from pathlib import Path
from urllib.request import urlopen

from agent.visual_server import _scene_file, start_visual_server


def test_three_js_scene_is_present_and_bundled_by_pyinstaller():
    scene = _scene_file()
    assert scene.is_file(), f"3D scene asset is missing: {scene}"
    spec = Path(__file__).resolve().parents[1] / "jarvis_desktop.spec"
    spec_text = spec.read_text(encoding="utf-8")
    assert '"ui/jarvis_3d.html", "ui"' in spec_text, "PyInstaller must bundle the 3D scene under ui/"


def test_visual_server_serves_scene_and_live_state():
    server, url = start_visual_server(lambda: {"state": "THINKING", "level": 0.7})
    try:
        with urlopen(url, timeout=3) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "NEURAL REACTOR" in html
            assert "three.module.js" in html
        with urlopen(url + "state", timeout=3) as response:
            state = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert state == {"state": "THINKING", "level": 0.7}
    finally:
        server.shutdown()
        server.server_close()
