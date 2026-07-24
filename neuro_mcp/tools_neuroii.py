"""neuroii annotation/visualization tools.

Integration is greenfield. When NEUROII_API_URL is unset, each tool returns the
documented contract (status 'not_configured') instead of erroring, so the
neuroii app has a fixed target to build against. When configured, the tools call
the real endpoints and pull clinician annotations back into the database.
"""

from __future__ import annotations

from .app import mcp
from .config import get_config
from .db import store
from .db.models import STATUS_ACTIVE, Annotation, Derivative, Recording
from .neuroii.client import NeuroiiClient, not_configured_response
from .utils import to_jsonable


def _client() -> NeuroiiClient | None:
    cfg = get_config()
    if not cfg.neuroii_api_url:
        return None
    return NeuroiiClient(cfg.neuroii_api_url, token=cfg.neuroii_api_token)


@mcp.tool()
def neuroii_push_recording(recording_id: int) -> dict:
    """Push a recording (and its derivatives) to neuroii for clinician viewing.

    Returns a not_configured contract if NEUROII_API_URL is unset.
    """
    client = _client()
    if client is None:
        return not_configured_response("push_recording")
    with store.get_session() as s:
        rec = s.get(Recording, recording_id)
        if not rec:
            raise ValueError(f"No recording id {recording_id}.")
        derivs = s.query(Derivative).filter_by(recording_id=recording_id).all()
        payload = {
            "recording_id": rec.id,
            "bids_path": rec.bids_path,
            "modality": rec.modality,
            "derivatives": [
                {"kind": d.kind, "uri": d.uri, "params": d.params} for d in derivs
            ],
        }
    try:
        return to_jsonable({"status": "pushed", **client.push_recording(payload)})
    finally:
        client.close()


@mcp.tool()
def neuroii_create_viz_session(recording_id: int, layout: str | None = None) -> dict:
    """Create a shareable neuroii viz/annotation session for a recording.

    Returns a not_configured contract if NEUROII_API_URL is unset.
    """
    client = _client()
    if client is None:
        return not_configured_response("create_viz_session")
    try:
        body = {"recording_id": recording_id}
        if layout:
            body["layout"] = layout
        return to_jsonable({"status": "created", **client.create_viz_session(body)})
    finally:
        client.close()


@mcp.tool()
def neuroii_pull_annotations(recording_id: int, actor: str = "neuroii") -> dict:
    """Pull clinician annotations from neuroii into the database (source='neuroii').

    Each pulled annotation is stored as a new audited annotation. Returns a
    not_configured contract if NEUROII_API_URL is unset.
    """
    client = _client()
    if client is None:
        return not_configured_response("pull_annotations")
    try:
        data = client.pull_annotations(recording_id)
    finally:
        client.close()

    pulled = data.get("annotations", [])
    created = []
    with store.get_session() as s:
        if not s.get(Recording, recording_id):
            raise ValueError(f"No recording id {recording_id}.")
        for a in pulled:
            ann = Annotation(
                logical_id=store.new_logical_id(),
                version=1,
                status=STATUS_ACTIVE,
                recording_id=recording_id,
                author=a.get("author", actor),
                onset=float(a.get("onset", 0.0)),
                duration=float(a.get("duration", 0.0)),
                label=a.get("label", ""),
                channels=a.get("channels", []),
                payload=a.get("payload", {}),
                source="neuroii",
            )
            s.add(ann)
            s.flush()
            store.record_audit(
                s, actor=actor, action="create", target_table="annotations",
                target_id=ann.id, before=None, after=store.to_dict(ann),
            )
            created.append(store.to_dict(ann))
    return to_jsonable(
        {"status": "pulled", "recording_id": recording_id,
         "n_pulled": len(created), "annotations": created}
    )
