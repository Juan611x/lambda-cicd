"""Empaqueta la función Lambda en build/lambda.zip.

El paquete es reproducible: los archivos se añaden en orden alfabético y con fecha
y permisos fijos, de modo que el mismo código produce siempre el mismo SHA-256.

Uso:  python scripts/package.py
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
REQUIREMENTS = ROOT / "requirements.txt"
BUILD_DIR = ROOT / "build"
DEPS_DIR = BUILD_DIR / "deps"
ZIP_PATH = BUILD_DIR / "lambda.zip"

FIXED_DATE = (1980, 1, 1, 0, 0, 0)  # Fecha mínima que admite el formato ZIP
FILE_MODE = 0o644
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def has_dependencies():
    """Indica si requirements.txt declara alguna dependencia real."""
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    return any(line.strip() and not line.strip().startswith("#") for line in lines)


def install_dependencies():
    """Instala las dependencias de la función junto al código, si las hay."""
    if not has_dependencies():
        print("Dependencias: ninguna (requirements.txt no declara paquetes)")
        return
    print(f"Dependencias: instalando desde {REQUIREMENTS.name}")
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-compile",
        "--disable-pip-version-check",
    ]
    subprocess.run([*command, "-r", str(REQUIREMENTS), "--target", str(DEPS_DIR)], check=True)


def collect_files():
    """Devuelve {ruta dentro del zip: archivo en disco}, ordenado por ruta."""
    files = {}
    for base in (DEPS_DIR, SRC_DIR):  # El código propio prevalece sobre las dependencias
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix in EXCLUDED_SUFFIXES:
                continue
            if EXCLUDED_DIRS.intersection(path.relative_to(base).parts):
                continue
            files[path.relative_to(base).as_posix()] = path
    return dict(sorted(files.items()))


def write_zip(files):
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = FILE_MODE << 16
            archive.writestr(info, path.read_bytes())


def main():
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    BUILD_DIR.mkdir(parents=True)

    install_dependencies()
    files = collect_files()
    if "lambda_function.py" not in files:
        sys.exit("Error: no se encontró src/lambda_function.py; el paquete no tendría handler.")
    write_zip(files)

    sha256 = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    size = ZIP_PATH.stat().st_size

    print(f"Paquete:  {ZIP_PATH.relative_to(ROOT).as_posix()}")
    print(f"Archivos: {len(files)}")
    for name in files:
        print(f"  - {name}")
    print(f"Tamaño:   {size} bytes")
    print(f"SHA-256:  {sha256}")

    # En GitHub Actions, deja los datos disponibles para los pasos siguientes
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as output:
            output.write(f"sha256={sha256}\nsize={size}\nfiles={len(files)}\n")


if __name__ == "__main__":
    main()
