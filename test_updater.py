"""Unit tests for the Auto-Update module (updater.py)."""
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
            "html_url": "https://github.com/PT-Lindu-Putra-Utama/NOC-Project/releases/tag/v2.0.0",
            "published_at": "2026-10-10T12:00:00Z",
            "assets": [
                {
                    "name": "NOC Tools.exe",
                    "browser_download_url": "https://github.com/PT-Lindu-Putra-Utama/NOC-Project/releases/download/v2.0.0/NOC_Tools.exe",
                    "size": 60000000,
                }
            ],
        }
        mock_get.return_value = mock_resp

        info = check_github_release("PT-Lindu-Putra-Utama/NOC-Project")
        self.assertIsNotNone(info)
        self.assertEqual(info["tag_name"], "v2.0.0")
        self.assertEqual(info["asset_name"], "NOC Tools.exe")
        self.assertTrue(info["has_update"])
        self.assertIn("NOC_Tools.exe", info["download_url"])

    @patch("updater.requests.get")
    def test_check_github_release_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        info = check_github_release("nonexistent/repo")
        self.assertIsNone(info)

    def test_repo_settings(self):
        orig = get_github_repo()
        set_github_repo("test-owner/test-repo")
        self.assertEqual(get_github_repo(), "test-owner/test-repo")
        set_github_repo(orig)  # restore


if __name__ == "__main__":
    unittest.main()

