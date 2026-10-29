# PyInstaller spec for the cloud-only JARVIS desktop application.
a = Analysis(
    ["jarvis_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("docs", "docs"), ("assets/jarvis-reactor-logo.png", "assets"), ("ui/jarvis_3d.html", "ui"), ("ui/vendor", "ui/vendor")],
    hiddenimports=[
        "numpy",
        "faster_whisper",
        "ctranslate2",
        "av",
        "sounddevice",
        "pycaw",
        "pycaw.pycaw",
        "comtypes",
    ],
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
    upx=True,
    console=False,
    icon="assets/jarvis-reactor-logo.ico",
)
