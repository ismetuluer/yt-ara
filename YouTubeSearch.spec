# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# yt-dlp dinamik olarak extractor modullerini yukler; hepsini toplamak gerekir.
ytdlp_hidden = collect_submodules('yt_dlp')
ytdlp_data = collect_data_files('yt_dlp')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=ytdlp_data + [('assets', 'assets')],
    hiddenimports=ytdlp_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YouTubeSearch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YouTubeSearch',
)
