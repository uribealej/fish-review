"""Verify archived ROI map recovery without modifying scientific inputs."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fish_review.merged_inputs import resolve_roi_map


class MergedInputTests(unittest.TestCase):
    def test_verified_archive_and_mismatched_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "merged_dFoF"
            folder.mkdir()
            source = root / "plane0/dFoF"
            source.mkdir(parents=True)
            data = np.arange(12.0).reshape(4, 3)
            path = folder / "fish_dFoF_merged.npy"
            np.save(path, data)
            np.save(source / "fish_dFoF.npy", data)
            np.save(folder / "fish_dFoF_merged_filtered_roi_indices.npy", [2, 5, 9])
            mapping = pd.DataFrame(dict(plane=["plane0"] * 3,
                roi_index_in_plane=[0, 1, 2], filtered_roi_index=[2, 5, 9],
                global_col=[0, 1, 2], source_dfof_file=["fish_dFoF.npy"] * 3))
            canonical = folder / "fish_dFoF_merged_map.csv"
            mapping.iloc[:2].to_csv(canonical, index=False)
            first = folder / "fish_dFoF_merged_map_20251028_133419.csv"
            second = folder / "fish_dFoF_merged_map_20251028_142035.csv"
            mapping.to_csv(first, index=False)
            mapping.to_csv(second, index=False)
            selected, result, evidence = resolve_roi_map(path, data)
            self.assertEqual(selected, first)
            self.assertEqual(len(result), 3)
            self.assertIn(source / "fish_dFoF.npy", evidence)
            self.assertEqual(len(pd.read_csv(canonical)), 2)
            np.save(source / "fish_dFoF.npy", data + 1)
            with self.assertRaisesRegex(ValueError, "No archived map could be verified"):
                resolve_roi_map(path, data)
            mapping.to_csv(canonical, index=False)
            self.assertEqual(resolve_roi_map(path, data)[0], canonical)

    def test_reject_non_matrix(self):
        with self.assertRaisesRegex(ValueError, "time x neurons"):
            resolve_roi_map(Path("unused.npy"), np.zeros(3))
