import unittest
from datetime import datetime
from io import BytesIO, StringIO
import csv
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

from openpyxl import Workbook, load_workbook
from PyQt6.QtCore import QEvent, QEventLoop, QRect, QSettings, QThread, QTimer, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QMainWindow,
)

from app import StartupSplash, _StartupSplashDismissal
from noc_brand import apply_standard_window_chrome
from desktop_app import (
    AppSelectionDialog,
    DEFAULT_RESOLUTION,
    DEFAULT_SCALE_PERCENT,
    NORMALIZED_COLUMNS,
    SCALE_OPTIONS,
    SUMMARY_REPORT_COLUMNS,
    WINDOW_RESOLUTIONS,
    _LauncherReturnFilter,
    _qt_scale_factor,
    _relaunch_with_scale,
    _saved_resolution,
    _saved_scale_percent,
    _window_geometry_for_resolution,
    _alarm_overlaps_range,
    _executive_summary_text,
    _preferred_alarm_names,
    _raw_alarm_rows_and_headers,
    _report_data_for_selection,
    _selected_site_report_rows,
    _suggested_selected_export_filename,
    save_report,
    save_selected_site_report,
)
from alarm_analysis import (
    build_site_index,
    detect_alarm_vendor,
    format_duration,
    normalize_alarms,
    read_table,
    summarize_providers,
)


class AlarmAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.site_index = build_site_index([
            {
                "Site ID": "MLU00001",
                "Site Name": "SITE SATU",
                "Satellite/MW Brand": "TELSTAR-18V",
                "Spotbeam": "BEAM 11",
                "Status": "BAPL",
                "Provinsi": "MALUKU",
                "Vendor Transmisi": "IPT",
            },
            {
                "Site ID": "MLU00002",
                "Site Name": "SITE DUA",
                "Satellite/MW Brand": "TELSTAR-18V",
                "Spotbeam": "BEAM 11",
                "Status": "Non BAPL",
                "Provinsi": "MALUKU",
            },
        ])

    def test_fiberhome_s1_link_is_preferred_with_other_preferred_alarms(self):
        alarms = [
            {"Alarm Name": "S1 Link Failure", "Vendor": "Fiberhome"},
            {"Alarm Name": "Cell Out of Service", "Vendor": "Fiberhome"},
            {"Alarm Name": "S1 Link Alarm", "Vendor": "ZTE"},
            {"Alarm Name": "Radio Unit Fault", "Vendor": "Huawei"},
        ]

        self.assertEqual(
            _preferred_alarm_names(alarms),
            {"S1 Link Failure", "Cell Out of Service"},
        )

    def test_fiberhome_s1_link_preserves_existing_down_alarm_fallback(self):
        alarms = [
            {"Alarm Name": "S1 Link Failure", "Vendor": "Fiberhome"},
            {"Alarm Name": "Power cut", "Vendor": "ZTE"},
        ]

        self.assertEqual(
            _preferred_alarm_names(alarms),
            {"S1 Link Failure", "Power cut"},
        )

    def test_normalizes_fiberhome_and_enriches_from_site_management(self):
        rows = normalize_alarms([
            {
                "Fault Source": "Maluku,ZZX_MLU00001_FV_SITE_SATU(1037)",
                "Alarm Name": "NE Disconnected",
                "Generation Time": "09-27-2026 16:26:42",
                "Clear Time": "09-27-2026 16:29:27",
                "Clear Status": "NE reported and cleared",
                "Level": "Major",
                "Alarm Type": "Telecommunication",
                "NE ID": "1037",
            },
        ], self.site_index, "Fiberhome")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Site ID"], "MLU00001")
        self.assertEqual(rows[0]["VSAT Provider"], "TELSTAR-18V")
        self.assertEqual(rows[0]["Status BAPL"], "BAPL")
        self.assertEqual(rows[0]["Vendor Transmisi"], "IPT")
        self.assertEqual(rows[0]["Alarm Type"], "Telecommunication")
        self.assertEqual(rows[0]["Alarm State"], "Cleared")


    def test_peak_counts_distinct_sites_during_overlapping_cleared_alarms(self):
        start = datetime(2026, 9, 27, 16, 0)
        alarms = [
            {
                "Site ID": "MLU00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": start, "Clear Time": datetime(2026, 9, 27, 16, 10),
            },
            {
                "Site ID": "MLU00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "ENB out of service", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 16, 2), "Clear Time": datetime(2026, 9, 27, 16, 8),
            },
            {
                "Site ID": "MLU00002", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 16, 4), "Clear Time": datetime(2026, 9, 27, 16, 12),
            },
        ]

        summary = summarize_providers(alarms, {"NE Disconnected", "ENB out of service"}, minimum_sites=2, now=start)

        self.assertEqual(summary[0]["Peak Simultaneous Sites"], 2)
        self.assertEqual(summary[0]["Sites at Peak"], ["MLU00001", "MLU00002"])
        self.assertEqual(summary[0]["Current Down Sites"], 0)
        self.assertTrue(summary[0]["Massive Down"])

    def test_active_alarms_are_counted_once_per_site(self):
        start = datetime(2026, 9, 27, 16, 0)
        alarms = [
            {
                "Site ID": "MLU00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Active",
                "Occurrence Time": start, "Clear Time": None,
            },
            {
                "Site ID": "MLU00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "ENB out of service", "Alarm State": "Active",
                "Occurrence Time": start, "Clear Time": None,
            },
        ]

        summary = summarize_providers(
            alarms,
            {"NE Disconnected", "ENB out of service"},
            now=datetime(2026, 9, 27, 16, 5),
        )

        self.assertEqual(summary[0]["Current Down Sites"], 1)
        self.assertEqual(summary[0]["Peak Simultaneous Sites"], 1)

    def test_peak_only_counts_alarm_intervals_overlapping_selected_range(self):
        alarms = [
            {
                "Site ID": "MLU00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 8, 55),
                "Clear Time": datetime(2026, 9, 27, 9, 5),
            },
            {
                "Site ID": "MLU00002", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 9, 1),
                "Clear Time": datetime(2026, 9, 27, 9, 4),
            },
            {
                "Site ID": "MLU00002", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 10, 1),
                "Clear Time": datetime(2026, 9, 27, 10, 4),
            },
        ]

        summary = summarize_providers(
            alarms,
            {"NE Disconnected"},
            range_start=datetime(2026, 9, 27, 9),
            range_end=datetime(2026, 9, 27, 10),
            now=datetime(2026, 9, 27, 11),
        )

        self.assertEqual(summary[0]["Peak Simultaneous Sites"], 2)
        self.assertEqual(summary[0]["Sites at Peak"], ["MLU00001", "MLU00002"])
        self.assertGreaterEqual(summary[0]["Peak Time"], datetime(2026, 9, 27, 9))
        self.assertLess(summary[0]["Peak Time"], datetime(2026, 9, 27, 10))

    def test_detects_multiple_massive_incidents_for_same_vsat(self):
        alarms = [
            {
                "Site ID": "OLD00001", "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11",
                "Alarm Name": "NE Disconnected", "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 1),
                "Clear Time": datetime(2026, 9, 27, 12),
            },
        ]
        for occurrence, clear_time in (
            (datetime(2026, 9, 27, 5), datetime(2026, 9, 27, 5, 30)),
            (datetime(2026, 9, 27, 7), datetime(2026, 9, 27, 7, 30)),
        ):
            for site_id in ("MLU00001", "MLU00002", "MLU00003"):
                alarms.append({
                    "Site ID": site_id,
                    "VSAT Provider": "TELSTAR-18V",
                    "Spotbeam": "BEAM 11",
                    "Alarm Name": "NE Disconnected",
                    "Alarm State": "Cleared",
                    "Occurrence Time": occurrence,
                    "Clear Time": clear_time,
                })

        summaries = summarize_providers(
            alarms,
            {"NE Disconnected"},
            minimum_sites=3,
            range_start=datetime(2026, 9, 27, 4),
            range_end=datetime(2026, 9, 27, 8),
            now=datetime(2026, 9, 27, 8),
        )

        self.assertEqual(len(summaries), 2)
        self.assertEqual(
            [summary["Peak Time"] for summary in summaries],
            [datetime(2026, 9, 27, 5), datetime(2026, 9, 27, 7)],
        )
        self.assertEqual([summary["Peak Simultaneous Sites"] for summary in summaries], [3, 3])
        self.assertTrue(all(summary["Massive Down"] for summary in summaries))
        self.assertEqual(
            [summary["Sites at Peak"] for summary in summaries],
            [["MLU00001", "MLU00002", "MLU00003"], ["MLU00001", "MLU00002", "MLU00003"]],
        )

    def test_rejects_invalid_time_range(self):
        with self.assertRaises(ValueError):
            summarize_providers(
                [],
                set(),
                range_start=datetime(2026, 9, 27, 10),
                range_end=datetime(2026, 9, 27, 9),
            )

    def test_detects_excel_alarm_vendor_without_known_filename_or_extension(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["ME", "Alarm Code Name", "Alarm Type", "Occurrence Time", "Clear Time"])
        sheet.append([
            "ZZX_MLU00001_FV_SITE_SATU(1037)",
            "NE Disconnected",
            "Communication Alarm",
            "2026-09-27 09:00:00",
            "",
        ])
        buffer = BytesIO()
        workbook.save(buffer)

        rows = read_table(buffer.getvalue(), "random-download.data")

        self.assertEqual(detect_alarm_vendor(rows), "ZTE")
        normalized = normalize_alarms(rows, self.site_index, detect_alarm_vendor(rows) or "")
        self.assertEqual(normalized[0]["Site ID"], "MLU00001")
        self.assertEqual(normalized[0]["Alarm Type"], "Communication Alarm")

    def test_detects_nms_workbook_inside_zip_with_arbitrary_names(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Fault Source", "Alarm Name", "Generation Time", "Clear Time", "Clear Status"])
        sheet.append([
            "Maluku,ZZX_MLU00001_FV_SITE_SATU(1037)",
            "NE Disconnected",
            "09-27-2026 09:00:00",
            "",
            "Uncleared",
        ])
        excel = BytesIO()
        workbook.save(excel)
        archive_buffer = BytesIO()
        with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("opaque-member.data", excel.getvalue())

        rows = read_table(archive_buffer.getvalue(), "alarm-bundle.unknown")

        self.assertEqual(detect_alarm_vendor(rows), "Fiberhome")
        normalized = normalize_alarms(rows, self.site_index, detect_alarm_vendor(rows) or "")
        self.assertEqual(normalized[0]["Alarm State"], "Active")

    def test_reads_zte_csv_with_preamble_and_arbitrary_filename(self):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Alarm Records -- Alarm Logs"])
        writer.writerow(["Save Time: 2026-09-27 10:30:00"])
        writer.writerow(["", "Severity", "Alarm ID", "Name", "Alarm Source", "Occurred On (NT)", "Cleared On (NT)", "Clearance Status"])
        writer.writerow(["Root alarm", "Critical", "1014", "The link between the server and the ME is broken", "ZZX_MLU00001_FV_SITE_SATU", "2026-09-27 09:00:00", "-", "Uncleared"])

        rows = read_table(output.getvalue().encode("utf-8-sig"), "whatever.content")

        self.assertEqual(detect_alarm_vendor(rows), "ZTE")
        normalized = normalize_alarms(rows, self.site_index, detect_alarm_vendor(rows) or "")
        self.assertEqual(normalized[0]["Alarm Name"], "The link between the server and the ME is broken")
        self.assertEqual(normalized[0]["Alarm State"], "Active")

    def test_reads_huawei_xlsx_from_alarm_table_content_not_workbook_title(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Alarm Records -- Alarm Logs"])
        sheet.append(["Save Time: 2026-10-05 21:23:58"])
        sheet.append(["Username: MSS_LINDU"])
        sheet.append(["Maintenance Status is in NORMAL."])
        sheet.append([])
        sheet.append([
            "", "Severity", "Alarm ID", "Name", "NE Type", "Alarm Source",
            "Occurred On (NT)", "Cleared On (NT)", "Clearance Status", "eNodeB ID",
        ])
        sheet.append([
            "Root alarm", "Major", "26564", "Cell Unavailable", "BTS5900",
            "MLU00001_BTS", "2026-10-05 09:00:00", "-", "Uncleared", "1037",
        ])
        buffer = BytesIO()
        workbook.save(buffer)

        rows = read_table(buffer.getvalue(), "export-without-vendor-name.xlsx")

        self.assertEqual(detect_alarm_vendor(rows), "Huawei")
        normalized = normalize_alarms(
            rows,
            build_site_index([{
                "Site ID": "MLU00001",
                "Site Name": "SITE SATU",
                "enodeb ID/enodeb ID OPSEL": "1037",
            }]),
            detect_alarm_vendor(rows) or "",
        )
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["Vendor"], "Huawei")
        self.assertEqual(normalized[0]["Site ID"], "MLU00001")
        self.assertEqual(normalized[0]["Alarm Name"], "Cell Unavailable")
        self.assertEqual(
            list(normalized[0]["_raw"]),
            [
                "Column 1", "Severity", "Alarm ID", "Name", "NE Type",
                "Alarm Source", "Occurred On (NT)", "Cleared On (NT)",
                "Clearance Status", "eNodeB ID",
            ],
        )

    def test_maps_huawei_current_alarm_using_embedded_enodeb_id_and_first_occurrence(self):
        rows = [{
            "Severity": "Major",
            "Alarm ID": "25954",
            "Name": "User Plane Fault",
            "NE Type": "BTS5900",
            "Alarm Source": "-",
            "First Occurred (NT)": "2026-10-05 09:00:00",
            "Last Occurred (NT)": "2026-10-05 10:00:00",
            "Cleared On (NT)": "2026-10-05 10:01:19",
            "Clearance Status": "Cleared",
            "eNodeB ID": "-",
            "Additional Information": "RAT_INFO=L, eNodeBId=1037",
        }]
        site_index = build_site_index([{
            "Site ID": "MLU00001",
            "Site Name": "SITE SATU",
            "enodeb ID/enodeb ID OPSEL": "1037",
        }])

        normalized = normalize_alarms(rows, site_index, "Huawei")

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["Site ID"], "MLU00001")
        self.assertEqual(
            normalized[0]["Occurrence Time"],
            datetime(2026, 10, 5, 9, 0),
        )
        self.assertEqual(
            normalized[0]["Clear Time"],
            datetime(2026, 10, 5, 10, 1, 19),
        )
        self.assertEqual(normalized[0]["Duration"], "1h 1m 19s")


class DesktopExportTests(unittest.TestCase):
    def test_raw_alarm_headers_follow_source_order_and_append_extra_columns(self):
        alarms = [
            {
                "Occurrence Time": datetime(2026, 9, 27, 6, 10),
                "_raw": {"ME": "site-1", "Alarm Code Name": "Down", "Occurrence Time": "06:10"},
            },
            {
                "Occurrence Time": datetime(2026, 9, 27, 6, 11),
                "_raw": {
                    "Occurrence Time": "06:11",
                    "ME": "site-2",
                    "Alarm Code Name": "Down",
                    "New Vendor Field": "extra",
                },
            },
        ]

        raw_rows, headers = _raw_alarm_rows_and_headers(alarms)

        self.assertEqual(
            headers,
            ["ME", "Alarm Code Name", "Occurrence Time", "New Vendor Field"],
        )
        self.assertEqual(raw_rows[1]["New Vendor Field"], "extra")

    def test_selected_site_rows_keep_repeated_sites_in_separate_incidents(self):
        alarms = []
        for occurrence, clear_time in (
            (datetime(2026, 9, 27, 5), datetime(2026, 9, 27, 5, 30)),
            (datetime(2026, 9, 27, 7), datetime(2026, 9, 27, 7, 30)),
        ):
            alarms.append({
                "Vendor": "ZTE", "Site ID": "MLU00001", "Site Name": "SITE MLU00001",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": occurrence, "Clear Time": clear_time,
                "Duration": "30m 0s", "Alarm State": "Cleared", "NE ID": "1037", "Alarm ID": "MLU00001",
            })
        summaries = [
            {
                "Range Start": datetime(2026, 9, 27, 4), "Range End": datetime(2026, 9, 27, 8),
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Current Down Sites": 0,
                "Peak Simultaneous Sites": 1, "Peak Time": datetime(2026, 9, 27, 5),
                "Massive Down": True, "Sites at Peak": ["MLU00001"],
            },
            {
                "Range Start": datetime(2026, 9, 27, 4), "Range End": datetime(2026, 9, 27, 8),
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Current Down Sites": 0,
                "Peak Simultaneous Sites": 1, "Peak Time": datetime(2026, 9, 27, 7),
                "Massive Down": True, "Sites at Peak": ["MLU00001"],
            },
        ]

        rows = _selected_site_report_rows(alarms, summaries)

        self.assertEqual(len(rows), 2)
        self.assertEqual([row["Occurrence Time"] for row in rows], [
            datetime(2026, 9, 27, 5),
            datetime(2026, 9, 27, 7),
        ])
        self.assertEqual([row["_peak_time"] for row in rows], [
            datetime(2026, 9, 27, 5),
            datetime(2026, 9, 27, 7),
        ])

    def test_report_selection_includes_alarms_overlapping_range_start(self):
        start = datetime(2026, 9, 27, 9)
        end = datetime(2026, 9, 27, 10)
        alarms = [
            {
                "Vendor": "ZTE", "Site ID": "MLU00001", "Site Name": "SITE MLU00001",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 8, 55),
                "Clear Time": datetime(2026, 9, 27, 9, 20), "Alarm State": "Cleared",
                "NE ID": "1037", "Alarm ID": "MLU00001",
            },
            {
                "Vendor": "ZTE", "Site ID": "MLU00002", "Site Name": "SITE MLU00002",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 10, 1),
                "Clear Time": datetime(2026, 9, 27, 10, 20), "Alarm State": "Cleared",
                "NE ID": "1038", "Alarm ID": "MLU00002",
            },
        ]
        summaries = [
            {
                "Range Start": start, "Range End": end, "VSAT Provider": "TELSTAR-18V",
                "Spotbeam": "BEAM 11", "Current Down Sites": 0, "Peak Simultaneous Sites": 1,
                "Peak Time": datetime(2026, 9, 27, 9), "Massive Down": False,
                "Sites at Peak": ["MLU00001"],
            },
        ]

        selected_alarms, _ = _report_data_for_selection(
            alarms,
            summaries,
            {"NE Disconnected"},
            {"TELSTAR-18V"},
            {"Communication"},
            start,
            end,
            selected_summary_keys={("TELSTAR-18V", "BEAM 11")},
            group_by_spotbeam=True,
        )

        self.assertTrue(_alarm_overlaps_range(alarms[0], start, end))
        self.assertFalse(_alarm_overlaps_range(alarms[1], start, end))
        self.assertEqual([alarm["Site ID"] for alarm in selected_alarms], ["MLU00001"])

    def test_selected_summary_export_has_one_row_per_site(self):
        start = datetime(2026, 9, 27, 9)
        end = datetime(2026, 9, 27, 10)
        alarms = [
            {
                "Vendor": "ZTE", "Site ID": site_id, "Site Name": f"SITE {site_id}",
                "VSAT Provider": provider, "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Paket": "10", "Area": "AREA 5 - MALUKU",
                "Vendor Transmisi": "IPT",
                "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 9, 10),
                "Clear Time": datetime(2026, 9, 27, 9, 20), "Alarm State": "Cleared",
                "NE ID": "1037", "Alarm ID": site_id,
            }
            for provider, site_id in (
                ("TELSTAR-18V", "MLU00001"),
                ("TELSTAR-18V", "MLU00002"),
                ("JCSAT-1C", "MLU00003"),
            )
        ]
        alarms.append({
            **alarms[0],
            "Alarm Name": "Power cut",
            "Occurrence Time": datetime(2026, 9, 27, 9, 12),
            "Clear Time": datetime(2026, 9, 27, 9, 30),
        })
        summaries = [
            {
                "Range Start": start, "Range End": end, "VSAT Provider": "TELSTAR-18V",
                "Spotbeam": "BEAM 11", "Current Down Sites": 2, "Peak Simultaneous Sites": 2,
                "Peak Time": datetime(2026, 9, 27, 9, 15), "Massive Down": True,
                "Sites at Peak": ["MLU00001", "MLU00002"],
            },
            {
                "Range Start": start, "Range End": end, "VSAT Provider": "JCSAT-1C",
                "Spotbeam": "BEAM 11", "Current Down Sites": 1, "Peak Simultaneous Sites": 1,
                "Peak Time": datetime(2026, 9, 27, 9, 15), "Massive Down": False,
                "Sites at Peak": ["MLU00003"],
            },
        ]

        selected_alarms, selected_summaries = _report_data_for_selection(
            alarms,
            summaries,
            {"NE Disconnected", "Power cut"},
            {"TELSTAR-18V", "JCSAT-1C"},
            {"Communication"},
            start,
            end,
            selected_summary_keys={("TELSTAR-18V", "BEAM 11")},
            group_by_spotbeam=True,
        )

        with TemporaryDirectory() as directory:
            path = f"{directory}/selected-vsat.xlsx"
            save_selected_site_report(path, selected_alarms, selected_summaries)
            workbook = load_workbook(path, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Executive Summary", "Site Impact Massive", "Alarm Original - ZTE"],
        )
        executive_sheet = workbook["Executive Summary"]
        self.assertEqual(len(executive_sheet._charts), 0)
        self.assertEqual(executive_sheet.max_column, 5)
        self.assertEqual(executive_sheet.max_row, 12)
        self.assertEqual(
            {str(merged_range) for merged_range in executive_sheet.merged_cells.ranges},
            {"A1:E1", "A10:C10"},
        )
        self.assertEqual(executive_sheet["A1"].value, "EXECUTIVE SUMMARY | VSAT OUTAGE")
        self.assertEqual(executive_sheet["A2"].value, "Paket")
        self.assertEqual(executive_sheet["B2"].value, 10)
        self.assertEqual(executive_sheet["A3"].value, "Area")
        self.assertEqual(executive_sheet["B3"].value, "AREA 5 - MALUKU")
        self.assertEqual(executive_sheet["A4"].value, "Vendor Transmisi")
        self.assertEqual(executive_sheet["B4"].value, "IPT")
        self.assertEqual(executive_sheet["A5"].value, "Satellite")
        self.assertEqual(executive_sheet["B5"].value, "TELSTAR-18V")
        self.assertEqual(executive_sheet["A6"].value, "Unique impacted sites")
        self.assertEqual(executive_sheet["B6"].value, 2)
        self.assertEqual(executive_sheet["A7"].value, "BAPL")
        self.assertEqual(executive_sheet["B7"].value, 2)
        self.assertEqual(executive_sheet["A8"].value, "Non BAPL")
        self.assertEqual(executive_sheet["B8"].value, 0)
        self.assertEqual(executive_sheet["D2"].value, "Total Site ZTE")
        self.assertEqual(executive_sheet["E2"].value, 2)
        self.assertEqual(executive_sheet["D3"].value, "Alarm Occurrence")
        self.assertEqual(executive_sheet["D4"].value, "Alarm Clear")
        self.assertEqual(executive_sheet["D5"].value, "Incident duration")
        self.assertEqual(executive_sheet["D6"].value, "Average BTS Downtime")
        self.assertEqual(executive_sheet["E6"].value, "00:14:00")
        self.assertEqual(executive_sheet["A10"].value, "REGION")
        self.assertEqual(
            [executive_sheet.cell(11, col).value for col in range(1, 4)],
            ["Region", "Unique Sites", "Share"],
        )
        executive_values = [
            str(cell.value)
            for row in executive_sheet.iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertFalse(any("Service Incident TT" in value for value in executive_values))
        self.assertIn("Unique impacted sites", executive_values)
        self.assertIn("Alarm Occurrence", executive_values)
        self.assertIn("Alarm Clear", executive_values)
        self.assertIn("REGION", executive_values)
        self.assertFalse(any("OUTAGE TIMELINE" in value for value in executive_values))
        self.assertFalse(any("Site-level detail and impacted site list" in value for value in executive_values))
        site_rows = _selected_site_report_rows(selected_alarms, selected_summaries)
        copy_text = _executive_summary_text(selected_alarms, site_rows, selected_summaries)
        self.assertIn("2 Site (2 BAPL, 0 non BAPL)", copy_text)
        self.assertIn("Status : CLOSED", copy_text)
        self.assertIn("Start time : 2026-09-27 09:10:00", copy_text)
        self.assertIn("End time : 2026-09-27 09:30:00", copy_text)
        self.assertIn("PIC Vendor Transmisi : IPT", copy_text)
        self.assertIn("Action : Autorecovery", copy_text)
        site_sheet = workbook["Site Impact Massive"]
        headers = ["No", *NORMALIZED_COLUMNS]
        self.assertEqual(
            [cell.value for cell in site_sheet[1]],
            headers,
        )
        site_rows = list(site_sheet.iter_rows(min_row=2, values_only=True))
        site_id_index = headers.index("Site ID")
        vendor_index = headers.index("Vendor")
        alarm_name_index = headers.index("Alarm Name")
        self.assertEqual(
            [row[site_id_index] for row in site_rows],
            ["MLU00001", "MLU00002"],
        )
        self.assertEqual(len({row[site_id_index] for row in site_rows}), len(site_rows))
        self.assertEqual(site_rows[0][vendor_index], "ZTE")
        self.assertEqual(site_rows[0][alarm_name_index], "Power cut")
        self.assertEqual(site_sheet.max_column, len(headers))

        raw_sheet = workbook["Alarm Original - ZTE"]
        raw_rows = list(raw_sheet.iter_rows(min_row=2, values_only=True))
        # MLU00001 had 2 alarms (Power cut and NE Disconnected) and MLU00002 had 1, so both are preserved without deduplication
        self.assertEqual(len(raw_rows), 3)

    def test_incident_report_pic_values_follow_transmission_vendor(self):
        site_rows = [
            {
                "Site ID": "MLU00001",
                "Vendor Transmisi": "IPT",
                "Status BAPL": "BAPL",
                "Occurrence Time": datetime(2026, 9, 27, 9, 10),
                "Clear Time": datetime(2026, 9, 27, 9, 20),
                "Alarm State": "Cleared",
            },
            {
                "Site ID": "MLU00002",
                "Vendor Transmisi": "VENDOR PAPUA",
                "Status BAPL": "Non BAPL",
                "Occurrence Time": datetime(2026, 9, 27, 9, 12),
                "Clear Time": datetime(2026, 9, 27, 9, 25),
                "Alarm State": "Cleared",
            },
        ]
        report = _executive_summary_text([], site_rows, [])

        self.assertIn("PIC Incident : IPT, VENDOR PAPUA", report)
        self.assertIn("PIC Vendor Transmisi : IPT, VENDOR PAPUA", report)

    def test_selected_summary_export_multi_vendor_has_combined_site_impact_and_original_sheets(self):
        start = datetime(2026, 9, 27, 9)
        end = datetime(2026, 9, 27, 10)
        alarms = [
            {
                "Vendor": "ZTE", "Site ID": "MLU00001", "Site Name": "SITE MLU00001",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 9, 10),
                "Clear Time": datetime(2026, 9, 27, 9, 20), "Alarm State": "Cleared",
                "NE ID": "1037", "Alarm ID": "1",
                "_raw": {"ME": "ZZX_MLU00001", "Alarm Code Name": "NE Disconnected", "Occurred On": "2026-09-27 09:10:00"},
            },
            {
                "Vendor": "Fiberhome", "Site ID": "MLU00002", "Site Name": "SITE MLU00002",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 9, 15),
                "Clear Time": datetime(2026, 9, 27, 9, 25), "Alarm State": "Cleared",
                "NE ID": "1038", "Alarm ID": "2",
                "_raw": {"Fault Source": "Maluku,ZZX_MLU00002", "Alarm Name": "NE Disconnected", "Generation Time": "2026-09-27 09:15:00"},
            },
            # Duplicate alarm on Fiberhome site MLU00002 to test that duplicate alarms are preserved
            {
                "Vendor": "Fiberhome", "Site ID": "MLU00002", "Site Name": "SITE MLU00002",
                "VSAT Provider": "TELSTAR-18V", "Spotbeam": "BEAM 11", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "ENB out of service", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 9, 16),
                "Clear Time": datetime(2026, 9, 27, 9, 28), "Alarm State": "Cleared",
                "NE ID": "1038", "Alarm ID": "3",
                "_raw": {"Fault Source": "Maluku,ZZX_MLU00002", "Alarm Name": "ENB out of service", "Generation Time": "2026-09-27 09:16:00"},
            },
        ]
        summaries = [
            {
                "Range Start": start, "Range End": end, "VSAT Provider": "TELSTAR-18V",
                "Spotbeam": "BEAM 11", "Current Down Sites": 2, "Peak Simultaneous Sites": 2,
                "Peak Time": datetime(2026, 9, 27, 9, 16), "Massive Down": True,
                "Sites at Peak": ["MLU00001", "MLU00002"],
            },
        ]

        with TemporaryDirectory() as directory:
            path = f"{directory}/multi-vendor.xlsx"
            save_selected_site_report(path, alarms, summaries)
            workbook = load_workbook(path, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Executive Summary", "Site Impact Massive", "Alarm Original - ZTE", "Alarm Original - Fiberhome"],
        )
        executive_sheet = workbook["Executive Summary"]
        self.assertEqual(executive_sheet["D2"].value, "Total Site ZTE")
        self.assertEqual(executive_sheet["E2"].value, 1)
        self.assertEqual(executive_sheet["D3"].value, "Total Site Fiberhome")
        self.assertEqual(executive_sheet["E3"].value, 1)
        self.assertEqual(executive_sheet["D4"].value, "Alarm Occurrence")
        executive_values = [
            str(cell.value)
            for row in workbook["Executive Summary"].iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertFalse(any("Service Incident TT" in value for value in executive_values))
        self.assertEqual(len(workbook["Executive Summary"]._charts), 0)
        impact_sites = list(workbook["Site Impact Massive"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(impact_sites), 2)

        zte_raw_headers = [cell.value for cell in workbook["Alarm Original - ZTE"][1]]
        fh_raw_headers = [cell.value for cell in workbook["Alarm Original - Fiberhome"][1]]
        self.assertIn("ME", zte_raw_headers)
        self.assertIn("Fault Source", fh_raw_headers)

        # Fiberhome raw alarms sheet should have both records (no duplicate drop)
        fh_raw_rows = list(workbook["Alarm Original - Fiberhome"].iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(fh_raw_rows), 2)

    def test_selected_summary_export_filters_pre_existing_outages_and_preserves_order(self):
        start = datetime(2026, 9, 27, 6)
        end = datetime(2026, 9, 27, 7)
        alarms = [
            # Pre-existing isolated down site from the night before (6 hours earlier)
            {
                "Vendor": "Fiberhome", "Site ID": "MLA00434", "Site Name": "SITE MLA00434",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 26, 23, 53, 30),
                "Clear Time": datetime(2026, 9, 27, 7, 10, 30), "Alarm State": "Cleared",
                "NE ID": "1001", "Alarm ID": "101",
                "_raw": {"No.": "1", "NE ID": "1001", "NE Type": "OMC", "Fault Source": "Maluku,MLA00434", "Generation Time": "09-26-2026 23:53:30"},
            },
            # Massive outage sites occurring in a tight cluster around 06:12
            {
                "Vendor": "Fiberhome", "Site ID": "MLA00105", "Site Name": "SITE MLA00105",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 6, 12, 0),
                "Clear Time": datetime(2026, 9, 27, 6, 13, 30), "Alarm State": "Cleared",
                "NE ID": "1002", "Alarm ID": "102",
                "_raw": {"No.": "2", "NE ID": "1002", "NE Type": "OMC", "Fault Source": "Maluku,MLA00105", "Generation Time": "09-27-2026 06:12:00"},
            },
            {
                "Vendor": "Fiberhome", "Site ID": "MLA00106", "Site Name": "SITE MLA00106",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 6, 10, 0),
                "Clear Time": datetime(2026, 9, 27, 6, 25, 0), "Alarm State": "Cleared",
                "NE ID": "1003", "Alarm ID": "103",
                "_raw": {"No.": "3", "NE ID": "1003", "NE Type": "OMC", "Fault Source": "Maluku,MLA00106", "Generation Time": "09-27-2026 06:10:00"},
            },
            # An unrelated alarm on MLA00106 from 10 hours ago that should not be in the massive raw export
            {
                "Vendor": "Fiberhome", "Site ID": "MLA00106", "Site Name": "SITE MLA00106",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "Power cut", "Alarm Type": "Environmental",
                "Severity": "Warning", "Occurrence Time": datetime(2026, 9, 26, 15, 0, 0),
                "Clear Time": datetime(2026, 9, 26, 16, 0, 0), "Alarm State": "Cleared",
                "NE ID": "1003", "Alarm ID": "99",
                "_raw": {"No.": "0", "NE ID": "1003", "NE Type": "OMC", "Fault Source": "Maluku,MLA00106", "Generation Time": "09-26-2026 15:00:00"},
            },
        ]
        summaries = [
            {
                "Range Start": start, "Range End": end, "VSAT Provider": "JCSAT-1C",
                "Spotbeam": "BEAM 13", "Current Down Sites": 0, "Peak Simultaneous Sites": 3,
                "Peak Time": datetime(2026, 9, 27, 6, 12, 0), "Massive Down": True,
                "Sites at Peak": ["MLA00434", "MLA00105", "MLA00106"],
            },
        ]

        with TemporaryDirectory() as directory:
            path = f"{directory}/incident_window_test.xlsx"
            save_selected_site_report(path, alarms, summaries)
            workbook = load_workbook(path, data_only=True)

        impact_sheet = workbook["Site Impact Massive"]
        impact_site_ids = [row[2] for row in impact_sheet.iter_rows(min_row=2, values_only=True)]
        # Pre-existing outage MLA00434 from 23:53 yesterday must NOT be included
        self.assertNotIn("MLA00434", impact_site_ids)
        # Sites down during the massive event (06:10 and 06:12) must be included
        self.assertEqual(impact_site_ids, ["MLA00105", "MLA00106"])

        # Check raw sheet
        raw_sheet = workbook["Alarm Original - Fiberhome"]
        raw_headers = [cell.value for cell in raw_sheet[1]]
        # Headers must follow original file sequence, NOT alphabetical
        self.assertEqual(raw_headers, ["No.", "NE ID", "NE Type", "Fault Source", "Generation Time"])

        # Raw alarms should only contain the alarms within the incident window for the massive sites
        raw_rows = list(raw_sheet.iter_rows(min_row=2, values_only=True))
        self.assertEqual(len(raw_rows), 2)
        raw_ne_ids = [r[1] for r in raw_rows]
        self.assertNotIn("1001", raw_ne_ids)  # MLA00434
        self.assertEqual(raw_ne_ids, ["1003", "1002"])  # Chronological order of 06:10 then 06:12

    def test_save_report_exports_original_vendor_sheets_with_original_order(self):
        alarms = [
            {
                "Vendor": "Fiberhome", "Site ID": "MLA00105", "Site Name": "SITE MLA00105",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 6, 12, 0),
                "Clear Time": datetime(2026, 9, 27, 6, 13, 30), "Alarm State": "Cleared",
                "NE ID": "1002", "Alarm ID": "102",
                "_raw": {"No.": "1", "NE ID": "1002", "NE Type": "OMC", "Fault Source": "Maluku,MLA00105", "Generation Time": "09-27-2026 06:12:00"},
            },
            {
                "Vendor": "ZTE", "Site ID": "MLA00200", "Site Name": "SITE MLA00200",
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Status BAPL": "BAPL",
                "Region": "MALUKU", "Alarm Name": "NE Disconnected", "Alarm Type": "Communication",
                "Severity": "Major", "Occurrence Time": datetime(2026, 9, 27, 6, 15, 0),
                "Clear Time": datetime(2026, 9, 27, 6, 20, 0), "Alarm State": "Cleared",
                "NE ID": "2001", "Alarm ID": "201",
                "_raw": {"ME": "ZZX_MLA00200", "Alarm Code Name": "NE Disconnected", "Relevancy": "1", "Resource Type": "Radio", "Occurrence Time": "2026-09-27 06:15:00"},
            },
        ]
        summaries = [
            {
                "Range Start": datetime(2026, 9, 27, 6), "Range End": datetime(2026, 9, 27, 7),
                "VSAT Provider": "JCSAT-1C", "Spotbeam": "BEAM 13", "Current Down Sites": 0,
                "Peak Simultaneous Sites": 2, "Peak Time": datetime(2026, 9, 27, 6, 15),
                "Massive Down": True, "Sites at Peak": ["MLA00105", "MLA00200"],
            },
        ]

        with TemporaryDirectory() as directory:
            path = f"{directory}/full_report.xlsx"
            save_report(path, alarms, summaries)
            workbook = load_workbook(path, data_only=True)

        self.assertEqual(
            workbook.sheetnames,
            ["Executive Summary", "Consolidated Alarms", "VSAT Summary", "Alarm Original - Fiberhome", "Alarm Original - ZTE"],
        )
        executive_values = [
            str(cell.value)
            for row in workbook["Executive Summary"].iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertFalse(any("Service Incident TT" in value for value in executive_values))
        self.assertEqual(len(workbook["Executive Summary"]._charts), 0)
        summary_rows = list(workbook["VSAT Summary"].iter_rows(values_only=True))
        self.assertEqual(summary_rows[0], tuple(SUMMARY_REPORT_COLUMNS))
        self.assertEqual(len(summary_rows), 2)  # header + 1 summary row
        fh_headers = [cell.value for cell in workbook["Alarm Original - Fiberhome"][1]]
        self.assertEqual(fh_headers, ["No.", "NE ID", "NE Type", "Fault Source", "Generation Time"])

        zte_headers = [cell.value for cell in workbook["Alarm Original - ZTE"][1]]
        self.assertEqual(zte_headers, ["ME", "Alarm Code Name", "Relevancy", "Resource Type", "Occurrence Time"])

    def test_raw_export_headers_follow_first_imported_alarm_not_chronological_sort(self):
        alarms = [
            {
                "Vendor": "ZTE",
                "Site ID": "MLU00001",
                "Occurrence Time": datetime(2026, 9, 27, 10),
                "_raw": {
                    "ME": "MLU00001",
                    "Alarm Code Name": "Down",
                    "Occurrence Time": "10:00",
                },
            },
            {
                "Vendor": "ZTE",
                "Site ID": "MLU00002",
                "Occurrence Time": datetime(2026, 9, 27, 9),
                "_raw": {
                    "Occurrence Time": "09:00",
                    "ME": "MLU00002",
                    "Alarm Code Name": "Down",
                    "Extra Source Column": "value",
                },
            },
        ]

        with TemporaryDirectory() as directory:
            path = f"{directory}/raw_order_test.xlsx"
            save_report(path, alarms, [])
            workbook = load_workbook(path, data_only=True)

        raw_sheet = workbook["Alarm Original - ZTE"]
        self.assertEqual(
            [cell.value for cell in raw_sheet[1]],
            ["ME", "Alarm Code Name", "Occurrence Time", "Extra Source Column"],
        )
        self.assertEqual(
            [row[0] for row in raw_sheet.iter_rows(min_row=2, values_only=True)],
            ["MLU00002", "MLU00001"],
        )

    def test_detects_and_normalizes_huawei_alarms_with_duration(self):
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Alarm Records -- Huawei U2000"])
        writer.writerow(["eNodeB ID", "Alarm Source", "Occurred On (NT)", "Cleared On (NT)", "Name", "Severity"])
        writer.writerow(["1037094", "MLU00499_eNodeB", "2026-09-27 09:00:00", "2026-09-27 10:30:15", "eNodeB Unavailable", "Major"])

        rows = read_table(output.getvalue().encode("utf-8-sig"), "huawei_alarm.csv")
        self.assertEqual(detect_alarm_vendor(rows), "Huawei")

        site_index = build_site_index([
            {
                "Site ID": "MLU00499",
                "Site Name": "SITE MLU00499",
                "Satellite/MW Brand": "TELSTAR-18V",
                "Spotbeam": "BEAM 11",
                "Status": "BAPL",
                "Provinsi": "MALUKU",
                "enodeb ID/enodeb ID OPSEL": "1037094",
            }
        ])
        normalized = normalize_alarms(rows, site_index, "Huawei")
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["Site ID"], "MLU00499")
        self.assertEqual(normalized[0]["Vendor"], "Huawei")
        self.assertEqual(normalized[0]["Alarm Name"], "eNodeB Unavailable")
        self.assertEqual(normalized[0]["Duration"], "1h 30m 15s")
        self.assertEqual(normalized[0]["Duration Seconds"], 5415)

    def test_format_duration_edge_cases(self):
        # Occurrence is None
        self.assertEqual(format_duration(None, datetime.now()), "-")
        # Clear time is None (still down)
        self.assertEqual(format_duration(datetime(2026, 9, 27, 10, 0), None), "Active (Masih Down)")
        # Clock skew / negative duration
        self.assertEqual(format_duration(datetime(2026, 9, 27, 10, 0), datetime(2026, 9, 27, 9, 50)), "-")
        # Sub-minute duration (< 60s)
        self.assertEqual(format_duration(datetime(2026, 9, 27, 10, 0, 0), datetime(2026, 9, 27, 10, 0, 45)), "45s")
        # Minutes without hours (< 3600s)
        self.assertEqual(format_duration(datetime(2026, 9, 27, 10, 0, 0), datetime(2026, 9, 27, 10, 15, 30)), "15m 30s")
        # Hours, minutes, seconds
        self.assertEqual(format_duration(datetime(2026, 9, 27, 10, 0, 0), datetime(2026, 9, 27, 12, 34, 56)), "2h 34m 56s")

    def test_suggested_selected_export_filename(self):
        summaries = [{
            "VSAT Provider": "TELKOMSAT",
            "Spotbeam": "BEAM 1",
            "Peak Time": datetime(2026, 9, 27, 14, 30),
        }]
        site_rows = [
            {"Site ID": "MLU00001", "VSAT Provider": "TELKOMSAT", "Paket": "1", "Area": "MALUKU"},
            {"Site ID": "MLU00002", "VSAT Provider": "TELKOMSAT", "Paket": "1", "Area": "MALUKU"},
            {"Site ID": "MLU00003", "VSAT Provider": "TELKOMSAT", "Paket": "1", "Area": "MALUKU"},
        ]
        filename = _suggested_selected_export_filename(summaries, site_rows)
        self.assertIn("3 SITES VSAT DOWN", filename)
        self.assertIn("PAKET 1", filename)
        self.assertIn("AREA MALUKU", filename)
        self.assertIn("UNDER TELKOMSAT", filename)
        self.assertIn("20260927", filename)
        self.assertTrue(filename.endswith(".xlsx"))

    def test_summarize_providers_grouped_by_spotbeam(self):
        alarms = [
            {
                "Site ID": "SITE_A",
                "Alarm Name": "NE Disconnected",
                "VSAT Provider": "TELKOMSAT",
                "Spotbeam": "BEAM 1",
                "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 10, 0),
                "Clear Time": datetime(2026, 9, 27, 10, 30),
            },
            {
                "Site ID": "SITE_B",
                "Alarm Name": "NE Disconnected",
                "VSAT Provider": "TELKOMSAT",
                "Spotbeam": "BEAM 2",
                "Alarm State": "Cleared",
                "Occurrence Time": datetime(2026, 9, 27, 10, 5),
                "Clear Time": datetime(2026, 9, 27, 10, 25),
            },
        ]
        # Grouped by spotbeam -> should have 2 distinct groups
        summaries = summarize_providers(
            alarms,
            {"NE Disconnected"},
            minimum_sites=1,
            group_by_spotbeam=True,
        )
        self.assertEqual(len(summaries), 2)
        spotbeams = {s["Spotbeam"] for s in summaries}
        self.assertEqual(spotbeams, {"BEAM 1", "BEAM 2"})


class DisplaySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def test_saved_display_settings_use_defaults_and_validate_values(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            self.assertEqual(
                _saved_scale_percent(settings), DEFAULT_SCALE_PERCENT
            )
            self.assertEqual(_saved_resolution(settings), DEFAULT_RESOLUTION)

            settings.setValue("display/scalePercent", 125)
            settings.setValue("display/resolution", "1600x900")
            self.assertEqual(_saved_scale_percent(settings), 125)
            self.assertEqual(_saved_resolution(settings), "1600x900")

            settings.setValue("display/scalePercent", 110)
            settings.setValue("display/resolution", "1111x777")
            self.assertEqual(
                _saved_scale_percent(settings), DEFAULT_SCALE_PERCENT
            )
            self.assertEqual(_saved_resolution(settings), DEFAULT_RESOLUTION)
            self.assertEqual(SCALE_OPTIONS, (100, 125, 150, 175))
            self.assertIn("1600x900", WINDOW_RESOLUTIONS)

    def test_qt_scale_factor_matches_target_scale_over_windows_dpi(self):
        self.assertEqual(_qt_scale_factor(150, 144), 1.0)
        self.assertAlmostEqual(_qt_scale_factor(125, 120), 1.0)
        self.assertAlmostEqual(_qt_scale_factor(100, 144), 2 / 3)

    def test_scale_change_relaunches_only_noc_tools_with_selected_profile(self):
        with patch("desktop_app.subprocess.Popen") as start_process:
            _relaunch_with_scale(
                "cctv", 125, "1600x900", "Apple Modern (Light)", 144
            )

        command, = start_process.call_args.args
        environment = start_process.call_args.kwargs["env"]
        self.assertEqual(environment["QT_SCALE_FACTOR"], "0.833333")
        self.assertEqual(environment["NOC_TOOLS_RESOLUTION"], "1600x900")
        self.assertEqual(environment["NOC_TOOLS_THEME"], "Apple Modern (Light)")
        self.assertEqual(environment["NOC_TOOLS_LAUNCH_APP"], "cctv")
        self.assertEqual(command[0], sys.executable)

    def test_resolution_window_is_scaled_centered_and_clamped(self):
        available = QRect(100, 50, 1920, 1040)
        geometry = _window_geometry_for_resolution(
            (1600, 900), 100, available
        )
        self.assertEqual(geometry, QRect(260, 120, 1600, 900))

        compact_screen = QRect(0, 0, 1280, 680)
        clamped = _window_geometry_for_resolution(
            (1920, 1080), 150, compact_screen
        )
        self.assertEqual(clamped, compact_screen)

    def test_launcher_places_display_controls_below_choices_side_by_side(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            with patch("desktop_app._display_settings", return_value=settings):
                dialog = AppSelectionDialog()

        layout = dialog.scale_combo.parentWidget().layout()
        self.assertIsInstance(layout, QGridLayout)
        self.assertEqual(
            layout.getItemPosition(layout.indexOf(dialog.scale_combo))[:2],
            (1, 0),
        )
        self.assertEqual(
            layout.getItemPosition(layout.indexOf(dialog.resolution_combo))[:2],
            (1, 1),
        )
        self.assertEqual(
            dialog.scale_combo.currentData(),
            DEFAULT_SCALE_PERCENT,
        )
        self.assertEqual(len(dialog.application_choice_buttons), 2)
        self.assertTrue(
            all(
                isinstance(button.graphicsEffect(), QGraphicsDropShadowEffect)
                for button in dialog.application_choice_buttons
            )
        )
        dialog.close()

    def test_startup_splash_has_an_advancing_loading_animation(self):
        splash = StartupSplash()
        initial_rotation = splash._rotation
        initial_dots = splash._loading_dots

        for _ in range(10):
            splash._advance_animation()

        self.assertNotEqual(splash._rotation, initial_rotation)
        self.assertNotEqual(splash._loading_dots, initial_dots)
        splash.close()

    def test_startup_splash_stays_until_first_window_is_shown(self):
        splash = StartupSplash()
        dismissal = _StartupSplashDismissal(splash)
        window = QMainWindow()
        splash.show()
        dismissal.start()
        self.assertTrue(dismissal._dismiss_timer.isActive())

        dismissal._check_visible_window()
        self.assertTrue(splash.isVisible())

        window.show()
        self.application.processEvents()

        dismissal._check_visible_window()
        self.assertFalse(splash.isVisible())
        self.assertFalse(dismissal._dismiss_timer.isActive())

        window.close()

    def test_closing_selected_window_triggers_launcher_callback_once(self):
        window = QMainWindow()
        callbacks = []
        return_filter = _LauncherReturnFilter(
            lambda _window: callbacks.append(True)
        )
        return_filter.set_active_window(window)

        with patch(
            "desktop_app.QTimer.singleShot",
            side_effect=lambda _delay, callback: callback(),
        ):
            window.close()
            return_filter.eventFilter(window, QEvent(QEvent.Type.Close))

        self.assertEqual(callbacks, [True])

    def test_launcher_returns_without_waiting_for_window_worker(self):
        closed_after_worker = []

        class Worker(QThread):
            def run(self):
                self.msleep(120)

        class DeferredCloseWindow(QMainWindow):
            def closeEvent(self, event):
                if self.worker.isRunning():
                    self._close_pending = True
                    self.hide()
                    event.ignore()
                    return
                closed_after_worker.append(True)
                super().closeEvent(event)

        window = DeferredCloseWindow()
        window._close_pending = False
        window.worker = Worker(window)
        callbacks = []
        return_filter = _LauncherReturnFilter(
            lambda _window: callbacks.append(True)
        )
        return_filter.set_active_window(window)

        window.worker.start()
        self.assertFalse(window.close())

        event_loop = QEventLoop()
        QTimer.singleShot(500, event_loop.quit)
        event_loop.exec()

        self.assertEqual(callbacks, [True])
        self.assertEqual(closed_after_worker, [True])
        self.assertEqual(return_filter._retired_windows, [])

    def test_standard_window_chrome_includes_native_windows_controls(self):
        window = QMainWindow()
        apply_standard_window_chrome(window)
        flags = window.windowFlags()

        for expected in (
            Qt.WindowType.Window,
            Qt.WindowType.WindowTitleHint,
            Qt.WindowType.WindowSystemMenuHint,
            Qt.WindowType.WindowMinimizeButtonHint,
            Qt.WindowType.WindowMaximizeButtonHint,
            Qt.WindowType.WindowCloseButtonHint,
        ):
            self.assertEqual(flags & expected, expected)
        self.assertFalse(flags & Qt.WindowType.FramelessWindowHint)


if __name__ == "__main__":
    unittest.main()
