from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

abp_ROOT = Path(SPECPATH).parent
abp_PKG = abp_ROOT / "abp_rutasegura"
abp_RES = "abp_rutasegura/abp_resources"

abp_datas = [
    (str(abp_PKG / "abp_resources" / "abp_norms"), f"{abp_RES}/abp_norms"),
    (str(abp_PKG / "abp_resources" / "abp_profiles"), f"{abp_RES}/abp_profiles"),
    (str(abp_PKG / "abp_resources" / "abp_symbols"), f"{abp_RES}/abp_symbols"),
    (
        str(abp_PKG / "abp_engines" / "abp_cad" / "abp_bin"),
        "abp_rutasegura/abp_engines/abp_cad/abp_bin",
    ),
    *collect_data_files("ezdxf"),
    (
        str(abp_PKG / "abp_data" / "abp_migrations"),
        "abp_rutasegura/abp_data/abp_migrations",
    ),
]

abp_hiddenimports = [
    *collect_submodules("abp_rutasegura"),
    *collect_submodules("reportlab.pdfbase"),
    *collect_submodules("reportlab.graphics"),
    "alembic.runtime.migration",
    "alembic.ddl.sqlite",
    "sqlalchemy.dialects.sqlite",
    "matplotlib.backends.backend_agg",
]

abp_excludes = [
    "tkinter",
    "IPython",
    "pytest",
    "mypy",
    "ruff",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtNetwork",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_tkagg",
]

abp_a = Analysis(
    [str(abp_ROOT / "abp_packaging" / "abp_launcher.py")],
    pathex=[str(abp_ROOT)],
    datas=abp_datas,
    hiddenimports=abp_hiddenimports,
    excludes=abp_excludes,
    noarchive=False,
)
abp_pyz = PYZ(abp_a.pure)

abp_exe = EXE(
    abp_pyz,
    abp_a.scripts,
    [],
    exclude_binaries=True,
    name="RutaSegura",
    console=False,
    upx=False,
)

abp_coll = COLLECT(
    abp_exe,
    abp_a.binaries,
    abp_a.datas,
    upx=False,
    name="RutaSegura",
)
