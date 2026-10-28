from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "assets" / "jarvis-reactor-logo.png"


def test_reactor_logo_asset_is_valid_png():
    data = LOGO.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", data[16:24]) == (192, 192)


def test_windows_exe_uses_generated_ico_and_bundles_logo_png():
    spec = (ROOT / "jarvis_desktop.spec").read_text(encoding="utf-8")
    build = (ROOT / "scripts" / "build_exe.ps1").read_text(encoding="utf-8")
    desktop = (ROOT / "jarvis_desktop.py").read_text(encoding="utf-8")
    assert 'icon="assets/jarvis-reactor-logo.ico"' in spec
    assert "Image.open('assets/jarvis-reactor-logo.png')" in build
    assert '("assets/jarvis-reactor-logo.png", "assets")' in spec
    assert "self.iconphoto(True, self._brand_image)" in desktop


def test_android_header_and_launcher_reference_the_same_brand_asset():
    pubspec = (ROOT / "ui" / "pubspec.yaml").read_text(encoding="utf-8")
    main = (ROOT / "ui" / "lib" / "main.dart").read_text(encoding="utf-8")
    manifest = (ROOT / "ui" / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "build-android.yml").read_text(encoding="utf-8")
    assert "assets/jarvis-reactor-logo.png" in pubspec
    assert "Image.asset('assets/jarvis-reactor-logo.png'" in main
    assert 'android:icon="@drawable/jarvis_reactor_logo"' in manifest
    assert 'android:roundIcon="@drawable/jarvis_reactor_logo"' in manifest
    assert "jarvis_reactor_logo.xml" in workflow
    assert (ROOT / "ui" / "assets" / "jarvis-reactor-logo.png").is_file()
    assert (ROOT / "ui" / "android" / "app" / "src" / "main" / "res" / "drawable" / "jarvis_reactor_logo.xml").is_file()
