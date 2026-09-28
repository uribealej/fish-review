"""Check timing defaults and experiment-scoped order navigation."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fish_review.inventory import Fish
from fish_review.plot_generation import plotting_defaults


class ResponseSettingsTests(unittest.TestCase):
    def test_separate_stimulus_root_after_moving_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fish = Fish("f1", "exp", root / "data/2p/f1", root / "paper/2p_derived/exp")
            parameters = root / "data/stimuli/exp/parameters/experiment_parameters.csv"
            parameters.parent.mkdir(parents=True)
            parameters.write_text("framerate\n30\n")
            settings = plotting_defaults(fish, {"framerate": "2"}, fish.experiment_dir.parent,
                                         stimuli_root=root / "data/stimuli")
            self.assertEqual(Path(settings["stimuli_dir"]), parameters.parent.parent)
            self.assertEqual(settings["stimulus_fps"], 30.0)

    def test_stimulus_rate_fallback_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fish = Fish("f1", "exp", root / "source", root / "derived/exp")
            def rate():
                result = plotting_defaults(fish, {"framerate": "2"}, root / "derived")
                self.assertEqual(result["imaging_fps"], 2.0)
                return result["stimulus_fps"]
            self.assertEqual(rate(), 60.0)
            parameters = root / "stimuli/exp/parameters/experiment_parameters.csv"
            parameters.parent.mkdir(parents=True)
            for contents, expected in [("framerate\n30\n30\n", 30.0),
                                       ("other\n1\n", 60.0),
                                       ("framerate\nunknown\n", 60.0),
                                       ("framerate\n30\n60\n", None)]:
                parameters.write_text(contents)
                self.assertEqual(rate(), expected)

    def test_order_survives_fish_and_experiment_navigation(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('''
from pathlib import Path
from unittest.mock import patch
import streamlit as st
from fish_review.inventory import Fish
from fish_review.ui import response_settings
experiment = st.selectbox("Experiment", ["exp1", "exp2"])
fish_id = st.selectbox("Fish", ["f1", "f2"])
fish = Fish(fish_id, experiment, Path("unused"), Path("unused") / experiment)
defaults = dict(stimuli_dir="", selected_blocks=["B1"], imaging_fps=2.0,
                stimulus_fps=60.0, frames_per_block=100, pre_stimulus_sec=5.0,
                post_stimulus_sec=27.0, sort_by_correlation=True, stimulus_order=None)
catalog = [{"Number": 1, "Letter": "A", "Stimulus": "Left"},
           {"Number": 2, "Letter": "B", "Stimulus": "Right"}]
with patch("fish_review.ui.plotting_defaults", return_value=defaults), \\
     patch("fish_review.ui.stimulus_catalog", return_value=catalog):
    result = response_settings(fish, {"metadata": {}}, {"derived_root": "unused"}, experiment + fish_id)
    st.session_state["result"] = result
''').run()
        def order_input():
            return next(widget for widget in app.text_input if widget.label.startswith("Plot order:"))
        order_input().set_value("2, 1").run()
        app.selectbox[1].select("f2").run()
        self.assertEqual(app.session_state["result"]["stimulus_order"], ["Right", "Left"])
        app.selectbox[0].select("exp2").run()
        self.assertEqual(app.session_state["result"]["stimulus_order"], ["Left", "Right"])
        app.selectbox[0].select("exp1").run()
        self.assertEqual(app.session_state["result"]["stimulus_order"], ["Right", "Left"])
        order_input().set_value("1, 1").run()
        self.assertIsNone(app.session_state["result"])
        app.selectbox[0].select("exp2").run()
        app.selectbox[0].select("exp1").run()
        self.assertEqual(app.session_state["result"]["stimulus_order"], ["Right", "Left"])
        self.assertFalse(app.exception)
