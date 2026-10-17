"""Unit tests for the Auto-Update module (updater.py)."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from updater import (
    check_github_release,
    get_github_repo,
    is_newer_version,
    parse_version,
    set_github_repo,
)


class UpdaterVersionTests(unittest.TestCase):
    def test_parse_version_standard(self):
        self.assertEqual(parse_version("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("V2.10.4"), (2, 10, 4))

    def test_parse_version_variable_lengths(self):
        self.assertEqual(parse_version("1.0"), (1, 0))
        self.assertEqual(parse_version("v3"), (3,))
        self.assertEqual(parse_version("v1.0.0.4"), (1, 0, 0, 4))

    def test_parse_version_with_suffixes(self):
        self.assertEqual(parse_version("v1.2.0-rc1"), (1, 2, 0, 1))
        self.assertEqual(parse_version("v2.0-beta"), (2, 0))

    def test_is_newer_version_cases(self):
        self.assertTrue(is_newer_version("1.0.0", "1.0.1"))
        self.assertTrue(is_newer_version("1.0.0", "1.1.0"))
        self.assertTrue(is_newer_version("1.0.0", "2.0.0"))
        self.assertTrue(is_newer_version("1.0.0", "v1.0.1"))
        self.assertTrue(is_newer_version("1.9.9", "1.10.0"))
        self.assertTrue(is_newer_version("1.2", "1.2.1"))

        # Same or older
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("1.1.0", "1.0.9"))
        self.assertFalse(is_newer_version("2.0.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.2.0", "1.2"))


class UpdaterGitHubTests(unittest.TestCase):
    @patch("updater.requests.get")
    def test_check_github_release_found_with_asset(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "name": "NOC Tools v2.0.0 Update",
            "body": "Fixed multi-incident detection and improved CCTV reports.",
            "html_url": "https://github.com/robertositumeang/NOC_Tools/releases/tag/v2.0.0",
            "published_at": "2026-10-10T12:00:00Z",
            "assets": [
                {
                    "name": "NOC Tools.exe",
                    "browser_download_url": "https://github.com/robertositumeang/NOC_Tools/releases/download/v2.0.0/NOC_Tools.exe",
                    "size": 60000000,
                }
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("robertositumeang/NOC_Tools")
        self.assertIsNotNone(info)
        self.assertEqual(info["tag_name"], "v2.0.0")
        self.assertEqual(info["asset_name"], "NOC Tools.exe")
        self.assertTrue(info["has_update"])
        self.assertIn("NOC_Tools.exe", info["download_url"])

    @patch("updater.requests.get")
    def test_check_github_release_does_not_treat_setup_installer_as_module(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.0.6",
            "name": "NOC Tools v1.0.6",
            "assets": [
                {
                    "name": "NOC_Tools_Setup_v1.0.6.exe",
                    "browser_download_url": "https://example.test/NOC_Tools_Setup_v1.0.6.exe",
                    "size": 174659016,
                }
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("robertositumeang/NOC_Tools")
        self.assertEqual(info["tag_name"], "v1.0.6")
        self.assertIsNone(info["asset_name"])
        self.assertIsNone(info["download_url"])
        self.assertFalse(info["has_update"])
        self.assertEqual(info["modular_items"], [])
        self.assertEqual(info["pending_modular"], [])

    @patch("updater.requests.get")
    def test_check_github_release_prefers_main_executable_over_setup_installer(
        self, mock_get
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.0.7",
            "name": "NOC Tools v1.0.7",
            "assets": [
                {
                    "name": "NOC Tools.exe",
                    "browser_download_url": "https://example.test/NOC%20Tools.exe",
                    "size": 63011084,
                },
                {
                    "name": "NOC_Tools_Setup_v1.0.7.exe",
                    "browser_download_url": "https://example.test/NOC_Tools_Setup_v1.0.7.exe",
                    "size": 174653642,
                },
            ],
        }
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            (app_dir / "NOC Tools.exe").write_bytes(b"a" * 63011084)
            with patch("updater.__file__", str(app_dir / "updater.py")):
                with patch("updater.APP_VERSION", "1.0.6"):
                    info = check_github_release("robertositumeang/NOC_Tools")

        self.assertEqual(info["asset_name"], "NOC Tools.exe")
        self.assertEqual(info["download_url"], "https://example.test/NOC%20Tools.exe")
        self.assertEqual(info["pending_modular"], [])
        self.assertTrue(info["has_update"])

    @patch("updater.requests.get")
    def test_check_github_release_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        info = check_github_release("nonexistent/repo")
        self.assertIsNone(info)

    @patch("updater.requests.get")
    def test_check_github_release_tracks_combined_web_tools_only(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "assets": [
                {
                    "name": "NOC Web Tools.exe",
                    "browser_download_url": "https://example.test/NOC-Web-Tools.exe",
                    "size": 1000000,
                },
                {
                    "name": "NOC Web Dashboard.exe",
                    "browser_download_url": "https://example.test/old-dashboard.exe",
                    "size": 1000000,
                },
                {
                    "name": "NOC Web Ticket Checker.exe",
                    "browser_download_url": "https://example.test/old-checker.exe",
                    "size": 1000000,
                },
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("owner/repo")

        self.assertIsNone(info["asset_name"])
        self.assertEqual(
            [item["name"] for item in info["modular_items"]],
            ["NOC Web Tools.exe"],
        )
        self.assertEqual(
            info["modular_items"][0]["target_rel_path"],
            "bin\\NOC Web Tools.exe",
        )

    @patch("updater.requests.get")
    def test_check_github_release_ignores_retired_vpn_assets(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "assets": [
                {
                    "name": "NOC VPN Manager.exe",
                    "browser_download_url": "https://example.test/old-vpn.exe",
                    "size": 1000000,
                }
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("owner/repo")

        self.assertIsNone(info["asset_name"])
        self.assertEqual(info["modular_items"], [])

    @patch("updater.requests.get")
    def test_check_github_release_does_not_track_external_master_workbook(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.0.1",
            "assets": [
                {
                    "name": "Site Management.xlsx",
                    "browser_download_url": "https://example.test/Site-Management.xlsx",
                    "size": 573222,
                }
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("owner/repo")

        self.assertFalse(info["has_update"])
        self.assertEqual(info["modular_items"], [])

    @patch("updater.requests.get")
    def test_check_github_release_matches_github_normalized_executable_names(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.0.1",
            "assets": [
                {
                    "name": "NOC.Tools.exe",
                    "browser_download_url": "https://example.test/NOC.Tools.exe",
                    "size": 1024,
                },
                {
                    "name": "NOC.Web.Tools.exe",
                    "browser_download_url": "https://example.test/NOC.Web.Tools.exe",
                    "size": 2048,
                },
                {
                    "name": "Capture_Modem.exe",
                    "browser_download_url": "https://example.test/Capture_Modem.exe",
                    "size": 3072,
                },
                {
                    "name": "NOC_Tools_Portable.zip",
                    "browser_download_url": "https://example.test/NOC_Tools_Portable.zip",
                    "size": 4096,
                },
            ],
        }
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = Path(temp_dir)
            (app_dir / "bin").mkdir()
            (app_dir / "NOC Tools.exe").write_bytes(b"a" * 1024)
            (app_dir / "bin" / "NOC Web Tools.exe").write_bytes(b"b" * 2048)
            (app_dir / "bin" / "Capture_Modem.exe").write_bytes(b"c" * 3072)

            with patch("updater.__file__", str(app_dir / "updater.py")):
                info = check_github_release("owner/repo")

        self.assertEqual(info["asset_name"], "NOC Tools.exe")
        self.assertEqual(
            [item["name"] for item in info["modular_items"]],
            ["NOC Tools.exe", "NOC Web Tools.exe", "Capture_Modem.exe"],
        )
        self.assertEqual(
            [item["target_rel_path"] for item in info["modular_items"]],
            ["NOC Tools.exe", "bin\\NOC Web Tools.exe", "bin\\Capture_Modem.exe"],
        )
        self.assertFalse(info["has_update"])
        self.assertEqual(info["pending_modular"], [])

    def test_repo_settings(self):
        orig = get_github_repo()
        set_github_repo("test-owner/test-repo")
        self.assertEqual(get_github_repo(), "test-owner/test-repo")
        set_github_repo(orig)  # restore


if __name__ == "__main__":
    unittest.main()
