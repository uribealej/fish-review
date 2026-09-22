# Agreed workflow and next development steps

## User decisions

- Separate fish-review repository; eventual GitHub remote on the user's personal account.
- Choose an experiment by name, select a fish from its list, then use Previous/Next.
- First example: L800_f09 in Exp_8_accumulation_ev.
- Raw images are unavailable on this computer. Begin from Suite2p outputs and do not request raw images.
- Imaging quality, bleaching and Z-drift are manual assessments.
- Suite2p: inspect per-plane reference images with ROI overlays; detailed editing remains in Suite2p.
- Traces: automatic availability only, no manual trace-quality questionnaire.
- Responses: show existing plots and later generate the notebook's figures from already merged data.
- Overall/left/right response choices: good, acceptable, poor, no response, cannot assess; initial state not reviewed.
- Bias choices: no clear bias, stronger left, stronger right, cannot assess.
- Each review stage offers stop/pause or exclude at this stage, with optional comment.
- Final decision: use, exclude, review or undecided, with an optional overall fish comment.
- Missing data never automatically excludes a fish. Keep availability and quality independent.
- Refresh preserves manual answers and can flag changes to supporting outputs.
- Reviews will live in source metadata/fish_review.yaml; summaries will populate experiment/fish,
  experiment_overview.* and global; plots stay flat in experiment/plots.
- New-fish discovery will add unambiguous assignments and surface ambiguous assignments for review.

## Verified first example

Existing inventory: seven experiments, 77 fish; Exp_8_accumulation_ev has 11 fish.
L800_f09: five Suite2p planes, fluorescence files, merged delta F/F, merged mapping,
Z-score archive, significance archive and three existing images.
Acquisition metadata reports framerate=2 and n_slices=5.
Stimulus metadata contains a historical network path; the local stimuli folder exists,
but its correspondence, timing, selected blocks and alignment still need inspection.
Do not assume another notebook example's selected blocks or analysis windows.

## Pipeline integration

Reference: calcium-imaging-pipeline/notebooks/basic_single_fish_analysis.ipynb.
Reuse src/stimulus_analysis.py and src/plotting.py. Do not call prepare_merged_dfof.
Load the existing <fish>_dFoF_merged.npy and map directly after checking orientation and shape.
Planned outputs:
- <fish>_full_activity.png
- <fish>_stimulus_rasters.png
- <fish>_stimulus_auc.png
- <fish>_stimulus_max_amplitude.png

## Validation of the first read-only milestone

- Four unittest checks passed: duplicate inventory entries, relative source paths,
  late outputs with missing upstream data, inaccessible sources, and empty planes.
- Streamlit AppTest passed against real data: initial L800_f09 selection, Next/Previous,
  experiment switch and refresh.
- localhost:8501 health endpoint returned ok.
- Browser visual inspection could not run: no browser was available through the UI tool.
- No new scientific figures were generated and no source/review/derived records were written.
- Manual saving, new plot generation, global summaries and new-fish discovery remain unimplemented.


## Implemented review milestone (2026-09-17)

The user approved manual QC and optional per-question comments, prominent fish comments,
explicit final decisions and exclusion reasons, and shared plots/segmentation and plots/general
subfolders. These subfolders supersede the earlier flat plots proposal.
For L800_f09 the correct destination is Exp_8_accumulation_ev; Exp_1_flickering was interpreted
as a layout example.

Implemented YAML saving with revision history, unknown-field retention, lock and stale-save
protection; per-stage pause/exclude; reopening; and generated fish/experiment/global HTML/CSV.
Unsubmitted drafts persist in the browser session while switching fish.
Manual decisions remain untouched by availability scans or plot generation.

Validated L800_f09: 2,010 cells and 1,318 non-cells across five planes.
Generated montage, stimulus raster and combined AUC/maximum bars; all rendered images inspected.
Response inputs: B1-B4, 1,356 frames/block, 2 Hz imaging, 60 Hz stimulus, existing (5,424, 2,010)
merged matrix. All 64 presentations retained across 16 stimuli (four repeats each).
Unique case-only alias LeB -> leB recorded; plain x/y/radius columns supported in pipeline helper.
The pipeline original notebook bar call remains valid.
Summary exports cover 77 fish in seven experiments. No real manual decision was invented/saved.
Browser visual automation is still unavailable; UI behavior checked with Streamlit AppTest.

Remaining: new-fish discovery, personal GitHub remote, and configuration/validation on other fish.


## Progress, ordering, raw F and repetition views (2026-09-17)

User requested removal of the progress dropdown and separation of progress from decision.
UI now offers Save review, Save and continue later, Resume review and Finish review.
Exclusion is selected only under Final decision, with the reason and originating stage.
The response tab follows the same controls. Undo unsaved changes replaces the old reload label.

Response settings expose an explicit 1-based number/letter/name map and validate complete order
strings. Regeneration replaces generated outputs in plots/general. Added an individual-trial
raster with repetitions concatenated within each stimulus, preserving chronology and row order.

Added a self-contained raw-F HTML viewer under plots/segmentation. L800_f09 includes 3,328 ROIs
across five planes and every one of its 18,051,072 samples. Every embedded sample was compared
against F.npy and matches exactly. Viewer JavaScript filtering, time controls and reset passed
a DOM/canvas test harness; AppTest verifies embedding/download controls.
No browser was available for an actual HTML screenshot; this remains a visual-QA limitation.
The new repetition PNG was rendered and visually inspected: labels and layout are readable.

Existing manual review files were not overwritten during these changes. Summary export continued
after Windows denied replacement of Exp_1_flickering/experiment_overview.csv; HTML and other
experiment/global outputs can still update. That CSV requires retry when Windows permits access.
