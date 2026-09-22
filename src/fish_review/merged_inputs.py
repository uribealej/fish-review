"""Resolve existing merged ROI provenance without changing or merging data."""
import re

import numpy as np
import pandas as pd


def resolve_roi_map(data_path, dfof):
    """Use the canonical map or an unambiguous, independently verified archive."""
    canonical = data_path.with_name(data_path.stem + "_map.csv")
    if dfof.ndim != 2:
        raise ValueError(f"Merged array must be time x neurons; found shape {dfof.shape}.")

    def valid_columns(mapping):
        return len(mapping) == dfof.shape[1] and "global_col" in mapping and np.array_equal(
            np.sort(mapping["global_col"].to_numpy()), np.arange(dfof.shape[1]))

    mapping = pd.read_csv(canonical)
    if valid_columns(mapping):
        return canonical, mapping, []
    problem = (f"Merged array has {dfof.shape[1]} neurons, but {canonical.name} has "
               f"{len(mapping)} rows or invalid global_col indices.")
    ids_path = data_path.with_name(data_path.stem + "_filtered_roi_indices.npy")
    if not ids_path.is_file():
        raise ValueError(problem + " No merged ROI indices are available to verify an archived map.")
    ids = np.load(ids_path, allow_pickle=False)
    matches = []
    required = {"plane", "roi_index_in_plane", "filtered_roi_index", "source_dfof_file"}
    for path in sorted(canonical.parent.glob(canonical.stem + "_*.csv")):
        if not re.fullmatch(re.escape(canonical.stem) + r"_\d{8}_\d{6}\.csv", path.name):
            continue
        candidate = pd.read_csv(path)
        if not valid_columns(candidate) or not required.issubset(candidate.columns):
            continue
        candidate = candidate.sort_values("global_col").reset_index(drop=True)
        if not np.array_equal(candidate.filtered_roi_index.to_numpy(), ids):
            continue
        evidence = [ids_path]
        verified = True
        for plane, group in candidate.groupby("plane", sort=False):
            filenames = group.source_dfof_file.unique()
            if not re.fullmatch(r"plane\d+", str(plane)) or len(filenames) != 1:
                verified = False
                break
            # Archived exports use filenames relative to each plane's dFoF folder.
            filename = str(filenames[0])
            if "/" in filename or "\\" in filename:
                verified = False
                break
            source = data_path.parent.parent / plane / "dFoF" / filename
            if not source.is_file():
                verified = False
                break
            original = np.load(source, mmap_mode="r", allow_pickle=False)
            local = group.roi_index_in_plane.to_numpy()
            if (original.ndim != 2 or original.shape[0] < dfof.shape[0]
                    or not np.issubdtype(local.dtype, np.integer)
                    or (local < 0).any() or (local >= original.shape[1]).any()
                    or group.roi_index_in_plane.duplicated().any()):
                verified = False
                break
            for start in range(0, len(group), 128):
                columns = group.iloc[start:start + 128]
                if not np.array_equal(dfof[:, columns.global_col],
                                      original[:dfof.shape[0], columns.roi_index_in_plane],
                                      equal_nan=True):
                    verified = False
                    break
            if not verified:
                break
            evidence.append(source)
        if verified:
            matches.append((path, candidate, evidence))
    if not matches:
        raise ValueError(problem + " No archived map could be verified against ROI indices and per-plane traces.")
    identity = ["global_col", "plane", "roi_index_in_plane", "filtered_roi_index"]
    if any(not candidate[identity].equals(matches[0][1][identity]) for _, candidate, _ in matches[1:]):
        raise ValueError(problem + " Multiple different archived maps match; resolve the ambiguity before plotting.")
    return matches[0]
