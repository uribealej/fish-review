"""Discover source fish and append inventory entries without touching reviews."""
import os
import re
from pathlib import Path
import yaml
from fish_review.reviews import atomic_write

SKELETON = ("plots/segmentation", "plots/general", "aligned_traces", "neuron_index", "stimuli")


def discover(source_root, experiment):
    if not re.fullmatch(r"Exp_[A-Za-z0-9][A-Za-z0-9_-]*", experiment):
        raise ValueError("Use an experiment name such as Exp_8_accumulation_ev (letters, numbers, underscores or hyphens).")
    found = []
    suffix = "_" + experiment
    for path in sorted(Path(source_root).iterdir()):
        if path.is_dir() and path.name.endswith(suffix):
            fish_id = path.name[:-len(suffix)]
            if re.fullmatch(r"L[0-9]+_f[0-9]+", fish_id):
                found.append((fish_id, path.resolve()))
    return found


def inventory_changes(source_root, derived_root, experiment):
    found = discover(source_root, experiment)
    folder = Path(derived_root) / experiment
    metadata = folder / "experiment_metadata.yaml"
    original = metadata.read_bytes() if metadata.exists() else None
    data = yaml.safe_load(original) if original is not None else {"experiment_id": experiment, "fish": []}
    if not isinstance(data, dict) or data.get("experiment_id") != experiment or not isinstance(data.get("fish"), list):
        raise ValueError("Existing experiment inventory is invalid; it was not changed.")
    existing = {}
    for item in data["fish"]:
        if not isinstance(item, dict) or not isinstance(item.get("fish_id"), str) or not isinstance(item.get("source_folder"), str):
            raise ValueError("Existing fish entry is invalid; inventory was not changed.")
        if item["fish_id"] in existing:
            raise ValueError("Duplicate fish identifiers in existing inventory.")
        existing[item["fish_id"]] = (folder / item["source_folder"]).resolve()
    other_ids = set()
    for other in Path(derived_root).glob("*/experiment_metadata.yaml"):
        if other.resolve() == metadata.resolve():
            continue
        other_data = yaml.safe_load(other.read_text(encoding="utf-8-sig"))
        other_ids.update(item["fish_id"] for item in other_data["fish"])
    additions = []
    for fish_id, source in found:
        if fish_id in existing:
            if existing[fish_id] != source:
                raise ValueError(f"{fish_id} already points to a different source folder. Resolve this before adding fish.")
        else:
            if fish_id in other_ids:
                raise ValueError(f"{fish_id} is already registered in another experiment.")
            additions.append({"fish_id": fish_id, "source_folder": Path(os.path.relpath(source, folder)).as_posix()})
    return metadata, original, data, additions, found


def add_discovered_fish(source_root, derived_root, experiment):
    metadata, original, data, additions, found = inventory_changes(source_root, derived_root, experiment)
    if not found:
        raise ValueError("No matching fish folders found. Nothing was created.")
    metadata.parent.mkdir(parents=True, exist_ok=True)
    lock = metadata.with_suffix(".discovery.lock")
    handle = lock.open("x")
    try:
        with handle:
            current = metadata.read_bytes() if metadata.exists() else None
            if current != original:
                raise ValueError("Inventory changed during discovery. Scan again.")
            for name in SKELETON:
                (metadata.parent / name).mkdir(parents=True, exist_ok=True)
            if additions or original is None:
                data["fish"].extend(additions)
                atomic_write(metadata, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    finally:
        lock.unlink()
    return [item["fish_id"] for item in additions]
