# PyInstaller spec for the native JARVIS desktop application.
# Keep the agent imports explicit, but bundle PyTorch because the desktop GUI
# uses Silero TTS directly and the import is dynamic at runtime.
hiddenimports = [
    "torch",
    "torch._C",
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "sounddevice",
    "speech_recognition",
    "keyring.backends.Windows",
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
