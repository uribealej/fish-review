"""Contract checks for inventory paths, partial outputs, and inaccessible sources."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fish_review.inventory import Fish, load_inventory
from fish_review.detection import scan_fish, summary_row


class DetectionTests(unittest.TestCase):
    def test_existing_late_outputs_do_not_imply_raw_or_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fish = Fish("L1_f01", "Exp_1", root / "fish", root / "derived" / "Exp_1")
            merged = fish.source / "03_analysis/functional/suite2P/merged_dFoF"
            merged.mkdir(parents=True)
            (merged / "L1_f01_dFoF_merged.npy").touch()
            result = scan_fish(fish)
            states = {item["item"]: item["status"] for item in result["items"]}
            self.assertNotIn("Raw imaging", states)
            self.assertEqual(states["Merged delta F/F"], "Present")
            self.assertEqual(summary_row(fish, result)["Decision / reason"], "Undecided")
            self.assertFalse((fish.source / "01_raw").exists())

    def test_unreachable_source_is_not_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            fish = Fish("L1_f01", "Exp_1", Path(temporary) / "absent", Path(temporary))
            result = scan_fish(fish)
            self.assertIsNotNone(result["error"])
            self.assertEqual(summary_row(fish, result)["Source"], "Could not verify")

    def test_inventory_resolves_paths_and_warns_on_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exp = root / "derived/Exp_1"
            exp.mkdir(parents=True)
            (exp / "experiment_metadata.yaml").write_text(
                "experiment_id: Exp_1\nfish:\n"
                "  - {fish_id: L1_f01, source_folder: ../../2p/Fish1}\n"
                "  - {fish_id: L1_f01, source_folder: ../../2p/Fish2}\n", encoding="utf-8")
            experiments, warnings = load_inventory(root / "derived")
            self.assertEqual(experiments["Exp_1"][0].source, (root / "2p/Fish1").resolve())
            self.assertEqual(len(experiments["Exp_1"]), 1)
            self.assertIn("Duplicate", warnings[0])

    def test_empty_plane_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fish = Fish("L1_f01", "Exp_1", root / "fish", root / "derived")
            (fish.source / "03_analysis/functional/suite2P/plane0").mkdir(parents=True)
            result = scan_fish(fish)
            self.assertEqual(result["planes"][0]["F"], "Not found here")
