# PyInstaller spec for the cloud-only JARVIS desktop application.
a = Analysis(
    ["jarvis_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("docs", "docs"), ("ui/jarvis_3d.html", "ui"), ("ui/vendor", "ui/vendor")],
    hiddenimports=[
        "numpy",
        "sounddevice",
        "pycaw",
        "pycaw.pycaw",
        "comtypes",
        "crypto_analyst.dashboard",
        "crypto_analyst.okx_ws",
        "websockets",
        "websockets.asyncio.client",
        "youtube_transcript_api",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest", "faster_whisper", "ctranslate2", "av"],
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
    icon=None,
)
