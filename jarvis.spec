# PyInstaller spec for the JARVIS desktop command center.
# The desktop build is the primary Windows EXE.
hiddenimports = [
    "torch",
    "torch._C",
    "numpy",
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
    name="jarvis",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
