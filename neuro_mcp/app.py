"""The shared FastMCP application instance.

Kept in its own module so tool modules (core analysis, source imaging) can each
register tools on the same server without importing one another.
"""

from __future__ import annotations

import mne
from fastmcp import FastMCP

# Keep MNE's own logging quiet so it doesn't pollute the stdio transport.
mne.set_log_level("ERROR")

mcp = FastMCP(
    "neuro-analysis",
    instructions=(
        "An MCP for NeuroAgents that assist clinicians and researchers: MNE "
        "processing, a Postgres+BIDS data/EHR store, and NeuroII web "
        "visualization.\n\n"
        "PROCESSING (in-memory session, threaded by session_id): "
        "load_neuro -> filter_neuro -> set_montage -> set_reference -> "
        "detect_bad_channels -> run_ica/apply_ica -> find_events -> epoch_neuro -> "
        "compute_psd/compute_erp/time_frequency. Source imaging after epoching: "
        "fetch_template_head -> compute_forward -> compute_noise_covariance -> "
        "make_inverse_operator -> apply_inverse (or apply_lcmv_beamformer) -> "
        "extract_label_timecourses.\n\n"
        "DATA/EHR (persistent, in Postgres+BIDS): register_subject, add_ehr_record, "
        "amend_ehr_record (versioned+audited), get_ehr_history, void_ehr_record; "
        "import_recording, register_dataset, query_datasets; add_annotation, "
        "update_annotation, void_annotation; get_audit_log. EHR/annotations are "
        "never overwritten or hard-deleted — edits create audited new versions.\n\n"
        "NEUROII (web visualization): neuroii_push_recording, "
        "neuroii_create_viz_session, neuroii_pull_annotations.\n\n"
        "For processing, pick a stable session_id (e.g. 'default') and call "
        "load_neuro first. For data/EHR, subjects/recordings persist across sessions."
    ),
)
