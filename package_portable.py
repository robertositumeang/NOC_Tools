from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


PORTABLE_FILES = (
    ("dist/NOC Tools.exe", "NOC Tools.exe"),
    ("dist/bin/NOC Web Tools.exe", "bin/NOC Web Tools.exe"),
    ("dist/bin/Capture_Modem.exe", "bin/Capture_Modem.exe"),
    ("dist/data/Site Management.xlsx", "data/Site Management.xlsx"),
    ("app_icon.ico", "app_icon.ico"),
    ("PORTABLE_README.txt", "README_PORTABLE.txt"),
)
def build_portable_package(
    project_root: Path,
    output_path: Path,
) -> Path:
    project_root = project_root.resolve()
    missing = [
        str(project_root / source)
        for source, _ in PORTABLE_FILES
        if not (project_root / source).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Portable package is missing required files:\n" + "\n".join(missing)
        )

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.stem}-",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for source, archive_name in PORTABLE_FILES:
                archive.write(project_root / source, archive_name)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a portable NOC Tools package for Windows laptops."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("installer_output") / "NOC_Tools_Portable.zip",
        help="ZIP output path (default: installer_output/NOC_Tools_Portable.zip)",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent
    output_path = args.output
    if not output_path.is_absolute():
        output_path = project_root / output_path
    package_path = build_portable_package(project_root, output_path)
    print(f"Portable package created: {package_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
