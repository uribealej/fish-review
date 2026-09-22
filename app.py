"""Select experiments and review fish with saved decisions and supporting plots."""
import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from fish_review.inventory import load_inventory
from fish_review.detection import scan_fish
from fish_review.summaries import overview_row, export_summaries
from fish_review.ui import render_review
from fish_review.discovery_ui import discovery_controls


@st.cache_data(show_spinner=False, ttl=30)
def cached_scan(fish):
    """Cache file scans until the user explicitly refreshes."""
    return scan_fish(fish)


def move_fish(key, fish_ids, direction):
    """Navigate within the chosen experiment."""
    position = fish_ids.index(st.session_state[key])
    st.session_state[key] = fish_ids[max(0, min(len(fish_ids) - 1, position + direction))]


def main():
    """Render experiment selection, overview and individual fish evidence."""
    st.set_page_config(page_title="Fish review", page_icon=":fish:", layout="wide")
    st.title("Fish review")
    st.caption("Choose an experiment, then select a fish from its list.")
    if "review_flash" in st.session_state:
        st.success(st.session_state.pop("review_flash"))
    config_path = Path(os.environ.get("FISH_REVIEW_CONFIG", ROOT / "config.local.json"))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        st.error(f"Configure config.local.json using config.example.json first. {error}")
        return
    discovery_controls(config, cached_scan.clear)
    refresh_requested = st.session_state.pop("discovery_refresh_summaries", False)
    with st.sidebar:
        st.header("Settings")
        st.caption("Fish reviews and summaries")
        if st.button("Refresh file checks", type="primary"):
            cached_scan.clear()
            refresh_requested = True
        with st.expander("Data location"):
            st.code(config["derived_root"], language=None)
    try:
        experiments, warnings = load_inventory(config["derived_root"])
    except (OSError, KeyError) as error:
        st.error(f"Cannot read the inventory location: {error}")
        return
    if st.sidebar.button("Regenerate all summaries") or refresh_requested:
        try:
            with st.spinner("Updating saved summary views..."):
                _, export_errors = export_summaries(experiments, config["derived_root"])
            for error in export_errors:
                st.warning(error)
            st.success("Summary views updated.")
        except (OSError, ValueError) as error:
            st.error(str(error))
    for warning in warnings:
        st.warning(warning)
    if not experiments:
        st.info("No experiment inventories were found.")
        return
    with st.expander("All experiments: global fish summary"):
        if st.checkbox("Show all fish"):
            global_rows = [overview_row(fish, cached_scan(fish))
                           for fishes in experiments.values() for fish in fishes]
            query = st.text_input("Filter all fish by experiment, decision or comment")
            if query:
                global_rows = [row for row in global_rows if query.lower() in str(row).lower()]
            st.dataframe(global_rows, hide_index=True, width="stretch",
                         column_order=["Experiment", "Fish", "Review progress", "Decision / reason", "Fish comment", "Source", "Imaging QC", "Suite2p", "Suite2p review", "Traces", "Response review", "Cells", "Non-cells", "Image quality", "Image quality comment", "Bleaching", "Bleaching comment", "Z-drift", "Z-drift comment", "Suite2p comment", "Left response", "Right response", "Left/right bias", "Response comment", "Final decision", "Decision reason", "Exclusion stage", "Review stage", "Review saved"])
    names = list(experiments)
    default = config.get("default_experiment")
    experiment = st.selectbox("1. Choose an experiment", names,
                                      index=names.index(default) if default in names else 0)
    discovery_controls(config, cached_scan.clear, experiment)
    fishes = experiments[experiment]
    if not fishes:
        st.info("This experiment has no usable fish records.")
        return
    with st.spinner("Checking available files..."):
        scans = {fish.fish_id: cached_scan(fish) for fish in fishes}
    st.subheader(experiment)
    st.caption(f"{len(fishes)} fish. Availability is based on files in the configured locations; quality is assessed separately.")
    st.dataframe([overview_row(fish, scans[fish.fish_id]) for fish in fishes],
                 hide_index=True, width="stretch",
                 column_order=["Fish", "Review progress", "Decision / reason", "Fish comment", "Source", "Imaging QC", "Suite2p", "Suite2p review", "Traces", "Response review", "Cells", "Non-cells", "Image quality", "Image quality comment", "Bleaching", "Bleaching comment", "Z-drift", "Z-drift comment", "Suite2p comment", "Left response", "Right response", "Left/right bias", "Response comment", "Final decision", "Decision reason", "Exclusion stage", "Review stage", "Review saved"])
    ids = [fish.fish_id for fish in fishes]
    key = f"fish_{experiment}"
    if key not in st.session_state or st.session_state[key] not in ids:
        st.session_state[key] = config.get("default_fish") if config.get("default_fish") in ids else ids[0]
    selected = st.selectbox("2. Choose a fish", ids, key=key)
    position = ids.index(selected)
    left, middle, right = st.columns([1, 4, 1])
    left.button("Previous fish", disabled=position == 0, on_click=move_fish, args=(key, ids, -1))
    middle.caption(f"Fish {position + 1} of {len(ids)}")
    right.button("Next fish", disabled=position == len(ids) - 1,
                 on_click=move_fish, args=(key, ids, 1))
    fish = fishes[position]
    scan = scans[selected]
    st.header(selected)
    st.caption("Source > Imaging QC > Suite2p > Traces > Responses > Final decision")
    if scan["error"]:
        st.error(f"Source folder could not be accessed: {scan['error']}")
        return
    render_review(fish, scan, config, experiments, cached_scan.clear)



if __name__ == "__main__":
    main()
