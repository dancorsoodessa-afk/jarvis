from pathlib import Path
import py_compile


def test_desktop_ui_compiles():
    path = Path(__file__).resolve().parents[1] / "jarvis_desktop.py"
    py_compile.compile(str(path), doraise=True)
