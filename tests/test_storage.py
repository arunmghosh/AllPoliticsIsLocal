"""Tests for Excel persistence, historical appending, results archival, and data wiping."""

import os
import random
import tempfile
import unittest

from openpyxl import load_workbook

from constants import HISTORICAL_HEADERS, SENIORITY_HEADERS, TIER_CITY_COUNCIL
from custom_types import Candidate
from data_tracker import (
    append_historical_row,
    load_party_names,
    read_historical_data,
    read_seniority_data,
    run_historical_simulation,
    save_results,
    wipe_data,
    write_seniority_data,
)
from simulator import build_nation


class TestStorage(unittest.TestCase):
    """Verify Excel schemas, dynamic row updates, archival, and cleanup."""

    def test_historical_xlsx_write_append_and_read(self):
        rng = random.Random(51)
        nation = build_nation(
            "StoreNation", ["Economy", "Healthcare"], load_party_names(), rng=rng
        )
        with tempfile.TemporaryDirectory() as tmp:
            hist_path = os.path.join(tmp, "data", "historical_data.xlsx")
            rows, _ = run_historical_simulation(
                nation=nation,
                home_state=2,
                home_city=4,
                home_district=10,
                num_cycles=12,
                filepath=hist_path,
                rng=rng,
            )
            self.assertEqual(len(rows), 12)
            self.assertTrue(os.path.exists(hist_path))

            wb = load_workbook(hist_path)
            ws = wb.active
            header_row = [cell.value for cell in ws[1]]
            self.assertEqual(header_row, HISTORICAL_HEADERS)

            loaded = read_historical_data(hist_path)
            self.assertEqual(len(loaded), 12)
            for idx, r in enumerate(loaded, start=1):
                self.assertEqual(r["Cycle"], idx)
                for col in HISTORICAL_HEADERS[1:]:
                    self.assertIn(r[col], range(len(nation.parties)))

            # Append cycle 13
            new_row = dict(loaded[-1])
            new_row["Cycle"] = 13
            append_historical_row(new_row, filepath=hist_path)
            loaded2 = read_historical_data(hist_path)
            self.assertEqual(len(loaded2), 13)
            self.assertEqual(loaded2[-1]["Cycle"], 13)

    def test_seniority_xlsx_schema_and_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            sen_path = os.path.join(tmp, "data", "seniority.xlsx")
            cands = [
                Candidate(
                    name="Alpha One",
                    party_index=0,
                    platform=[0.25],
                    tier=TIER_CITY_COUNCIL,
                    seniority=0,
                    victory_size=54.321,
                ),
                Candidate(
                    name="Beta Two",
                    party_index=0,
                    platform=[0.30],
                    tier=2,
                    seniority=6,
                    victory_size=0.0,
                ),
            ]
            write_seniority_data(cands, filepath=sen_path)
            wb = load_workbook(sen_path)
            ws = wb.active
            self.assertEqual([cell.value for cell in ws[1]], SENIORITY_HEADERS)

            loaded = read_seniority_data(sen_path)
            self.assertEqual(len(loaded), 2)
            # Sorted by Level of Office ascending (tier 2 before tier 7)
            self.assertEqual(loaded[0]["Name"], "Beta Two")
            self.assertEqual(loaded[0]["Level of Office"], 2)
            self.assertEqual(loaded[0]["Seniority"], 6)
            self.assertEqual(loaded[0]["Victory Size"], 0)
            self.assertEqual(loaded[1]["Name"], "Alpha One")
            self.assertAlmostEqual(loaded[1]["Victory Size"], 54.32, places=2)

    def test_save_results_moves_files_and_wipes_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")
            os.makedirs(data_dir, exist_ok=True)

            hist_path = os.path.join(data_dir, "historical_data.xlsx")
            sen_path = os.path.join(data_dir, "seniority.xlsx")
            with open(hist_path, "w", encoding="utf-8") as f:
                f.write("hist")
            with open(sen_path, "w", encoding="utf-8") as f:
                f.write("sen")

            dest1 = save_results(
                data_dir=data_dir, results_dir=results_dir, timestamp="2026-11-11_12-00-00"
            )
            self.assertEqual(os.listdir(data_dir), [])
            self.assertTrue(os.path.exists(os.path.join(dest1, "historical_data.xlsx")))
            self.assertTrue(os.path.exists(os.path.join(dest1, "seniority.xlsx")))

            # Second save with same timestamp must not overwrite first
            with open(hist_path, "w", encoding="utf-8") as f:
                f.write("hist2")
            dest2 = save_results(
                data_dir=data_dir, results_dir=results_dir, timestamp="2026-11-11_12-00-00"
            )
            self.assertNotEqual(dest1, dest2)
            self.assertTrue(os.path.exists(os.path.join(dest2, "historical_data.xlsx")))
            self.assertEqual(os.listdir(data_dir), [])

            # Wipe removes files and subdirectories
            subdir = os.path.join(data_dir, "nested")
            os.makedirs(subdir, exist_ok=True)
            with open(os.path.join(subdir, "f.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            wipe_data(data_dir)
            self.assertEqual(os.listdir(data_dir), [])


if __name__ == "__main__":
    unittest.main()

