"""Rapid end-to-end integration smoke tests without mocking core simulation logic."""

import os
import random
import tempfile
import unittest

import numpy as np

from data_tracker import read_historical_data, read_seniority_data
import runner


class TestSmoke(unittest.TestCase):
    """End-to-end integration smoke tests across the full game pipeline."""

    def test_end_to_end_real_pipeline_1_issue_with_save(self):
        outputs: list[str] = []

        def smart_input(prompt: str) -> str:
            low = prompt.lower()
            if "name for your nation" in low:
                return "SmokeRepublic"
            if "how many political issues" in low:
                return "1"
            if "issue 1/1" in low:
                return "1"
            if "candidate name" in low:
                return "Smoke Candidate"
            if "home state" in low:
                return "1"
            if "home city" in low:
                return "1"
            if "home district" in low:
                return "1"
            if "simulate prior historical" in low:
                return "y"
            if "how many cycles to simulate" in low:
                return "5"
            if "0.01-0.49 or 0.51-0.99" in low:
                return "0.25"
            if "tweak your platform" in low:
                return "n"
            if "batch " in low:
                return ""
            if "save the simulation spreadsheets" in low:
                return "y"
            raise AssertionError(f"Unexpected prompt: {prompt}")

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")

            outcome = runner.run_single_game(
                raw_input_fn=smart_input,
                output_fn=outputs.append,
                data_dir=data_dir,
                results_dir=results_dir,
                rng=random.Random(2026),
                np_rng=np.random.default_rng(2026),
            )

            self.assertIn(outcome, ("won", "lost_election", "lost_timeout"))
            self.assertEqual(os.listdir(data_dir), [])

            saved_folders = os.listdir(results_dir)
            self.assertEqual(len(saved_folders), 1)
            export_dir = os.path.join(results_dir, saved_folders[0])

            hist_path = os.path.join(export_dir, "historical_data.xlsx")
            sen_path = os.path.join(export_dir, "seniority.xlsx")
            self.assertTrue(os.path.exists(hist_path))
            self.assertTrue(os.path.exists(sen_path))

            hist_rows = read_historical_data(hist_path)
            # 5 historical cycles + at least 1 live gameplay cycle
            self.assertGreaterEqual(len(hist_rows), 6)
            sen_rows = read_seniority_data(sen_path)
            self.assertIsInstance(sen_rows, list)

            joined_out = "\n".join(outputs)
            self.assertIn("HISTORICAL ELECTION DATA", joined_out)
            self.assertIn("ELECTION NIGHT LIVE: Batch 1/10", joined_out)
            self.assertIn("ELECTION NIGHT LIVE: Batch 10/10", joined_out)
            self.assertIn("FINAL CALLED ELECTION RESULTS", joined_out)

    def test_end_to_end_3_issues_8_parties_tweak_and_discard(self):
        outputs: list[str] = []

        def smart_input(prompt: str) -> str:
            low = prompt.lower()
            if "name for your nation" in low:
                return "OctoLand"
            if "how many political issues" in low:
                return "3"
            if "issue 1/3" in low:
                return "1"
            if "issue 2/3" in low:
                return "2"
            if "issue 3/3" in low:
                return "Custom Tax Policy"
            if "candidate name" in low:
                return "Octo Player"
            if "home state" in low:
                return "5"
            if "home city" in low:
                return "3"
            if "home district" in low:
                return "12"
            if "simulate prior historical" in low:
                return "n"
            if "economic policy (0.01-0.49" in low:
                return "0.30"
            if "social policy (0.01-0.49" in low:
                return "0.70"
            if "custom tax policy (0.01-0.49" in low:
                return "0.40"
            if "tweak your platform" in low:
                return "y"
            if "range 0.01-0.49" in low:
                return "0.35"
            if "range 0.51-0.99" in low:
                return ""
            if "batch " in low:
                return ""
            if "save the simulation spreadsheets" in low:
                return "n"
            raise AssertionError(f"Unexpected prompt: {prompt}")

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            results_dir = os.path.join(tmp, "results")

            outcome = runner.run_single_game(
                raw_input_fn=smart_input,
                output_fn=outputs.append,
                data_dir=data_dir,
                results_dir=results_dir,
                rng=random.Random(999),
                np_rng=np.random.default_rng(999),
            )
            self.assertIn(outcome, ("won", "lost_election", "lost_timeout"))
            self.assertEqual(os.listdir(data_dir), [])
            self.assertFalse(os.path.exists(results_dir) and os.listdir(results_dir))


if __name__ == "__main__":
    unittest.main()

