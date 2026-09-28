"""Regenerate experiment and global views from authoritative records."""
import csv
import html
import io
import json
from pathlib import Path

from fish_review.detection import scan_fish, summary_row
from fish_review.reviews import atomic_write, load_review, review_status


def overview_row(fish, scan=None):
    """Combine detected outputs and manual decisions without changing either."""
    scan = scan if scan is not None else scan_fish(fish)
    row = {"Experiment": fish.experiment_id, **summary_row(fish, scan)}
    try:
        record, token = load_review(fish)
        row.update(review_status(record))
        manual = record["manual"]
        for field, label in (("quality", "Image quality"), ("bleaching", "Bleaching"), ("z_drift", "Z-drift")):
            row[label] = manual["imaging_qc"][field]["assessment"]
            row[label + " comment"] = manual["imaging_qc"][field]["comment"]
        row["Suite2p comment"] = manual["suite2p"]["comment"]
        row["Left response"] = manual["responses"]["left"]
        row["Right response"] = manual["responses"]["right"]
        row["Left/right bias"] = manual["responses"]["bias"]
        row["Response comment"] = manual["responses"]["comment"]
        row["Final decision"] = manual["decision"]["status"]
        row["Decision reason"] = manual["decision"]["reason"]
        row["Exclusion stage"] = manual["decision"].get("stage") or ""
        row["Review stage"] = manual["progress"].get("stage") or ""
        row["Review saved"] = record.get("updated_at", "Not saved")
    except (ValueError, OSError) as error:
        row["Decision / reason"] = f"Review unreadable: {error}"
        row["Fish comment"] = ""
    count_path = fish.experiment_dir / "plots/segmentation" / f"{fish.fish_id}_segmentation.json"
    if count_path.exists():
        try:
            counts = json.loads(count_path.read_text(encoding="utf-8"))["counts"]
            row["Cells"] = sum(item["cells"] for item in counts)
            row["Non-cells"] = sum(item["non_cells"] for item in counts)
        except (OSError, ValueError, KeyError, TypeError):
            row["Cells"] = "Could not read"
            row["Non-cells"] = "Could not read"
    return row


def html_table(rows):
    """Escape all recorded user text before embedding it into generated HTML."""
    if not rows:
        return "<p>No fish.</p>"
    columns = list(dict.fromkeys(key for row in rows for key in row))
    head = "".join(f"<th>{html.escape(key)}</th>" for key in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>"
                                   for key in columns) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def html_page(title, rows, extra=""):
    """Create a readable standalone summary with searchable fish rows."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:16px system-ui;margin:32px;color:#183247;background:#f6f9fb}}
table{{border-collapse:collapse;background:white;width:100%}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top;white-space:pre-wrap}}
th{{background:#dcecf2}}input{{padding:10px;width:360px;margin:12px 0}}.scroll{{overflow:auto}}
</style></head><body><h1>{html.escape(title)}</h1>{extra}
<label>Filter fish <input id="filter" placeholder="Fish, experiment, decision or comment"></label>
<div class="scroll">{html_table(rows)}</div>
<script>document.querySelector('#filter').addEventListener('input',function(){{
document.querySelectorAll('tbody tr').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(this.value.toLowerCase()));
}});</script></body></html>"""


def write_overview(folder, stem, title, rows):
    """Write HTML and CSV views using deterministic output names."""
    folder = Path(folder)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    errors = []
    for suffix, content in (("html", html_page(title, rows)), ("csv", buffer.getvalue())):
        path = folder / f"{stem}.{suffix}"
        try:
            atomic_write(path, content)
        except OSError as error:
            errors.append(f"Could not replace {path}; close it in other programs and retry. {error}")
    return errors


def export_summaries(experiments, derived_root):
    """Update all derived summaries without writing to any manual review."""
    global_rows = []
    errors = []
    for experiment, fishes in experiments.items():
        rows = []
        for fish in fishes:
            try:
                scan = scan_fish(fish)
                row = overview_row(fish, scan)
                rows.append(row)
            except (OSError, ValueError, KeyError) as error:
                errors.append(f"{fish.fish_id}: {error}")
                rows.append({"Experiment": experiment, "Fish": fish.fish_id,
                             "Decision / reason": f"Could not refresh: {error}"})
        if fishes:
            errors.extend(write_overview(fishes[0].experiment_dir, "experiment_overview", experiment, rows))
        global_rows.extend(rows)
    errors.extend(write_overview(Path(derived_root) / "global", "overview", "All experiments", global_rows))
    return global_rows, errors
