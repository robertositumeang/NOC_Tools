from pathlib import Path
from zipfile import ZipFile

import pytest

from package_portable import (
    PORTABLE_FILES,
    build_portable_package,
)


ROOT = Path(__file__).resolve().parent


def test_frozen_master_source_uses_bundled_resource_even_with_sibling_data(
    tmp_path: Path,
) -> None:
    from desktop_app import _resolve_master_source_dir

    executable_dir = tmp_path / "app"
    resource_dir = tmp_path / "runtime"
    sibling_data = executable_dir / "data"
    sibling_data.mkdir(parents=True)
    (sibling_data / "Site Management.xlsx").write_bytes(b"external workbook")

    source_dir = _resolve_master_source_dir(
        executable_dir,
        resource_dir,
        is_frozen=True,
    )

    assert source_dir == resource_dir / "site_management"
    assert source_dir != sibling_data


def test_source_mode_master_source_remains_project_directory(tmp_path: Path) -> None:
    from desktop_app import _resolve_master_source_dir

    project_dir = tmp_path / "project"
    resource_dir = tmp_path / "resources"

    assert _resolve_master_source_dir(project_dir, resource_dir, is_frozen=False) == project_dir


def _create_portable_inputs(root: Path) -> None:
    for relative_source, _ in PORTABLE_FILES:
        source = root / relative_source
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(f"fixture: {relative_source}".encode())
    admin_executable = root / "dist" / "NOC Tools Administrator.exe"
    admin_executable.parent.mkdir(parents=True, exist_ok=True)
    admin_executable.write_bytes(b"private admin executable")
    external_master = root / "dist" / "data" / "Site Management.xlsx"
    external_master.parent.mkdir(parents=True, exist_ok=True)
    external_master.write_bytes(b"duplicate master should not ship")
    (root / "dist" / "users.json").write_text("local credentials", encoding="utf-8")
    (root / "dist" / "bin" / "NOC VPN Manager.exe").write_text(
        "retired application", encoding="utf-8"
    )
    (root / "dist" / "bin" / "NOC Web Dashboard.exe").write_text(
        "retired application", encoding="utf-8"
    )
    (root / ".venv").mkdir()


def test_portable_package_excludes_admin_and_contains_only_operator_runtime_files(
    tmp_path: Path,
) -> None:
    _create_portable_inputs(tmp_path)
    output = tmp_path / "release" / "NOC_Tools_Portable.zip"

    result = build_portable_package(tmp_path, output)

    assert result == output.resolve()
    with ZipFile(result) as archive:
        names = set(archive.namelist())

    expected = {archive_name for _, archive_name in PORTABLE_FILES}
    assert names == expected
    assert "Admin/NOC Tools Administrator.exe" not in names
    assert "data/Site Management.xlsx" not in names
    assert "dist/users.json" not in names
    assert not any("VPN" in name for name in names)
    assert not any(name.startswith(".venv/") for name in names)
    assert not any("NOC Web Dashboard.exe" in name for name in names)


def test_portable_package_fails_for_missing_required_runtime_file(tmp_path: Path) -> None:
    _create_portable_inputs(tmp_path)
    missing_path = tmp_path / "dist" / "bin" / "Capture_Modem.exe"
    missing_path.unlink()
    output = tmp_path / "release" / "NOC_Tools_Portable.zip"

    with pytest.raises(FileNotFoundError, match="Capture_Modem.exe"):
        build_portable_package(tmp_path, output)

    assert not output.exists()
    assert not list(output.parent.glob("*.tmp"))


def test_distribution_configuration_excludes_vpn_and_documents_target_requirements() -> None:
    build_script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
    installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
    spec = (ROOT / "NOC Tools.spec").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    portable_readme = (ROOT / "PORTABLE_README.txt").read_text(encoding="utf-8")

    assert "package_portable.py" in build_script
    assert 'copy /y "%MASTER_FILE%" "dist\\data\\Site Management.xlsx"' not in build_script
    assert "dist\\data\\" not in installer
    assert "site_management" in spec
    assert "bundled inside NOC Tools.exe" in portable_readme
    assert "NOC VPN Manager.spec" not in build_script
    assert 'if exist "dist\\bin\\NOC VPN Manager.exe" del' in build_script
    assert "NOC VPN Manager" not in installer
    assert "each laptop must be" in readme.lower()
    assert "WebView2" in readme


def test_release_version_matches_installer_filename() -> None:
    from noc_brand import APP_VERSION

    installer = (ROOT / "installer.iss").read_text(encoding="utf-8")

    assert f'#define MyAppVersion "{APP_VERSION}"' in installer
    assert f"OutputBaseFilename=NOC_Tools_Setup_v{APP_VERSION}" in installer


def test_current_company_name_replaces_the_old_name_in_product_surfaces() -> None:
    files = (
        "build_exe.bat",
        "desktop_app.py",
        "installer.iss",
        "license_mgr.py",
    )
    for relative_path in files:
        contents = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "PT. LINDU PUTRA UTAMA" not in contents.upper()
        assert "PT. KEREAKTIF Indonesia" in contents
