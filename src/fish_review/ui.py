"""Review widgets, explicit save actions and plot generation controls."""
import copy
import json
from pathlib import Path

import streamlit as st

from fish_review.plot_generation import generate_segmentation, generate_responses, plotting_defaults, generate_fluorescence
from fish_review.reviews import (
    QUALITY, SEVERITY, RESPONSES, BIAS, SEGMENTATION, DECISIONS, STAGES,
    load_review, save_review, review_status, evidence_snapshot,
)
from fish_review.summaries import export_summaries
from fish_review.stimulus_order import stimulus_catalog, parse_stimulus_order
from fish_review.viewer_server import local_viewer_server
from fish_review.reviews import upgrade_record, apply_review_action


def choose(label, options, value, key):
    """Initialize a widget from the persisted or in-session draft value."""
    return st.selectbox(label, options, index=options.index(value), key=key,
                        format_func=(lambda item: {"undecided": "Undecided", "use": "Use", "exclude": "Exclude", "review": "Needs review"}.get(item, item)))


def stage_buttons(stage, prefix):
    """Provide an explicit save-and-stop action at each review stage."""
    if st.button("Save and continue later", key=f"{prefix}_pause_{stage}",
                 help=f"Saves your answers and pauses the review at {stage}. The final decision is unchanged."):
        return ("pause", stage)
    return None



def show_manifest(folder, filename):
    """Display a generated artifact and its recorded sources/settings."""
    path = folder / filename
    if not path.is_file():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        stale = []
        for source in record.get("sources", []):
            try:
                stat = Path(source["path"]).stat()
                if stat.st_mtime_ns != source["mtime_ns"] or stat.st_size != source["size"]:
                    stale.append(source["path"])
            except OSError:
                stale.append(source["path"])
        if stale:
            st.warning("Some inputs changed or cannot be accessed. Regenerate these plots before reassessing them.")
        if "counts" in record:
            cells = sum(row["cells"] for row in record["counts"])
            noncells = sum(row["non_cells"] for row in record["counts"])
            left, middle, right = st.columns(3)
            left.metric("Cells", f"{cells:,}")
            middle.metric("Non-cells", f"{noncells:,}")
            right.metric("Total ROIs", f"{cells + noncells:,}")
            st.dataframe(record["counts"], hide_index=True, width="stretch")
        for output in record["outputs"]:
            st.image(output, width="stretch")
        with st.expander("Figure settings and source files"):
            st.json(record)
        return True
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error(f"Could not display saved figures: {error}")
        return False


def refresh_summaries(experiments, config):
    """Regenerate derived summaries while reporting independent export failures."""
    try:
        with st.spinner("Updating experiment and global summaries..."):
            _, errors = export_summaries(experiments, config["derived_root"])
        for error in errors:
            st.warning(error)
    except (OSError, ValueError) as error:
        st.warning(f"Review/figure saved, but summary export needs another attempt: {error}")


def response_settings(fish, scan, config, prefix):
    """Expose fish-specific paths and timing without importing notebook example values."""
    try:
        defaults = plotting_defaults(fish, scan["metadata"], config["derived_root"],
                                     stimuli_root=config.get("stimuli_root"))
    except (OSError, ValueError, KeyError) as error:
        st.warning(f"Cannot infer plotting settings: {error}")
        return None
    manifest = fish.experiment_dir / "plots/general" / f"{fish.fish_id}_responses.json"
    if manifest.is_file():
        try:
            defaults.update(json.loads(manifest.read_text())["settings"])
        except (OSError, ValueError, KeyError):
            pass
    settings = copy.deepcopy(defaults)
    with st.expander("Response plot settings"):
        st.caption("Uses already merged traces. Confirm timing for this fish. Windows are relative to stimulus onset.")
        settings["stimuli_dir"] = st.text_input("Stimulus trajectory folder", defaults["stimuli_dir"], key=prefix+"_stimuli")
        blocks = st.text_input("Acquisition blocks, in order", ", ".join(defaults["selected_blocks"]), key=prefix+"_blocks")
        settings["selected_blocks"] = [value.strip() for value in blocks.split(",") if value.strip()]
        settings["imaging_fps"] = st.number_input("Imaging rate (Hz)", min_value=0.0,
                                                  value=defaults["imaging_fps"] or 0.0, key=prefix+"_ifps")
        settings["stimulus_fps"] = st.number_input("Stimulus rate (Hz)", min_value=0.0,
                                                   value=defaults["stimulus_fps"] or 0.0, key=prefix+"_sfps")
        settings["frames_per_block"] = st.number_input("Imaging frames per block", min_value=0,
                                                        value=defaults["frames_per_block"] or 0, key=prefix+"_frames")
        settings["pre_stimulus_sec"] = st.number_input("Seconds before onset", min_value=0.0,
                                                       value=defaults["pre_stimulus_sec"], key=prefix+"_pre")
        settings["post_stimulus_sec"] = st.number_input("Seconds from onset onward", min_value=0.1,
                                                        value=defaults["post_stimulus_sec"], key=prefix+"_post")
        settings["sort_by_correlation"] = st.checkbox("Sort raster neurons by correlation",
                                                        value=defaults["sort_by_correlation"], key=prefix+"_sort")
    st.markdown("**Stimulus map and plot order**")
    try:
        catalog = stimulus_catalog(fish, settings["stimuli_dir"], settings["selected_blocks"])
        st.dataframe(catalog, hide_index=True, width="stretch", height=min(440, 40 + 35 * len(catalog)))
        number_for_name = {row["Stimulus"]: str(row["Number"]) for row in catalog}
        experiment_key = "response_order_" + str(fish.experiment_dir.resolve())
        shared_orders = st.session_state.setdefault("experiment_response_orders", {})
        saved_order = shared_orders.get(experiment_key) or defaults.get("stimulus_order") or [row["Stimulus"] for row in catalog]
        initial = ", ".join(number_for_name.get(name, name) for name in saved_order)
        order_key = experiment_key + json.dumps(list(number_for_name))
        order = st.text_input("Plot order: numbers, letters, or names", initial, key=order_key,
                              help="For example 3, 1, 2 or C, A, B. Include every stimulus once. Blank uses the map order. Valid orders are remembered for this experiment during this browser session.")
        settings["stimulus_order"] = parse_stimulus_order(order, catalog)
        shared_orders[experiment_key] = list(settings["stimulus_order"])
        st.caption("Plot order: " + " > ".join(settings["stimulus_order"]))
    except (OSError, ValueError, KeyError) as error:
        st.warning(str(error))
        return None

    return settings


def render_review(fish, scan, config, experiments, clear_scans):
    """Render manual controls and save explicitly, preserving drafts when navigating."""
    prefix = f"review_{fish.experiment_id}_{fish.fish_id}"
    session_key = prefix + "_document"
    if session_key not in st.session_state:
        try:
            record, token = load_review(fish)
        except (OSError, ValueError) as error:
            st.error(str(error))
            return
        st.session_state[session_key] = {"record": record, "token": token,
                                         "draft": copy.deepcopy(record["manual"])}
    document = st.session_state[session_key]
    if "progress" not in document["draft"]:
        draft_record = copy.deepcopy(document["record"])
        draft_record["manual"] = document["draft"]
        document["draft"] = upgrade_record(draft_record)["manual"]
    document["record"] = upgrade_record(document["record"])
    manual = copy.deepcopy(document["draft"])
    saved = document["record"]
    status = review_status(saved)
    st.subheader("Decision: " + status["Decision / reason"])
    st.markdown("**Review progress: " + status["Review progress"] + "**")
    st.caption("Last saved: " + saved.get("updated_at", "Not saved yet"))
    if saved.get("availability") and saved["availability"] != evidence_snapshot(scan):
        st.warning("Supporting files have changed since this review was saved. Your answers have been kept.")
    if st.button("Undo unsaved changes", key=prefix+"_reload"):
        for key in list(st.session_state):
            if key.startswith(prefix):
                del st.session_state[key]
        st.rerun()
    manual["comment"] = st.text_area("Fish comment", manual["comment"], height=100,
                                      key=prefix+"_comment",
                                      help="Visible in experiment and global summaries after saving.")
    st.caption("Edits stay in this browser session while you navigate. Use Save review to keep them after closing the app.")
    tabs = st.tabs(["Available data", "Imaging QC", "Suite2p", "Raw fluorescence", "Responses", "Final decision", "Metadata"])
    actions = []
    with tabs[0]:
        st.caption("File availability only. Raw imaging is not required on this computer.")
        st.dataframe([{key: row[key] for key in ("item", "status", "count", "note")}
                      for row in scan["items"]], hide_index=True, width="stretch")
        with st.expander("Exact detected paths"):
            st.json(scan["items"])
        actions.append(stage_buttons("Source", prefix))

    with tabs[1]:
        st.caption("Your manual assessments. A strong concern does not automatically exclude the fish.")
        for field, label, options in (("quality", "General image quality", QUALITY),
                                      ("bleaching", "Bleaching", SEVERITY),
                                      ("z_drift", "Z-drift", SEVERITY)):
            assessment = manual["imaging_qc"][field]
            assessment["assessment"] = choose(label, options, assessment["assessment"], prefix+"_"+field)
            assessment["comment"] = st.text_input(label + " comment (optional)", assessment["comment"],
                                                    key=prefix+"_"+field+"_comment")
        actions.append(stage_buttons("Imaging QC", prefix))
    with tabs[2]:
        st.caption("Green outlines: cells. Pink outlines: non-cells. Labels come from the saved Suite2p iscell array.")
        if st.button("Generate / refresh segmentation figure", key=prefix+"_segplot"):
            try:
                with st.spinner("Rendering all imaging planes..."):
                    generate_segmentation(fish, config["pipeline_root"])
                clear_scans()
                refresh_summaries(experiments, config)
                st.success("Segmentation figure and cell counts saved.")
            except Exception as error:
                st.error(f"Segmentation generation failed: {error}")
        show_manifest(fish.experiment_dir / "plots/segmentation", f"{fish.fish_id}_segmentation.json")
        with st.expander("Per-plane files"):
            st.dataframe(scan["planes"], hide_index=True, width="stretch")
        manual["suite2p"]["assessment"] = choose("Segmentation quality", SEGMENTATION,
                                                  manual["suite2p"]["assessment"], prefix+"_segqc")
        manual["suite2p"]["comment"] = st.text_input("Segmentation comment", manual["suite2p"]["comment"],
                                                     key=prefix+"_segcomment")
        actions.append(stage_buttons("Suite2p", prefix))
    with tabs[3]:
        fluorescence_controls(fish, scan, config, prefix, experiments, clear_scans)
    with tabs[4]:
        st.caption("Assess responses below. Save and continue later pauses your review; use Final decision to accept or exclude the fish.")
        settings = response_settings(fish, scan, config, prefix)
        if st.button("Generate / refresh response plots", key=prefix+"_responsesplot", disabled=settings is None):
            try:
                with st.spinner("Generating average responses, combined bars and individual repetitions..."):
                    generate_responses(fish, config["pipeline_root"], settings)
                clear_scans()
                refresh_summaries(experiments, config)
                st.success("Response plots regenerated and replaced in plots/general.")
            except Exception as error:
                st.error(f"Response generation failed: {error}")
        show_manifest(fish.experiment_dir / "plots/general", f"{fish.fish_id}_responses.json")
        with st.expander("Other existing plots"):
            if scan["plots"]:
                path = st.selectbox("Saved plot", scan["plots"], format_func=lambda value: Path(value).name,
                                     key=prefix+"_existing")
                try:
                    st.image(path, width="stretch")
                except (OSError, ValueError) as error:
                    st.error(str(error))
        for field, label in (("overall", "Overall response"), ("left", "Response to left stimulation"),
                             ("right", "Response to right stimulation")):
            manual["responses"][field] = choose(label, RESPONSES, manual["responses"][field], prefix+"_"+field)
        manual["responses"]["bias"] = choose("Left/right bias", BIAS, manual["responses"]["bias"], prefix+"_bias")
        manual["responses"]["comment"] = st.text_area("Response comment", manual["responses"]["comment"],
                                                        key=prefix+"_respcomment")
        actions.append(stage_buttons("Responses", prefix))
    with tabs[5]:
        manual["decision"]["status"] = choose("Final decision", DECISIONS,
                                                manual["decision"]["status"], prefix+"_decision")
        manual["decision"]["reason"] = st.text_input(
            "Decision reason", manual["decision"]["reason"], key=prefix+"_reason",
            placeholder="For example: Strong Z-drift prevents use")
        if manual["decision"]["status"] == "exclude":
            manual["decision"]["stage"] = choose(
                "Where was the reason for exclusion identified?", STAGES,
                manual["decision"].get("stage") or "Final decision", prefix+"_exclusion_stage")
        st.caption("Progress is recorded automatically. Finishing the review does not mean the fish is accepted.")
        if st.button("Finish review", key=prefix+"_finish",
                     disabled=manual["decision"]["status"] == "undecided"):
            actions.append(("finish", "Final decision"))
        if manual["decision"]["status"] == "undecided":
            st.caption("Choose Use, Exclude, or Needs review before finishing.")
        actions.append(stage_buttons("Final decision", prefix))

    with tabs[6]:
        st.json(scan["metadata"])
        with st.expander("Saved review record"):
            st.json(saved)
    st.session_state[session_key]["draft"] = copy.deepcopy(manual)
    dirty = manual != saved["manual"]
    if dirty:
        st.warning("You have unsaved review changes.")
    save = st.button("Save review", type="primary", key=prefix+"_save")
    if manual["progress"]["state"] in ("paused", "finished"):
        if st.button("Resume review", key=prefix+"_resume"):
            actions.append(("resume", None))
    action = next((action for action in actions if action), None)
    if save or action:
        action_name, stage = action or ("save", None)
        manual = apply_review_action(manual, action_name, stage)
        try:
            # Refresh evidence at the point of save, including figures generated this run.
            from fish_review.detection import scan_fish
            record, token = save_review(fish, manual, scan_fish(fish), document["token"])
        except (OSError, ValueError) as error:
            st.error(f"Review was not saved: {error}")
            return
        for key in list(st.session_state):
            if key.startswith(prefix):
                del st.session_state[key]
        clear_scans()
        refresh_summaries(experiments, config)
        st.session_state["review_flash"] = f"{fish.fish_id}: review saved."
        st.rerun()

def fluorescence_controls(fish, scan, config, prefix, experiments, clear_scans):
    """Generate/download the HTML and optionally display it inside the app."""
    st.subheader("Raw fluorescence: cells and non-cells")
    st.caption("Scroll through original F traces by plane and cell classification. No delta F/F is calculated.")
    if st.button("Generate / replace raw fluorescence HTML", key=prefix+"_raw_f"):
        try:
            with st.spinner("Building the scrolling fluorescence viewer..."):
                fps = float(scan["metadata"]["framerate"]) if scan["metadata"].get("framerate") else None
                generate_fluorescence(fish, config["pipeline_root"], fps)
            clear_scans()
            refresh_summaries(experiments, config)
            st.success("Raw fluorescence HTML saved in plots/segmentation.")
        except Exception as error:
            st.error(f"Could not generate the raw fluorescence viewer: {error}")
    path = fish.experiment_dir / "plots/segmentation" / f"{fish.fish_id}_raw_fluorescence.html"
    if path.is_file():
        st.caption(str(path))
        try:
            viewer_url = local_viewer_server().register(path)
            st.link_button("Open fluorescence viewer in a new tab", viewer_url)
            if st.checkbox("Show fluorescence traces", value=True, key=prefix+"_open_raw"):
                st.caption("The viewer loads the saved HTML directly. Allow a few seconds for the traces to load.")
                st.iframe(viewer_url, height=1030)
        except OSError as error:
            st.error(f"Could not open the saved fluorescence viewer: {error}")
    else:
        st.info("No raw-fluorescence viewer has been generated for this fish yet. Click Generate / replace raw fluorescence HTML above.")
