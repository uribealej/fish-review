"""Persist manual reviews independently from automatic availability checks."""
import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

STAGES = ["Source", "Imaging QC", "Suite2p", "Traces", "Responses", "Final decision"]
QUALITY = ["Not assessed", "Good", "Acceptable", "Poor"]
SEVERITY = ["Not assessed", "None observed", "Mild", "Strong"]
RESPONSES = ["Not reviewed", "Good", "Acceptable", "Poor", "No response", "Cannot assess"]
BIAS = ["Not reviewed", "No clear bias", "Stronger left", "Stronger right", "Cannot assess"]
SEGMENTATION = ["Not reviewed", "Acceptable", "Needs correction", "Unusable", "Cannot assess"]
DECISIONS = ["undecided", "use", "exclude", "review"]


def now():
    """Return an unambiguous UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def review_path(fish):
    """Return the authoritative manual-record path."""
    return fish.source / "01_raw/2p/metadata/fish_review.yaml"


def default_manual():
    """Provide explicit unanswered states, separate from automatic checks."""
    return {
        "imaging_qc": {
            "quality": {"assessment": "Not assessed", "comment": ""},
            "bleaching": {"assessment": "Not assessed", "comment": ""},
            "z_drift": {"assessment": "Not assessed", "comment": ""},
        },
        "suite2p": {"assessment": "Not reviewed", "comment": ""},
        "responses": {"overall": "Not reviewed", "left": "Not reviewed", "right": "Not reviewed",
                      "bias": "Not reviewed", "comment": ""},
        "decision": {"status": "undecided", "reason": "", "stage": None},
        "progress": {"state": "not_started", "stage": None},
        "comment": "",
    }


def merge_values(original, updates):
    """Recursively merge controlled fields while retaining unknown metadata."""
    result = copy.deepcopy(original)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_values(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_review(fish):
    """Load a record and content token; reject incompatible or mismatched records."""
    path = review_path(fish)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {"schema_version": 2, "fish_id": fish.fish_id,
                "experiment_id": fish.experiment_id, "manual": default_manual()}, None
    try:
        record = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ValueError(f"Cannot parse review YAML: {path}") from error
    if not isinstance(record, dict) or record.get("schema_version") not in (1, 2):
        raise ValueError(f"Unsupported review schema: {path}. Existing record preserved.")
    if record.get("fish_id") != fish.fish_id or record.get("experiment_id") != fish.experiment_id:
        raise ValueError("Review identity does not match the selected fish.")
    if not isinstance(record.get("manual"), dict):
        raise ValueError("Review manual fields must be a mapping.")
    record = upgrade_record(record)
    try:
        validate_manual(record["manual"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Invalid saved review fields: {error}") from error
    return record, hashlib.sha256(raw).hexdigest()


def atomic_write(path, content):
    """Replace a derived file atomically using a temporary file in its folder."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_manual(manual):
    """Check field values and stop/decision consistency before writing."""
    for field, options in (("quality", QUALITY), ("bleaching", SEVERITY), ("z_drift", SEVERITY)):
        if manual["imaging_qc"][field]["assessment"] not in options:
            raise ValueError(f"Invalid imaging assessment: {field}")
    if manual["suite2p"]["assessment"] not in SEGMENTATION:
        raise ValueError("Invalid segmentation assessment.")
    for key in ("overall", "left", "right"):
        if manual["responses"][key] not in RESPONSES:
            raise ValueError(f"Invalid response assessment: {key}")
    if manual["responses"]["bias"] not in BIAS:
        raise ValueError("Invalid bias assessment.")
    if manual["decision"]["status"] not in DECISIONS:
        raise ValueError("Invalid final decision.")
    progress = manual["progress"]
    if progress["state"] not in ("not_started", "in_progress", "paused", "finished"):
        raise ValueError("Invalid review progress.")
    if progress["stage"] is not None and progress["stage"] not in STAGES:
        raise ValueError("Invalid review stage.")
    if manual["decision"].get("stage") is not None and manual["decision"]["stage"] not in STAGES:
        raise ValueError("Invalid decision stage.")



def evidence_snapshot(scan):
    """Record available paths and signatures to flag changed review evidence."""
    result = {}
    for item in scan["items"]:
        if item["item"] == "Manual review record":
            continue
        files = {}
        for value in item["paths"]:
            try:
                stat = Path(value).stat()
                files[value] = [stat.st_size, stat.st_mtime_ns]
            except OSError:
                files[value] = None
        result[item["item"]] = {"status": item["status"], "files": files}
    return result


def save_review(fish, manual, scan, expected_token):
    """Save only after checking stale edits, retaining unknown fields and history."""
    validate_manual(manual)
    path = review_path(fish)
    if not path.parent.is_dir():
        raise ValueError("The fish metadata folder must exist before saving a review.")
    lock = path.with_suffix(".yaml.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError("This review is being saved elsewhere. Retry after it finishes.") from error
    try:
        os.close(descriptor)
        current, token = load_review(fish)
        if token != expected_token:
            raise ValueError("This review changed elsewhere. Reload the saved review before saving.")
        if token is not None:
            history = current.setdefault("history", [])
            if not isinstance(history, list):
                raise ValueError("Review history is malformed; existing record preserved.")
            history.append({"updated_at": current.get("updated_at"),
                            "manual": copy.deepcopy(current["manual"]),
                            "availability": copy.deepcopy(current.get("availability", {}))})
        current["manual"] = merge_values(current["manual"], manual)
        current["updated_at"] = now()
        current["availability"] = evidence_snapshot(scan)
        atomic_write(path, yaml.safe_dump(current, sort_keys=False, allow_unicode=True))
    finally:
        lock.unlink(missing_ok=True)
    return load_review(fish)


def review_status(record):
    """Return concise human-facing stage, decision and comment summaries."""
    manual = record["manual"]
    assessed = [item["assessment"] for item in manual["imaging_qc"].values()
                if isinstance(item, dict) and "assessment" in item]
    qc = "Not assessed" if all(value == "Not assessed" for value in assessed) else ("Partly assessed" if "Not assessed" in assessed else "Assessed")
    if any(value in ("Poor", "Strong", "Mild") for value in assessed):
        qc = "Concern recorded"
    decision = manual["decision"]["status"]
    reason = manual["decision"]["reason"]
    stage = manual["decision"].get("stage")
    label = {"undecided": "Undecided", "use": "Use", "exclude": "Exclude", "review": "Needs review"}[decision]
    if decision == "exclude" and stage:
        label += f" at {stage}"
    if reason:
        label += ": " + reason
    progress = manual["progress"]
    progress_label = {"not_started": "Not started", "in_progress": "In progress",
                      "paused": "Paused", "finished": "Finished"}[progress["state"]]
    if progress["state"] == "paused" and progress["stage"]:
        progress_label += f" at {progress['stage']}"

    return {"Review progress": progress_label, "Imaging QC": qc, "Suite2p review": manual["suite2p"]["assessment"],
            "Response review": manual["responses"]["overall"],
            "Decision / reason": label, "Fish comment": manual["comment"]}

def upgrade_record(record):
    """Migrate old stop states in memory without changing saved answers on disk."""
    record = copy.deepcopy(record)
    version = record.get("schema_version")
    if version not in (1, 2):
        raise ValueError("Unsupported review schema; the existing file is preserved.")
    if version == 1:
        manual = record.get("manual", {})
        stop = manual.get("stop", {})
        decision = manual.get("decision", {})
        state = stop.get("state", "active")
        progress = "paused" if state == "paused" else (
            "finished" if state == "excluded" else
            "in_progress" if record.get("updated_at") else "not_started")
        manual["progress"] = {"state": progress, "stage": stop.get("stage")}
        if decision.get("status") == "exclude":
            decision["stage"] = stop.get("stage") or "Final decision"
        record["schema_version"] = 2
    record["manual"] = merge_values(default_manual(), record["manual"])
    return record


def apply_review_action(manual, action="save", stage=None):
    """Set progress from a user action independently from the use/exclude decision."""
    manual = copy.deepcopy(manual)
    state = {"save": "in_progress", "resume": "in_progress",
             "pause": "paused", "finish": "finished"}[action]
    manual["progress"].update(state=state, stage=stage)
    if action == "finish" and manual["decision"]["status"] == "undecided":
        raise ValueError("Choose a final decision before finishing the review.")
    if manual["decision"]["status"] != "exclude":
        manual["decision"]["stage"] = None
    elif not manual["decision"].get("stage"):
        manual["decision"]["stage"] = stage or "Final decision"
    return manual
