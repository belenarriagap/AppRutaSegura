from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

abp_ROOT = Path(__file__).resolve().parents[1]
abp_DIST = abp_ROOT / "dist"
abp_APP_DIR = abp_DIST / "RutaSegura"
abp_STAGING = abp_DIST / "_nuevo"
abp_NEXT_DIR = abp_DIST / "RutaSegura-nueva"
abp_ISS = abp_ROOT / "abp_packaging" / "abp_rutasegura.iss"
abp_ISCC_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Inno Setup 6"
    / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
]


def abp_version() -> str:
    sys.path.insert(0, str(abp_ROOT))
    import abp_rutasegura

    return abp_rutasegura.__version__


def abp_build() -> None:
    print("1/4 PyInstaller…", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(abp_STAGING),
            "--workpath",
            str(abp_ROOT / "build"),
            str(abp_ROOT / "abp_packaging" / "abp_rutasegura.spec"),
        ],
        check=True,
    )


def abp_self_test(abp_exe: Path) -> None:
    print("2/4 Autoprueba del ejecutable…", flush=True)
    abp_log = abp_DIST / "autoprueba.txt"
    abp_log.unlink(missing_ok=True)
    abp_result = subprocess.run([str(abp_exe), "--self-test", "--log", str(abp_log)], timeout=600)
    abp_text = abp_log.read_text(encoding="utf-8") if abp_log.exists() else "(sin registro)"
    print(abp_text)
    if abp_result.returncode != 0:
        raise SystemExit(f"La autoprueba del ejecutable falló (código {abp_result.returncode}).")


def abp_discard(abp_folder: Path) -> bool:
    if not abp_folder.exists():
        return True
    abp_trash = abp_DIST / f"_borrar-{abp_folder.name}"
    shutil.rmtree(abp_trash, ignore_errors=True)
    try:
        abp_folder.rename(abp_trash)
    except OSError:
        return False
    shutil.rmtree(abp_trash, ignore_errors=True)
    return True


def abp_publish() -> Path:
    abp_built = abp_STAGING / "RutaSegura"
    abp_target = abp_APP_DIR
    if not abp_discard(abp_APP_DIR):
        abp_target = abp_NEXT_DIR
        abp_number = 2
        while not abp_discard(abp_target):
            abp_target = abp_DIST / f"{abp_NEXT_DIR.name}-{abp_number}"
            abp_number += 1
        print(f"    RutaSegura está abierto: la versión nueva queda en dist/{abp_target.name}.")
    abp_built.rename(abp_target)
    shutil.rmtree(abp_STAGING, ignore_errors=True)
    if abp_target == abp_APP_DIR and not abp_discard(abp_NEXT_DIR):
        print(f"    dist/{abp_NEXT_DIR.name} (versión anterior) está abierta: no se borró.")
    return abp_target


def abp_portable_zip(abp_ver: str) -> Path:
    print("3/4 Paquete portable…", flush=True)
    abp_target = abp_DIST / f"RutaSegura-{abp_ver}-portable"
    abp_archive = Path(shutil.make_archive(str(abp_target), "zip", abp_STAGING, "RutaSegura"))
    print(f"    {abp_archive} ({abp_archive.stat().st_size // (1024 * 1024)} MB)")
    return abp_archive


def abp_installer(abp_ver: str) -> Path | None:
    print("4/4 Instalador (Inno Setup)…", flush=True)
    abp_iscc = next(
        (abp_p for abp_p in abp_ISCC_CANDIDATES if abp_p.exists()), None
    ) or shutil.which("ISCC.exe")
    if abp_iscc is None:
        print(
            "    Inno Setup 6 no está instalado: se omite el instalador (queda el .zip portable)."
        )
        return None
    subprocess.run(
        [str(abp_iscc), f"/DAppVersion={abp_ver}", f"/O{abp_DIST}", str(abp_ISS)], check=True
    )
    abp_out = abp_DIST / f"RutaSegura-{abp_ver}-instalador.exe"
    print(f"    {abp_out}")
    return abp_out


def abp_main() -> int:
    abp_parser = argparse.ArgumentParser(description="Construye el ejecutable de RutaSegura")
    abp_parser.add_argument("--skip-build", action="store_true", help="reusar dist/RutaSegura")
    abp_args = abp_parser.parse_args()
    if sys.platform != "win32":
        print("Este script genera el paquete de Windows; ejecútelo en Windows.")
        return 1
    abp_ver = abp_version()
    if not abp_args.skip_build:
        abp_build()
        abp_self_test(abp_STAGING / "RutaSegura" / "RutaSegura.exe")
        abp_portable_zip(abp_ver)
        print(f"    {abp_publish()}")
    else:
        abp_self_test(abp_APP_DIR / "RutaSegura.exe")
    abp_installer(abp_ver)
    print("Listo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(abp_main())
