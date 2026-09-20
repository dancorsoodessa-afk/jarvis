# PyInstaller spec for native JARVIS desktop application.
hiddenimports = [
    "numpy",
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "sounddevice",
    "vosk",
    "cffi",
]
a = Analysis(
    ["jarvis_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("docs", "docs"), ("vendor/stt_model", "stt_model"), ("vendor/piper", "piper")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="jarvis_desktop",
    debug=False, strip=False, upx=False, console=False, icon=None,
)
