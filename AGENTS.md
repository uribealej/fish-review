# fish-review

- Keep scientific calculation and figure construction in calcium-imaging-pipeline; this app integrates them.
- Reviews now save authoritative YAML and regenerate derived summaries. Keep availability separate from manual review.
- Preserve the existing data and 2p_derived layout. Never merge planes as part of review.
- Availability and manual quality/decisions are separate. Missing files never automatically exclude a fish.
- Unreachable sources must not be reported as confirmed missing data.
- Never commit scientific data, reviews, absolute local path configuration, or environments.
- Future writes must preserve manual answers, unknown fields, and evidence when refreshing.
- Inspect real metadata before choosing acquisition rates, blocks, timing, or stimulus order.
- Validate changes with small practical checks; visually inspect any new scientific figures.
- Do not publish or push until the GitHub destination is established.

- User decision: raw imaging is unavailable on this computer. Start from Suite2p outputs; do not request raw images. GitHub destination: personal account, username/visibility pending.

- Approved plot layout: plots/segmentation and plots/general per experiment, no fish subfolders. Use fish-prefixed filenames.
- Explicit exclusion may cite strong Z-drift or other manual concerns; never infer exclusion automatically.
