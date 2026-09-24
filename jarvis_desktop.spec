# PyInstaller spec for the native JARVIS desktop application.
# Голос полностью локальный: Piper входит в пакет.
from PyInstaller.utils.hooks import collect_data_files

faster_whisper_datas = collect_data_files("faster_whisper")

hiddenimports = [
    "numpy",
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "sounddevice",
    "faster_whisper",
    "ctranslate2",
    "av",
    "tokenizers",
    "huggingface_hub",
]

a = Analysis(
    ["jarvis_desktop.py"],
    pathex=["."],
    binaries=[],
    datas=[("docs", "docs"), ("vendor/stt_model", "stt_model"), ("vendor/piper", "piper")] + faster_whisper_datas,
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
    upx=True,
    console=False,
    icon=None,
)
