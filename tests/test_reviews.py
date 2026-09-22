"""Persistence and export regression tests using disposable synthetic fish only."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fish_review.inventory import Fish, load_inventory
from fish_review.detection import scan_fish
from fish_review.reviews import load_review, save_review, review_path
from fish_review.summaries import export_summaries


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.experiment = self.root / "2p_derived/Exp_test"
        self.experiment.mkdir(parents=True)
        self.fish = Fish("Test_f01", "Exp_test", self.root / "2p/Test_f01", self.experiment)
        (self.fish.source / "01_raw/2p/metadata").mkdir(parents=True)
        (self.experiment / "experiment_metadata.yaml").write_text(
            "experiment_id: Exp_test\nfish:\n"
            "  - {fish_id: Test_f01, source_folder: ../../2p/Test_f01}\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_strong_drift_is_not_automatic_exclusion(self):
        record, token = load_review(self.fish)
        record["manual"]["imaging_qc"]["z_drift"]["assessment"] = "Strong"
        saved, _ = save_review(self.fish, record["manual"], scan_fish(self.fish), token)
        self.assertEqual(saved["manual"]["decision"]["status"], "undecided")

    def test_preserve_unknown_fields_and_reject_stale_writer(self):
        record, token = load_review(self.fish)
        record["manual"]["comment"] = "First review"
        saved, token = save_review(self.fish, record["manual"], scan_fish(self.fish), token)
        saved["external_annotation"] = {"keep": True}
        saved["manual"]["future_field"] = "keep this too"
        review_path(self.fish).write_text(yaml.safe_dump(saved), encoding="utf-8")
        loaded, current_token = load_review(self.fish)
        manual = copy.deepcopy(loaded["manual"])
        manual["comment"] = "Changed"
        with self.assertRaisesRegex(ValueError, "changed elsewhere"):
            save_review(self.fish, manual, scan_fish(self.fish), token)
        written, _ = save_review(self.fish, manual, scan_fish(self.fish), current_token)
        self.assertTrue(written["external_annotation"]["keep"])
        self.assertEqual(written["manual"]["future_field"], "keep this too")
        self.assertEqual(written["history"][-1]["manual"]["comment"], "First review")

    def test_export_preserves_review_and_displays_reason_comment(self):
        record, token = load_review(self.fish)
        manual = record["manual"]
        manual["decision"] = {"status": "exclude", "reason": "Strong Z-drift"}
        manual["progress"] = {"state": "finished", "stage": "Final decision"}
        manual["decision"]["stage"] = "Imaging QC"
        manual["comment"] = "Visible <comment>"
        save_review(self.fish, manual, scan_fish(self.fish), token)
        before = review_path(self.fish).read_bytes()
        experiments = {"Exp_test": [self.fish]}
        rows, errors = export_summaries(experiments, self.root / "2p_derived")
        self.assertFalse(errors)
        self.assertEqual(before, review_path(self.fish).read_bytes())
        self.assertIn("Imaging QC", rows[0]["Decision / reason"])
        self.assertEqual(rows[0]["Fish comment"], "Visible <comment>")
        for path in [self.experiment / "fish/Test_f01.html",
                     self.experiment / "experiment_overview.html",
                     self.root / "2p_derived/global/overview.html"]:
            text = path.read_text()
            self.assertIn("Strong Z-drift", text)
            self.assertIn("Visible &lt;comment&gt;", text)

    def test_ui_save_exclude_and_reopen(self):
        from streamlit.testing.v1 import AppTest
        config = self.root / "config.json"
        config.write_text(json.dumps({"derived_root": str(self.root / "2p_derived"),
                                     "pipeline_root": str(ROOT.parent / "calcium-imaging-pipeline")}))
        with patch.dict(os.environ, {"FISH_REVIEW_CONFIG": str(config)}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
            self.assertFalse(app.exception)
            next(w for w in app.selectbox if w.label == "Z-drift").select("Strong").run()
            next(w for w in app.text_area if w.label == "Fish comment").set_value("Test comment").run()
            next(w for w in app.text_input if w.label == "Decision reason").set_value("Strong Z-drift").run()
            next(w for w in app.selectbox if w.label == "Final decision").select("exclude").run()
            next(w for w in app.selectbox if w.label == "Where was the reason for exclusion identified?").select("Imaging QC").run()
            next(w for w in app.button if w.label == "Finish review").click().run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
            saved, _ = load_review(self.fish)
            self.assertEqual(saved["manual"]["decision"]["status"], "exclude")
            self.assertEqual(saved["manual"]["decision"]["stage"], "Imaging QC")
            reopened = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
            self.assertFalse(reopened.exception)
            self.assertEqual(next(w for w in reopened.text_area if w.label == "Fish comment").value,
                             "Test comment")
            self.assertEqual(next(w for w in reopened.selectbox if w.label == "Z-drift").value, "Strong")

    def test_draft_survives_fish_navigation_without_writing(self):
        from streamlit.testing.v1 import AppTest
        other = self.root / "2p/Test_f02/01_raw/2p/metadata"
        other.mkdir(parents=True)
        inventory = self.experiment / "experiment_metadata.yaml"
        inventory.write_text(inventory.read_text() +
                             "  - {fish_id: Test_f02, source_folder: ../../2p/Test_f02}\n")
        config = self.root / "config.json"
        config.write_text(json.dumps({"derived_root": str(self.root / "2p_derived"),
                                     "pipeline_root": str(ROOT.parent / "calcium-imaging-pipeline")}))
        with patch.dict(os.environ, {"FISH_REVIEW_CONFIG": str(config)}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
            next(w for w in app.text_area if w.label == "Fish comment").set_value("Unsubmitted draft").run()
            next(w for w in app.button if w.label == "Next fish").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(next(w for w in app.text_area if w.label == "Fish comment").value, "")
            next(w for w in app.button if w.label == "Previous fish").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(next(w for w in app.text_area if w.label == "Fish comment").value,
                             "Unsubmitted draft")
            self.assertFalse(review_path(self.fish).exists())

    def test_legacy_exclusion_migrates_without_changing_file(self):
        record, _ = load_review(self.fish)
        record["schema_version"] = 1
        record["manual"].pop("progress")
        record["manual"]["decision"] = {"status": "exclude", "reason": "Original reason"}
        record["manual"]["stop"] = {"state": "excluded", "stage": "Imaging QC", "comment": "Original stop"}
        review_path(self.fish).write_text(yaml.safe_dump(record), encoding="utf-8")
        original = review_path(self.fish).read_bytes()
        migrated, _ = load_review(self.fish)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["manual"]["progress"]["state"], "finished")
        self.assertEqual(migrated["manual"]["decision"]["stage"], "Imaging QC")
        self.assertEqual(migrated["manual"]["decision"]["reason"], "Original reason")
        self.assertEqual(review_path(self.fish).read_bytes(), original)

    def test_pause_and_resume_do_not_change_decision(self):
        from fish_review.reviews import apply_review_action
        record, _ = load_review(self.fish)
        manual = record["manual"]
        manual["decision"]["status"] = "exclude"
        manual["decision"]["stage"] = "Responses"
        paused = apply_review_action(manual, "pause", "Responses")
        self.assertEqual(paused["progress"]["state"], "paused")
        self.assertEqual(paused["decision"]["status"], "exclude")
        resumed = apply_review_action(paused, "resume")
        self.assertEqual(resumed["progress"]["state"], "in_progress")
        self.assertEqual(resumed["decision"]["status"], "exclude")

    def test_locked_csv_does_not_block_html_or_global_exports(self):
        from fish_review.summaries import write_overview
        from fish_review.reviews import atomic_write
        def selective_write(path, content):
            if Path(path).suffix == ".csv":
                raise PermissionError("Simulated open CSV")
            atomic_write(path, content)
        with patch("fish_review.summaries.atomic_write", side_effect=selective_write):
            errors = write_overview(self.experiment, "experiment_overview", "Test", [{"Fish": "Test_f01"}])
        self.assertEqual(len(errors), 1)
        self.assertTrue((self.experiment / "experiment_overview.html").is_file())
