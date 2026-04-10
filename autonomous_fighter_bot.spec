# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
import os

datas = []
datas += collect_data_files('stable_baselines3')
datas += collect_data_files('ultralytics')
datas += collect_data_files('gymnasium')

# Add model file and other data files
datas.append(('yolov8n.pt', '.'))
datas.append(('common', 'common'))

# Add muscles DLL if it exists
if os.path.exists('muscles/build/Release/autonomous_fighter_muscles.dll'):
    datas.append(('muscles/build/Release/autonomous_fighter_muscles.dll', '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'ultralytics',
        'torch',
        'torchvision',
        'stable_baselines3',
        'gymnasium',
        'numpy',
        'cv2',
        'mss',
        'fastapi',
        'uvicorn',
        'websockets',
        'pydantic',
        'pywin32',
    ],
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
    a.binaries,
    a.datas,
    [],
    name='autonomous_fighter_bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
