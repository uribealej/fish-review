"""Give response stimuli stable, human-readable numeric and letter codes."""
import re
from pathlib import Path

import pandas as pd


def letter_code(index):
    """Return A..Z, AA..AZ etc for a zero-based display index."""
    code = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        code = chr(65 + remainder) + code
    return code


def stimulus_catalog(fish, stimuli_dir, selected_blocks):
    """Map only observed stimuli, following the pipeline's trajectory-file order."""
    paths = sorted(Path(stimuli_dir).glob("*trajectory.*"))
    logs = list((fish.source / "01_raw/2p/metadata").glob("*_block_log.csv"))
    if not paths or len(logs) != 1 or not selected_blocks:
        raise ValueError("Select the trajectory folder and acquisition blocks to display the stimulus map.")
    table = pd.read_csv(logs[0])
    extracted = table["event"].astype(str).str.extract(r"^(B\d+)_stim\d+_(.+)$")
    names = list(dict.fromkeys(extracted.loc[extracted[0].isin(selected_blocks), 1].dropna()))
    if not names:
        raise ValueError("No stimulus presentations found for the selected blocks.")
    rows = []
    matched = set()
    for path in paths:
        name = path.stem.removesuffix("_trajectory")
        matches = [observed for observed in names if observed.casefold() == name.casefold()]
        if len(matches) > 1 or any(value in matched for value in matches):
            raise ValueError(f"Ambiguous stimulus name: {name}")
        if matches:
            observed = matches[0]
            index = len(rows)
            rows.append({"Number": index + 1, "Letter": letter_code(index), "Stimulus": observed})
            matched.add(observed)
    if matched != set(names):
        raise ValueError("Missing trajectory files for: " + ", ".join(sorted(set(names) - matched)))
    return rows


def parse_stimulus_order(text, catalog):
    """Resolve numbers, letters or full names, rejecting missing/repeated stimuli."""
    if not text.strip():
        return [row["Stimulus"] for row in catalog]
    tokens = [token for token in re.split(r"[,;\s]+", text.strip()) if token]
    result = []
    for token in tokens:
        matches = {row["Stimulus"] for row in catalog
                   if token.casefold() in (str(row["Number"]), row["Letter"].casefold(),
                                           row["Stimulus"].casefold())}
        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous stimulus code: {token}")
        result.append(matches.pop())
    if len(result) != len(set(result)):
        raise ValueError("A stimulus is repeated in the order. Use every code once.")
    missing = [row["Stimulus"] for row in catalog if row["Stimulus"] not in result]
    if missing:
        raise ValueError("Add the missing stimuli: " + ", ".join(missing))
    return result
