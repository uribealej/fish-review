"""Read the saved experiment inventory without modifying scientific data."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Fish:
    """A fish linked to its authoritative experiment inventory."""
    fish_id: str
    experiment_id: str
    source: Path
    experiment_dir: Path


def load_inventory(derived_root):
    """Return experiment records and warnings, preserving inventory fish order."""
    root = Path(derived_root)
    list(root.iterdir())  # Raise if the root is inaccessible, rather than report no fish.
    experiments = {}
    warnings = []
    seen = set()
    for metadata in sorted(root.glob("*/experiment_metadata.yaml")):
        try:
            data = yaml.safe_load(metadata.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not isinstance(data.get("fish"), list):
                raise ValueError("Expected an experiment_id and a fish list")
            experiment_id = data["experiment_id"]
            if not isinstance(experiment_id, str) or not experiment_id:
                raise ValueError("Invalid experiment_id")
            if experiment_id in experiments:
                raise ValueError(f"Duplicate experiment: {experiment_id}")
            fishes = []
            for item in data["fish"]:
                try:
                    fish_id, source = item["fish_id"], item["source_folder"]
                    if not isinstance(fish_id, str) or not isinstance(source, str):
                        raise ValueError("fish_id and source_folder must be text")
                    if not fish_id or not source:
                        raise ValueError("Empty fish_id or source_folder")
                    if fish_id in seen:
                        raise ValueError(f"Duplicate fish identifier: {fish_id}")
                    seen.add(fish_id)
                    fishes.append(Fish(fish_id, experiment_id,
                                       (metadata.parent / source).resolve(), metadata.parent))
                except (KeyError, TypeError, ValueError) as error:
                    warnings.append(f"{metadata.name} ({experiment_id}): {error}")
            experiments[experiment_id] = fishes
        except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as error:
            warnings.append(f"{metadata}: {error}")
    return experiments, warnings
