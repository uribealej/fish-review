"""Inspect filenames only; availability never decides scientific quality."""
import csv
import os
from pathlib import Path


def read_files(folder, recursive=False):
    """Return files and errors, distinguishing absent folders from access failures."""
    folder = Path(folder)
    try:
        entries = list(folder.iterdir())
    except FileNotFoundError:
        return [], []
    except OSError as error:
        return [], [f"{folder}: {error}"]
    if not recursive:
        return [entry for entry in entries if entry.is_file()], []
    files, errors = [], []
    def record_error(error):
        errors.append(str(error))
    for current, directories, names in os.walk(folder, onerror=record_error, followlinks=False):
        files.extend(Path(current) / name for name in names)
    return files, errors


def evidence(label, paths, errors=(), note=""):
    """Make a transparent status from discovered files and scan failures."""
    paths = sorted(set(paths))
    status = "Could not verify" if errors else ("Present" if paths else "Not found here")
    return {"item": label, "status": status, "count": len(paths),
            "paths": [str(path) for path in paths], "note": note,
            "errors": list(errors)}


def scan_fish(fish):
    """Find known outputs without loading arrays or creating any records."""
    try:
        list(fish.source.iterdir())
    except OSError as error:
        return {"fish_id": fish.fish_id, "error": str(error), "items": [],
                "planes": [], "plots": [], "metadata": {}, "review_path": None}
    metadata_dir = fish.source / "01_raw" / "2p" / "metadata"
    metadata, metadata_errors = read_files(metadata_dir)
    suite_dir = fish.source / "03_analysis" / "functional" / "suite2P"
    suite, suite_errors = read_files(suite_dir, recursive=True)
    analysis_plots, plot_errors = read_files(
        fish.source / "03_analysis" / "functional" / "plots", recursive=True)
    derived_plots, derived_errors = read_files(fish.experiment_dir / "plots", recursive=True)
    notebook_plots, notebook_errors = read_files(
        fish.source / "04_plots" / "basic_calcium_analysis", recursive=True)
    all_outputs = suite + analysis_plots
    def matching(paths, suffix):
        return [path for path in paths if path.name.lower().endswith(suffix.lower())]
    rows = [
        evidence("Acquisition metadata", matching(metadata, "_metadata.csv"), metadata_errors),
        evidence("Block timing log", matching(metadata, "_block_log.csv"), metadata_errors),
        evidence("Trial sequence", matching(metadata, "_trial_sequence.csv"), metadata_errors),
        evidence("Fluorescence (F)", matching(suite, "_F.npy") +
                 [p for p in suite if p.name == "F.npy"], suite_errors),
        evidence("Merged delta F/F", matching(suite, "_dFoF_merged.npy"), suite_errors),
        evidence("Merged ROI mapping", matching(suite, "_dFoF_merged_map.csv"), suite_errors),
        evidence("Z-score", [p for p in all_outputs if p.suffix.lower() in {".npy", ".npz"}
                             and any(x in p.stem.lower() for x in ("zcore", "zscore", "z_score"))],
                 suite_errors + plot_errors),
        evidence("Significance", [p for p in all_outputs if p.suffix.lower() in {".npy", ".npz"}
                                  and "significant" in p.stem.lower()], suite_errors + plot_errors),
    ]
    try:
        plane_dirs = sorted(p for p in suite_dir.iterdir() if p.is_dir() and p.name.startswith("plane"))
    except FileNotFoundError:
        plane_dirs = []
    except OSError as error:
        plane_dirs = []
        suite_errors.append(str(error))
    planes = []
    for plane in plane_dirs:
        plane_files = [p for p in suite if p.parent == plane]
        present = {}
        for name in ("F", "Fneu", "stat", "iscell", "ops"):
            present[name] = any(p.name in (f"{name}.npy", f"{fish.fish_id}_{plane.name}_{name}.npy")
                                for p in plane_files)
        # Newer Suite2p versions split ops into registration and detection outputs.
        present["images"] = present["ops"] or any(p.name.endswith("reg_outputs.npy") for p in plane_files)
        planes.append({"Plane": plane.name, **{k: "Present" if v else "Not found here"
                                               for k, v in present.items()}})
    rows.append(evidence("Suite2p classifications", [p for p in suite if p.name == "iscell.npy" or p.name.endswith("_iscell.npy")], suite_errors))
    rows.append(evidence("Suite2p reference images", [p for p in suite if p.name in ("ops.npy", "reg_outputs.npy") or p.name.endswith(("_ops.npy", "_reg_outputs.npy"))], suite_errors))
    segmentation = [p for p in suite if p.name == "stat.npy" or p.name.endswith("_stat.npy")]
    rows.insert(3, evidence("Suite2p ROI geometry", segmentation, suite_errors,
                            "Presence only; segmentation quality is not reviewed. See per-plane files."))
    extensions = {".png", ".jpg", ".jpeg"}
    prefix = fish.fish_id + "_"
    plots = sorted(set(
        [p for p in analysis_plots + notebook_plots if p.suffix.lower() in extensions]
        + [p for p in derived_plots if p.name.startswith(prefix) and p.suffix.lower() in extensions]))
    html_plots = [p for p in derived_plots if p.name.startswith(prefix) and p.suffix.lower() == ".html"]
    rows.append(evidence("Interactive fluorescence", html_plots, derived_errors))
    rows.append(evidence("Saved review plots", plots, plot_errors + derived_errors + notebook_errors))
    review_path = metadata_dir / "fish_review.yaml"
    rows.append(evidence("Manual review record", [p for p in metadata if p.name == "fish_review.yaml"],
                         metadata_errors))
    acquisition = {}
    meta_files = matching(metadata, "_metadata.csv")
    if len(meta_files) == 1:
        try:
            with meta_files[0].open(encoding="utf-8-sig", newline="") as handle:
                acquisition = {row["parameter"]: row["value"] for row in csv.DictReader(handle)}
        except (OSError, KeyError, UnicodeError, csv.Error) as error:
            acquisition = {"Read error": str(error)}
    elif len(meta_files) > 1:
        acquisition = {"Warning": "Multiple metadata files: select an authoritative file before plotting."}
    return {"fish_id": fish.fish_id, "error": None, "items": rows, "planes": planes,
            "plots": [str(p) for p in plots], "interactive_plots": [str(p) for p in html_plots], "metadata": acquisition,
            "review_path": str(review_path)}


def summary_row(fish, scan):
    """Summarize detected files without treating their presence as manual acceptance."""
    if scan["error"]:
        return {"Fish": fish.fish_id, "Source": "Could not verify", "Imaging QC": "Not loaded",
                "Suite2p": "Could not verify", "Traces": "Could not verify",
                "Responses": "Not loaded", "Decision / reason": "Source folder inaccessible"}
    statuses = {item["item"]: item["status"] for item in scan["items"]}
    review = statuses["Manual review record"] == "Present"
    return {
        "Fish": fish.fish_id, "Source": statuses["Acquisition metadata"],
        "Imaging QC": "Record available" if review else "Not reviewed",
        "Suite2p": statuses["Suite2p ROI geometry"],
        "Traces": statuses["Merged delta F/F"],
        "Responses": f"{len(scan['plots'])} plots; review " + ("record available" if review else "pending"),
        "Decision / reason": "Open existing record" if review else "Undecided",
    }
