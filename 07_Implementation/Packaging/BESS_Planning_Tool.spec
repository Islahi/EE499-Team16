# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

implementation = Path(SPECPATH).resolve().parent
package = implementation / "src"
assets = package / "assets"

datas = [
    (str(assets), "src/assets"),
    # Numba uses the source path to locate its cache in a frozen application.
    (str(package / "fbs.py"), "src"),
]
datas += collect_data_files("xgboost", includes=["VERSION"])
for distribution in ("numba", "llvmlite", "numpy", "scikit-learn", "xgboost", "lightgbm"):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(package / "app.pyw")],
    pathex=[str(implementation)],
    binaries=collect_dynamic_libs("xgboost"),
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=[
        "IPython", "pytest", "statsmodels", "tkinter",
        "cupy", "dask", "distributed", "jax", "polars", "pyarrow", "tensorflow", "torch",
    ],
)
# Optional GPU adapters pulled in by scientific-library hooks can introduce
# hundreds of megabytes of CUDA DLLs on development PCs. The app uses CPU arrays.
gpu_components = {"cuda", "cupy", "cupy_backends", "cupyx", "nvidia"}
# Qt imports the Windows ICU ABI. A development tool's separate ICU DLL on
# PATH can shadow the system copy if the dependency scanner collects it.
shadowing_icu = {"icuuc.dll", "icudt78.dll"}


def cpu_entries(entries):
    return [
        entry for entry in entries
        if entry[0].replace("\\", "/").split("/")[0].split(".")[0] not in gpu_components
        and entry[0].lower() not in shadowing_icu
    ]


archive = PYZ(cpu_entries(analysis.pure))
exe = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="BESS_Planning_Tool",
    console=False,
    icon=str(assets / "icons" / "bess.ico"),
    upx=False,
)
distribution = COLLECT(
    exe, cpu_entries(analysis.binaries), cpu_entries(analysis.datas),
    name="BESS_Planning_Tool",
    upx=False,
)
