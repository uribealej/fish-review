# Fish review

A local browser app for reviewing fish calcium-imaging experiments. Fish review brings
Suite2p outputs, stimulus-response figures and manual quality assessments into one
place, so researchers can inspect each fish and record whether to use it, exclude it,
or review it further.

## What you can do

- Browse experiments and fish, check which processed outputs are available, and track review progress.
- Inspect Suite2p cell/non-cell outlines, ROI counts and individual fluorescence traces.
- Generate stimulus-average and individual-repetition rasters, plus AUC and maximum-amplitude summaries.
- Record image quality, bleaching, Z-drift, response assessments, comments and a final decision.
- Save reviews as YAML and regenerate experiment and global HTML/CSV summaries.

Availability and manual decisions are separate: missing files never automatically
exclude a fish. You can pause a review and resume it later.

## What you need

- Python 3.11 and the packages listed in [requirements.txt](requirements.txt), or Conda with [environment.yml](environment.yml).
- A browser. The app runs locally using Streamlit and listens only on localhost.
- Existing Suite2p outputs and experiment inventories in the expected `2p` / `2p_derived`
  layout. Response plots also need existing merged delta F/F traces, their ROI map,
  acquisition metadata, block logs and stimulus trajectories.
- A compatible local checkout of `calcium-imaging-pipeline`, which supplies the scientific
  calculations and figure helpers. It must include `src/review_plots.py`, support for
  unprefixed trajectory columns, and the optional `axis` argument to `plot_metric_bars`.
  These companion changes currently exist locally and have not been published.

Raw imaging files are not required. The app starts from processed outputs and does not
run Suite2p or merge planes. Scientific data and local path configuration are not
included in this repository.

## Install and run

Run these commands from the repository folder. With Conda:

```powershell
conda env create -f environment.yml
conda activate fish-review
```

Create your local configuration once:

```powershell
Copy-Item config.example.json config.local.json
```

Edit `config.local.json`: set `derived_root` to your `2p_derived` folder and
`pipeline_root` to your `calcium-imaging-pipeline` checkout. Set `default_experiment`
and `default_fish` to your preferred starting selection, or remove those optional fields.
Keep this configuration local; Git ignores it.

When storing derived outputs separately from the source data, set `source_root`
to the folder containing the source fish folders and `stimuli_root` to the folder
containing stimulus experiment folders. Otherwise these default to `2p` and
`stimuli` beside `derived_root`. Moving existing outputs also requires updating
inventory source references and saved plot paths.

Start the app from the activated Conda environment:

```powershell
python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Open **http://127.0.0.1:8501**. Keep the terminal open while using the app; press
**Ctrl+C** to stop the server. Save pending reviews before closing or refreshing the browser.

### Alternative: Python virtual environment

If you prefer `venv`, create the environment and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create and edit `config.local.json` as described above, then run `.\start.ps1` in
PowerShell. This launcher uses `.venv`; for Conda, use the `python -m streamlit` command above.

For a clickable Windows launcher, double-click **Open Fish Review.cmd**. It uses
the same `.venv` and opens the app in your browser. You can create a desktop
shortcut to this file for easy access. Keep its terminal window open while using
the app, and save pending reviews before stopping it with **Ctrl+C**.

## Review workflow

1. Choose an experiment, then a fish. Previous/Next follows the saved inventory order.
2. Inspect automatic output availability. Raw images are neither requested nor required.
3. Record manual image quality, bleaching and Z-drift. Not assessed is allowed.
4. Inspect Suite2p cell/non-cell outlines and per-plane/whole-fish counts.
5. Inspect the stimulus-average raster, combined AUC/maximum-amplitude bars, and individual-repetition raster; record
   overall, left, right and bias assessments.
6. Save a final use/exclude/review/undecided decision, reason and prominent fish comment.

Every stage offers Save and continue later. Progress is automatic: Not started, In progress, Paused or Finished.
Strong Z-drift or another concern does not automatically exclude a fish.
Use Resume review to continue; this does not change the final decision. Use Finish review after choosing a final decision.
Edits persist in the current browser session across fish navigation; Save review is required
before closing the browser. Reload saved review discards that fish's unsaved draft.
Simultaneous stale saves are rejected rather than overwrite newer answers.

## Authoritative and generated records

- Inventory: 2p_derived/<experiment>/experiment_metadata.yaml. Relative source_folder links
  resolve against that file.
- Manual authority: <fish>/01_raw/2p/metadata/fish_review.yaml.
- Individual fish HTML reports are not generated; per-fish plots remain accessible in the app.
- Experiment summary: <experiment>/experiment_overview.html and .csv.
- Global summary: global/overview.html and .csv.
- Segmentation: <experiment>/plots/segmentation/<fish>_segmentation.png,
  <fish>_cell_counts.csv and <fish>_segmentation.json.
- General plots: <experiment>/plots/general/<fish>_stimulus_rasters.png,
  <fish>_stimulus_metrics.png, <fish>_stimulus_repetitions.png and <fish>_responses.json.
- Raw fluorescence: plots/segmentation/<fish>_raw_fluorescence.html and its .json provenance.

Plot subfolders are shared by all fish; there are no per-fish plot folders.
This supersedes the earlier flat plots/ proposal. Exports are generated views, never independent
manual authorities. Saving or generating figures regenerates summaries. The sidebar also
provides Regenerate all summaries. Refresh checks preserves all manual decisions.

## Scientific conventions

The app calls calcium-imaging-pipeline helpers for all scientific calculations and figures.
The response adapter validates the merged ROI map, frame count, selected blocks and stimulus
matches. It resolves only unique case-only stimulus aliases and records them explicitly.
Notebook defaults are 5 seconds before onset and 27 seconds from onset onward; those analysis
windows are editable. Rates and block sizes come from this fish's metadata, not another example.
Response metrics follow the notebook: metrics of trial-averaged traces, then mean and SEM
across neurons. No additional baseline correction or responsive-neuron selection is applied.
Suite2p counts use iscell[:,0], not morphology-based guesses.

Plot sidecars record parameters, source sizes/timestamps and local code hashes. Reviews snapshot
file evidence and flag later changes. Array existence alone does not certify its contents.
Object arrays are loaded only from the user's trusted local Suite2p outputs.
If the canonical merged ROI map has inconsistent dimensions or column indices, the app
can use a timestamped archived map verified against the merged ROI indices and every
mapped per-plane trace. Different matching mappings remain an error. The selected map
and verification inputs are recorded in the response sidecar; source files are unchanged.

## Scope and GitHub

All 77 existing inventory entries are supported for navigation; plot generation was validated
on L800_f09. Other fish may require stimulus path or timing settings to be supplied.
Use Add experiment above the experiment selector: enter the exact experiment suffix, scan,
then create the experiment with the discovered fish. Under the selected experiment, Find new
fish scans and appends only new entries. Existing entries, custom YAML fields and manual
reviews are preserved; absent source folders are never removed from the inventory.
Discovery reads the sibling 2p directory by default; source_root in config.local.json can
override it. Fish folder names must follow L<number>_f<number>_<experiment>.
The scan previews changes before writing. GitHub publishing is still pending.
The chosen GitHub destination is a personal account; username and visibility remain to be established.
Source data, reviews, local configuration, figures, logs and environments are ignored by Git.

## Validation

From the activated Conda environment:

```powershell
python -m unittest discover -s tests -v
```

Or with the local virtual environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Persistence tests use temporary synthetic fish, including save/reopen, manual-only exclusion,
stale writes, unknown-field preservation, summary visibility and draft navigation.
The real example's figures were rendered and visually inspected. No real manual decisions
were created by automated tests.


## Stimulus ordering and additional views

The response tab shows a fixed map of stimulus numbers (starting at 1), letters and names.
Enter a complete order using numbers, letters, names or a mixture. Repeated, missing or
unknown entries prevent generation. Blank uses the map order. The order applies to all
response figures. Regeneration replaces the same fish-prefixed generated files.
Valid plot orders are remembered across fish within each experiment during the browser
session. Each experiment keeps its own order. Stimulus rate defaults to 60 Hz when no
rate is found in the stimulus parameters; a recorded rate takes precedence, and
conflicting recorded rates still require a manual choice.

The repetition raster concatenates the original trial windows within each stimulus in
presentation order; it never averages repetitions. Every strip uses the same neuron order
(from the average-response figure), colour range and population-trace y range.
Original R1/R2/... labels are preserved if boundary trials are dropped.

The Raw fluorescence tab can export an offline HTML viewer of every F.npy sample, preserving original
zero-based ROI indices and iscell labels. Controls select planes, cells/non-cells, trace height,
time window and separate/shared F scales. All samples are retained in lossless compressed
payloads; min/max envelopes are drawn only when there are more samples than screen pixels.
The app displays the saved viewer through a loopback-only HTTP server, avoiding large inline
Streamlit messages. A button also opens it in a new tab. Only explicitly registered viewer
files are served; no data directories are exposed. This viewer is intended for local app use.
No baseline correction, delta F/F or neuropil subtraction is performed.
A current browser with DecompressionStream support is needed (Chrome, Edge, Firefox or Safari).

Schema 1 reviews are migrated to schema 2 in memory without changing source files.
Progress and decision are independent fields; legacy stop fields and history are retained.
Files change only when the user saves. A locked summary CSV does not block other exports.
