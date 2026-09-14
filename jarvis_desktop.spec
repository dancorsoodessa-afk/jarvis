# PyInstaller spec for the native JARVIS desktop application.
# Torch is intentionally optional: when it is not installed, TTS falls back to SAPI/Piper.
hiddenimports = [
    "numpy",
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "sounddevice",
    "speech_recognition",
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
    name="jarvis_desktop",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
