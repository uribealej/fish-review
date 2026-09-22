"""Connect existing Suite2p and merged traces to pipeline-owned figure helpers."""
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fish_review.reviews import atomic_write, now
from fish_review.merged_inputs import resolve_roi_map


def pipeline_module(pipeline_root, name):
    """Load an explicit helper file, avoiding collisions between repositories' src packages."""
    path = Path(pipeline_root) / "src" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"review_pipeline_{name}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load pipeline helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def signature(path):
    """Record file identity and modification evidence without loading large arrays."""
    path = Path(path)
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def code_versions(pipeline_root):
    """Hash the exact local helper source used to generate plots."""
    result = {}
    for name in ("stimulus_analysis", "plotting", "review_plots"):
        path = Path(pipeline_root) / "src" / f"{name}.py"
        result[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["adapter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


def atomic_figure(figure, path):
    """Write a complete PNG before replacing the named generated figure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".png", dir=path.parent)
    os.close(handle)
    try:
        figure.savefig(temporary, dpi=180, bbox_inches="tight", facecolor="white")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def plane_file(folder, fish_id, name):
    """Resolve either canonical Suite2p naming or the fish-prefixed variant."""
    choices = [folder / f"{fish_id}_{folder.name}_{name}.npy", folder / f"{name}.npy"]
    found = [path for path in choices if path.is_file()]
    if len(found) != 1:
        raise ValueError(f"Expected exactly one {name} file in {folder}; found {len(found)}.")
    return found[0]


def generate_segmentation(fish, pipeline_root):
    """Save an all-plane montage, per-plane counts and source provenance."""
    suite = fish.source / "03_analysis/functional/suite2P"
    folders = sorted((path for path in suite.iterdir() if re.fullmatch(r"plane\d+", path.name)),
                     key=lambda path: int(path.name[5:]))
    planes, sources = [], []
    for folder in folders:
        stat_path = plane_file(folder, fish.fish_id, "stat")
        label_path = plane_file(folder, fish.fish_id, "iscell")
        try:
            image_path = plane_file(folder, fish.fish_id, "ops")
        except ValueError:
            image_path = plane_file(folder, fish.fish_id, "reg_outputs")
        # These object arrays are the user's trusted local Suite2p outputs.
        ops = np.load(image_path, allow_pickle=True).item()
        image_key = next((key for key in ("meanImg", "refImg") if key in ops), None)
        if image_key is None:
            raise ValueError(f"No reference image in {image_path}")
        image = np.array(ops[image_key], copy=True)
        del ops
        stats = np.load(stat_path, allow_pickle=True)
        labels = np.load(label_path, allow_pickle=False)
        if labels.ndim != 2 or labels.shape[1] < 1:
            raise ValueError(f"Invalid iscell shape: {label_path}")
        planes.append({"plane": folder.name, "image": image,
                       "stats": stats, "labels": labels[:, 0]})
        sources.extend(signature(path) for path in (stat_path, label_path, image_path))
    helpers = pipeline_module(pipeline_root, "review_plots")
    figure, counts = helpers.plot_segmentation_review(planes, fish.fish_id)
    folder = fish.experiment_dir / "plots/segmentation"
    output = folder / f"{fish.fish_id}_segmentation.png"
    try:
        atomic_figure(figure, output)
    finally:
        plt.close(figure)
    record = {"fish_id": fish.fish_id, "experiment_id": fish.experiment_id,
              "generated_at": now(), "sources": sources, "counts": counts,
              "classification": "iscell[:, 0]: 1=cell, 0=non-cell",
              "code": code_versions(pipeline_root), "outputs": [str(output)]}
    atomic_write(folder / f"{fish.fish_id}_segmentation.json", json.dumps(record, indent=2))
    atomic_write(folder / f"{fish.fish_id}_cell_counts.csv",
                 pd.DataFrame(counts).to_csv(index=False))
    return record


def plotting_defaults(fish, metadata, derived_root):
    """Discover candidate settings from this fish, marking unresolved timing explicitly."""
    stimuli = Path(derived_root).parent / "stimuli" / fish.experiment_id
    logs = list((fish.source / "01_raw/2p/metadata").glob("*_block_log.csv"))
    blocks = []
    if len(logs) == 1:
        events = pd.read_csv(logs[0])["event"].astype(str)
        blocks = list(dict.fromkeys(events.str.extract(r"^(B\d+)_stim\d+_")[0].dropna()))
    stimulus_fps = 60.0
    parameters = stimuli / "parameters/experiment_parameters.csv"
    if parameters.is_file():
        table = pd.read_csv(parameters)
        if "framerate" in table:
            rates = pd.to_numeric(table["framerate"], errors="coerce").dropna().unique()
            if len(rates) == 1:
                stimulus_fps = float(rates[0])
            elif len(rates) > 1:
                stimulus_fps = None  # Conflicting metadata still needs a manual choice.
    imaging_fps = float(metadata["framerate"]) if metadata.get("framerate") else None
    return {"stimuli_dir": str(stimuli), "selected_blocks": blocks,
            "imaging_fps": imaging_fps, "stimulus_fps": stimulus_fps,
            "frames_per_block": int(metadata["n_volumes"]) if metadata.get("n_volumes") else None,
            "pre_stimulus_sec": 5.0, "post_stimulus_sec": 27.0,
            "sort_by_correlation": True, "stimulus_order": None}


def generate_responses(fish, pipeline_root, settings):
    """Reuse pipeline calculations on existing merged data and export two figures."""
    analysis = pipeline_module(pipeline_root, "stimulus_analysis")
    plotting = pipeline_module(pipeline_root, "plotting")
    helpers = pipeline_module(pipeline_root, "review_plots")
    suite = fish.source / "03_analysis/functional/suite2P"
    data_path = suite / "merged_dFoF" / f"{fish.fish_id}_dFoF_merged.npy"
    dfof = np.load(data_path, mmap_mode="r", allow_pickle=False)
    map_path, mapping, map_evidence = resolve_roi_map(data_path, dfof)
    blocks = settings["selected_blocks"]
    if not blocks or len(set(blocks)) != len(blocks):
        raise ValueError("Select unique acquisition blocks in their recorded order.")
    if dfof.shape[0] % len(blocks):
        raise ValueError("Merged frame count is not divisible by selected blocks.")
    frames_per_block = settings.get("frames_per_block")
    if not frames_per_block or frames_per_block * len(blocks) != dfof.shape[0]:
        raise ValueError("Frames per block and selected blocks must explain the merged frame count.")
    imaging_fps, stimulus_fps = settings["imaging_fps"], settings["stimulus_fps"]
    if not imaging_fps or not stimulus_fps or min(imaging_fps, stimulus_fps) <= 0:
        raise ValueError("Confirm positive imaging and stimulus frame rates.")
    logs = list((fish.source / "01_raw/2p/metadata").glob("*_block_log.csv"))
    if len(logs) != 1:
        raise ValueError("Exactly one block log is required; resolve multiple logs before plotting.")
    log = pd.read_csv(logs[0])
    available_blocks = log.event.astype(str).str.extract(r"^(B\d+)_")[0]
    if set(blocks) - set(available_blocks.dropna()):
        raise ValueError("Some selected blocks are absent from the log.")
    log = log[available_blocks.isin(blocks)].copy()
    block_duration = frames_per_block / imaging_fps
    if pd.to_numeric(log.timestamp).max() > block_duration:
        raise ValueError("Block events exceed the selected block duration.")
    adjusted = analysis.adjust_block_log(log, blocks, block_duration)
    durations = analysis.load_stimulus_durations(settings["stimuli_dir"], stimulus_fps)
    names = list(dict.fromkeys(log.event.astype(str).str.extract(r"^B\d+_stim\d+_(.+)$")[0].dropna()))
    aliases = {}
    for name in names:
        if name not in durations:
            matches = [candidate for candidate in durations if candidate.casefold() == name.casefold()]
            if len(matches) != 1:
                raise ValueError(f"Cannot uniquely match stimulus {name} to a trajectory.")
            aliases[name] = matches[0]
    # Resolve unique case-only aliases explicitly; never silently drop stimulus events.
    durations = {next((name for name, original in aliases.items() if original == key), key): value
                 for key, value in durations.items()}
    timeline = analysis.build_stimulus_timeline(adjusted, durations, dfof.shape[0],
                                                 imaging_fps, stimulus_fps)
    expected_trials = int(log.event.astype(str).str.match(r"^B\d+_stim\d+_").sum())
    if len(timeline["stimulus_events"]) != expected_trials:
        raise ValueError("Some stimulus presentations were not recognized.")
    events = timeline["stimulus_events"]
    if (events["onset_time"] < 0).any() or (events["offset_time"] > dfof.shape[0] / imaging_fps).any():
        raise ValueError("Stimulus events extend beyond the merged recording.")
    aligned = analysis.build_trial_aligned_traces(
        dfof, timeline["stimulus_trace"], timeline["stimulus_id_map"], imaging_fps,
        settings["pre_stimulus_sec"], settings["post_stimulus_sec"])
    detected_trials = sum(value["found"] for value in aligned["trial_counts"].values())
    if detected_trials != expected_trials:
        raise ValueError("Sampled stimulus onsets do not match the logged trial count.")
    order = settings.get("stimulus_order") or list(aligned["mean_rasters"])
    if len(order) != len(set(order)) or set(order) != set(aligned["mean_rasters"]):
        raise ValueError("Stimulus order must include each observed stimulus exactly once.")
    mean_rasters = {name: aligned["mean_rasters"][name] for name in order}
    concatenated = analysis.concatenate_stimulus_mean_rasters(
        mean_rasters, durations, aligned["pre_frames"], imaging_fps, stimulus_order=order)
    neuron_order = plotting.correlation_sort_order(concatenated["raster"].T) if settings["sort_by_correlation"] else None
    metrics = analysis.compute_response_metrics(mean_rasters, aligned["pre_frames"], imaging_fps)
    auc = analysis.summarize_metric(metrics["auc"])
    maximum = analysis.summarize_metric(metrics["maximum_amplitude"])
    folder = fish.experiment_dir / "plots/general"
    raster_path = folder / f"{fish.fish_id}_stimulus_rasters.png"
    metric_path = folder / f"{fish.fish_id}_stimulus_metrics.png"
    raster_figure, _ = plotting.plot_concatenated_stimulus_responses(
        concatenated["raster"], concatenated["segments"], imaging_fps,
        fish.fish_id, neuron_order=neuron_order)
    raster_figure.set_size_inches(20, 8)
    try:
        atomic_figure(raster_figure, raster_path)
    finally:
        plt.close(raster_figure)
    metric_figure, _ = helpers.plot_response_metric_summary(auc, maximum, fish.fish_id, plotting.plot_metric_bars)
    try:
        atomic_figure(metric_figure, metric_path)
    finally:
        plt.close(metric_figure)
    repetition_path = folder / f"{fish.fish_id}_stimulus_repetitions.png"
    repetition_figure, _ = helpers.plot_repetition_responses(
        aligned["trial_traces"], aligned["retained_repetitions"], order, durations,
        aligned["pre_frames"], imaging_fps, fish.fish_id, neuron_order=neuron_order)
    try:
        atomic_figure(repetition_figure, repetition_path)
    finally:
        plt.close(repetition_figure)
    trajectory_paths = sorted(Path(settings["stimuli_dir"]).glob("*trajectory.*"))
    record = {"fish_id": fish.fish_id, "experiment_id": fish.experiment_id,
              "generated_at": now(), "settings": settings, "shape": list(dfof.shape),
              "stimulus_order": order, "case_aliases": aliases,
              "trial_counts": aligned["trial_counts"], "recognized_presentations": expected_trials,
              "roi_map": str(map_path),
              "sources": [signature(path) for path in [data_path, map_path, *map_evidence, logs[0], *trajectory_paths]],
              "code": code_versions(pipeline_root),
              "outputs": [str(raster_path), str(metric_path), str(repetition_path)],
              "retained_repetitions": aligned["retained_repetitions"],
              "metric_definition": "Pipeline mean +/- SEM across neurons; metrics of trial-averaged traces from stimulus onset through post_stimulus_sec."}
    atomic_write(folder / f"{fish.fish_id}_responses.json", json.dumps(record, indent=2))
    return record

def generate_fluorescence(fish, pipeline_root, fallback_fps=None):
    """Save a self-contained raw-F viewer with original ROI IDs and cell labels."""
    suite = fish.source / "03_analysis/functional/suite2P"
    folders = sorted((path for path in suite.iterdir() if re.fullmatch(r"plane\d+", path.name)),
                     key=lambda path: int(path.name[5:]))
    planes, sources, counts = [], [], []
    for folder in folders:
        fluorescence_path = plane_file(folder, fish.fish_id, "F")
        label_path = plane_file(folder, fish.fish_id, "iscell")
        fluorescence = np.load(fluorescence_path, mmap_mode="r", allow_pickle=False)
        classification = np.load(label_path, allow_pickle=False)
        if classification.ndim != 2 or classification.shape[1] < 1:
            raise ValueError(f"Invalid cell classification shape in {label_path}")
        fps = fallback_fps
        rate_source = "acquisition metadata"
        try:
            ops_path = plane_file(folder, fish.fish_id, "ops")
        except ValueError:
            ops_path = None
        if ops_path is not None:
            ops = np.load(ops_path, allow_pickle=True).item()
            fps = ops.get("fs", fps)
            if ops.get("nframes") is not None and int(ops["nframes"]) != fluorescence.shape[1]:
                raise ValueError(f"F frame count disagrees with Suite2p ops in {folder.name}")
            del ops
            sources.append(signature(ops_path))
            rate_source = "Suite2p ops fs"
        if fps is None or not np.isfinite(float(fps)) or float(fps) <= 0:
            raise ValueError(f"No verified positive frame rate for {folder.name}")
        planes.append({"name": folder.name, "fluorescence": fluorescence,
                       "labels": classification[:, 0], "fps": float(fps)})
        sources.extend(signature(path) for path in (fluorescence_path, label_path))
        counts.append({"plane": folder.name, "rois": fluorescence.shape[0],
                       "frames": fluorescence.shape[1], "fps": float(fps), "rate_source": rate_source})
    helper = pipeline_module(pipeline_root, "fluorescence_review")
    content = helper.fluorescence_html(planes, fish.fish_id)
    folder = fish.experiment_dir / "plots/segmentation"
    output = folder / f"{fish.fish_id}_raw_fluorescence.html"
    atomic_write(output, content)
    code = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(pipeline_root) / "src/fluorescence_review.py",
                         Path(pipeline_root) / "src/raw_fluorescence.html"]}
    record = {"fish_id": fish.fish_id, "generated_at": now(), "sources": sources,
              "planes": counts, "code": code, "outputs": [str(output)],
              "signal": "Original Suite2p F; no neuropil subtraction, baseline correction or delta F/F.",
              "display": "Every sample retained; min/max envelope when more samples than screen pixels."}
    atomic_write(folder / f"{fish.fish_id}_raw_fluorescence.json", json.dumps(record, indent=2))
    return record
