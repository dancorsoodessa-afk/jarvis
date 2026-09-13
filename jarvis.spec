# Windows GUI build for JARVIS
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("agent") + [
    "pycaw", "pycaw.pycaw", "comtypes",
    "sounddevice", "numpy", "speech_recognition",
]

a = Analysis(
    ["jarvis_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("docs", "docs")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="jarvis",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
