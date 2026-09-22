"""Validate stimulus ordering, original trial numbering and lossless raw-F export."""
import base64
import gzip
import json
import re
import sys
import unittest
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fish_review.stimulus_order import parse_stimulus_order
from fish_review.plot_generation import pipeline_module


class ScientificViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = ROOT.parent / "calcium-imaging-pipeline"

    def test_order_codes_and_validation(self):
        catalog = [{"Number": 1, "Letter": "A", "Stimulus": "Left"},
                   {"Number": 2, "Letter": "B", "Stimulus": "Right"},
                   {"Number": 3, "Letter": "C", "Stimulus": "Control"}]
        self.assertEqual(parse_stimulus_order("3, A, Right", catalog), ["Control", "Left", "Right"])
        self.assertEqual(parse_stimulus_order("c b a", catalog), ["Control", "Right", "Left"])
        with self.assertRaisesRegex(ValueError, "repeated"):
            parse_stimulus_order("1, 1, 2", catalog)
        with self.assertRaisesRegex(ValueError, "missing"):
            parse_stimulus_order("1, 2", catalog)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            parse_stimulus_order("0, 1, 2", catalog)

    def test_boundary_drop_preserves_original_repetition_numbers(self):
        helper = pipeline_module(self.pipeline, "stimulus_analysis")
        values = np.arange(30, dtype=float)[:, None]
        trace = np.zeros(30, dtype=int)
        trace[[0, 10, 20]] = 1
        aligned = helper.build_trial_aligned_traces(values, trace, {"S": 1}, 1, 2, 4)
        self.assertEqual(aligned["retained_repetitions"]["S"], [2, 3])
        np.testing.assert_array_equal(aligned["trial_traces"]["S"][0, :, 0], np.arange(8, 14))

    def test_repetition_plot_keeps_trials_separate_and_scale_shared(self):
        helper = pipeline_module(self.pipeline, "review_plots")
        trials = np.array([[[1, 4], [2, 5]], [[3, 6], [4, 7]]], dtype=float)
        names = ["S1", "S2"]
        figure, panels = helper.plot_repetition_responses(
            {name: trials for name in names}, {name: [1, 2] for name in names}, names,
            {name: {"static_before_sec": 0} for name in names}, 0, 1, "Test",
            neuron_order=np.array([1, 0]), stimuli_per_row=1)
        try:
            expected = np.concatenate([trials[:, :, 0], trials[:, :, 1]], axis=1)[[1, 0]]
            np.testing.assert_array_equal(panels[0][0].images[0].get_array(), expected)
            self.assertEqual(panels[0][0].images[0].get_clim(), panels[1][0].images[0].get_clim())
        finally:
            plt.close(figure)

    def test_raw_f_html_preserves_samples_labels_and_precision(self):
        helper = pipeline_module(self.pipeline, "fluorescence_review")
        values = np.array([[1.125, 2, np.nan], [-8, 5.5, 9]], dtype=np.float32)
        content = helper.fluorescence_html(
            [{"name": "plane0", "fluorescence": values, "labels": np.array([1, 0]), "fps": 2}], "Test")
        payload = json.loads(re.search(r'<script id="trace-data" type="application/json">(.*?)</script>',
                                       content, re.S).group(1))
        plane = payload["planes"][0]
        restored = np.frombuffer(gzip.decompress(base64.b64decode(plane["data"])), dtype="<f4").reshape(values.shape)
        np.testing.assert_array_equal(restored, values)
        self.assertEqual(plane["labels"], [1, 0])
        self.assertEqual(plane["fps"], 2)
        self.assertNotIn("https://", content)
