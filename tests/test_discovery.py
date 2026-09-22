import sys
import tempfile
import unittest
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fish_review.discovery import add_discovered_fish, inventory_changes, SKELETON
from fish_review.inventory import load_inventory

class DiscoveryTests(unittest.TestCase):
    def test_create_append_preserve_and_exact_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "2p"
            source.mkdir()
            derived = root / "2p_derived"
            exp = "Exp_8_accumulation_ev"
            fish = source / ("L800_f08_" + exp)
            fish.mkdir()
            (source / ("L800_f09_" + exp + "_other")).mkdir()
            review = fish / "fish_review.yaml"
            review.write_bytes(b"manual answers must survive")
            self.assertEqual(add_discovered_fish(source, derived, exp), ["L800_f08"])
            for name in SKELETON:
                self.assertTrue((derived / exp / name).is_dir())
            inventories, warnings = load_inventory(derived)
            self.assertFalse(warnings)
            self.assertEqual(inventories[exp][0].source, fish.resolve())
            metadata = derived / exp / "experiment_metadata.yaml"
            data = yaml.safe_load(metadata.read_text())
            data["custom"] = {"keep": True}
            data["fish"][0]["notes"] = "preserve"
            metadata.write_text(yaml.safe_dump(data))
            before = metadata.read_bytes()
            self.assertEqual(add_discovered_fish(source, derived, exp), [])
            self.assertEqual(metadata.read_bytes(), before)
            (source / ("L800_f10_" + exp)).mkdir()
            self.assertEqual(add_discovered_fish(source, derived, exp), ["L800_f10"])
            updated = yaml.safe_load(metadata.read_text())
            self.assertEqual(updated["custom"], data["custom"])
            self.assertEqual(updated["fish"][0], data["fish"][0])
            self.assertEqual(review.read_bytes(), b"manual answers must survive")

    def test_invalid_empty_and_conflicting_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "2p"
            source.mkdir()
            derived = root / "derived"
            for exp in ("../escape", "Exp_99_empty"):
                with self.assertRaises(ValueError):
                    add_discovered_fish(source, derived, exp)
            self.assertFalse(derived.exists())
            (source / "L1_f01_Exp_1_test").mkdir()
            add_discovered_fish(source, derived, "Exp_1_test")
            (source / "L1_f01_Exp_2_test").mkdir()
            with self.assertRaisesRegex(ValueError, "another experiment"):
                add_discovered_fish(source, derived, "Exp_2_test")
            self.assertFalse((derived / "Exp_2_test").exists())
