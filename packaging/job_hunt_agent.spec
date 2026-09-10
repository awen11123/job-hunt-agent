# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


project_root = Path(SPECPATH).resolve().parent
static_root = project_root / "src" / "job_hunt_agent" / "web_static"
if not (static_root / "index.html").is_file():
    raise SystemExit("Run scripts/build_frontend.py before PyInstaller.")

datas = [
    (str(static_root), "web_static"),
    *copy_metadata("keyring"),
    *collect_data_files("keyring"),
]
hiddenimports = collect_submodules("keyring.backends")

a = Analysis(
    [str(project_root / "src" / "job_hunt_agent" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JobHuntAgent",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="JobHuntAgent",
)
