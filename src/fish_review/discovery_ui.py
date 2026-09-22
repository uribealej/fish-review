"""Inventory discovery controls."""
from pathlib import Path
import streamlit as st
from fish_review.discovery import inventory_changes, add_discovered_fish


def discovery_controls(config, clear_scans, experiment=None):
    source = Path(config.get("source_root", Path(config["derived_root"]).parent / "2p"))
    with st.expander("Find new fish" if experiment else "Add experiment"):
        st.caption(f"Search fish folders in: {source}")
        name = experiment or st.text_input("New experiment name", placeholder="Exp_8_accumulation_ev")
        if not name:
            return
        key = "discovery_" + name
        if st.button("Scan for new fish", key=key+"_scan"):
            st.session_state[key] = True
        if not st.session_state.get(key):
            return
        try:
            _, original, data, additions, found = inventory_changes(source, config["derived_root"], name)
            st.write(f"{len(found)} matching source folders ? {len(data['fish'])} already registered ? {len(additions)} new fish")
            new_ids = {item["fish_id"] for item in additions}
            if found:
                st.dataframe([{"Fish": fid, "Status": "New" if fid in new_ids else "Already registered", "Source folder": str(path)} for fid, path in found], hide_index=True)
            else:
                st.info("No matching folders found. Check the experiment name; no folders have been created.")
            if additions and st.button("Create experiment and add fish" if original is None else "Add new fish to experiment", key=key+"_add", type="primary"):
                added = add_discovered_fish(source, config["derived_root"], name)
                clear_scans()
                st.session_state["review_flash"] = f"{name}: added {len(added)} fish. Existing entries and reviews were preserved."
                st.session_state["discovery_refresh_summaries"] = True
                st.rerun()
        except (OSError, ValueError, KeyError, TypeError) as error:
            st.error(f"Could not update the inventory: {error}")
