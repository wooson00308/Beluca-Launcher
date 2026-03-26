# -*- mode: python ; coding: utf-8 -*-
"""BPE Launcher PyInstaller spec."""

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

certifi_datas = collect_data_files("certifi")

a = Analysis(
    ["../src/launcher/__main__.py"],
    pathex=[],
    binaries=[],
    datas=certifi_datas,
    hiddenimports=[
        "launcher",
        "launcher.updater",
        "launcher.gui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BPELauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
