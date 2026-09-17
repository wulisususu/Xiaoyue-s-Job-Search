# PyInstaller onedir spec for the bundled core-api sidecar.
# Build with scripts/build-core.ps1 (local) or the CI packaging step (runner).
# alembic.ini + alembic/ ship as datas; app.db._core_root() resolves them
# via sys._MEIPASS (the _internal/ directory next to the exe).
from pathlib import Path

# SPECPATH is the directory containing this spec (services/core-api/packaging);
# the core root we need to collect from is its parent.
core_root = Path(SPECPATH).resolve().parents[0]

a = Analysis(
    [str(core_root / "packaging" / "xiaoyue_core_api.py")],
    pathex=[str(core_root)],
    binaries=[],
    datas=[
        (str(core_root / "alembic.ini"), "."),
        (str(core_root / "alembic"), "alembic"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="xiaoyue-core-api",
    debug=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="xiaoyue-core-api",
)
