# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules


hidden_imports = collect_submodules("mutagen") + collect_submodules("PySide6.QtMultimedia")

analysis = Analysis(
    ["echoscribe/main.py"],
    pathex=["echoscribe"],
    binaries=[],
    datas=[("echoscribe/assets", "assets")],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "PIL",
        "jinja2",
        "lxml",
        "matplotlib",
        "numpy",
        "openpyxl",
        "pandas",
        "pyarrow",
        "pygments",
        "pytest",
        "rich",
        "scipy",
        "torch",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="EchoScribe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="echoscribe/assets/echoscribe.ico",
    version="echoscribe/version_info.txt",
)
