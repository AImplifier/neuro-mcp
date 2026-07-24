"""Data, EHR, dataset, and annotation management tools (Postgres + BIDS).

Clinical records are versioned and audited: edits never overwrite or delete.
See :mod:`neuro_mcp.db.store` for the amend/void/history mechanics.
"""

from __future__ import annotations

from typing import Any

import mne

from .app import mcp
from .bids.layout import import_to_bids, summarize_bids
from .config import get_config
from .db import store
from .db.models import (
    STATUS_ACTIVE,
    STATUS_VOID,
    Annotation,
    Dataset,
    Derivative,
    EHRRecord,
    Recording,
    Subject,
)
from .session import store as session_store
from .utils import to_jsonable

mne.set_log_level("ERROR")


# --------------------------------------------------------------------------- #
# Subjects & EHR
# --------------------------------------------------------------------------- #
@mcp.tool()
def register_subject(
    external_id: str, demographics: dict | None = None, actor: str = "system"
) -> dict:
    """Register a study/patient subject (FHIR Patient-shaped demographics).

    Args:
        external_id: Your stable identifier for the subject (de-identified).
        demographics: Optional dict (e.g. {"gender": "female", "birthDate": "1990-01-01"}).
        actor: Who is performing this action (recorded for audit).
    """
    with store.get_session() as s:
        existing = s.query(Subject).filter_by(external_id=external_id).one_or_none()
        if existing:
            return to_jsonable({"outcome": "exists", **store.to_dict(existing)})
        subj = Subject(external_id=external_id, demographics=demographics or {})
        s.add(subj)
        s.flush()
        store.record_audit(
            s, actor=actor, action="create", target_table="subjects",
            target_id=subj.id, before=None, after=store.to_dict(subj),
        )
        return to_jsonable({"outcome": "created", **store.to_dict(subj)})


@mcp.tool()
def get_subject(external_id: str) -> dict:
    """Return a subject and their *current* (non-voided) EHR records."""
    with store.get_session() as s:
        subj = s.query(Subject).filter_by(external_id=external_id).one_or_none()
        if not subj:
            raise ValueError(f"No subject '{external_id}'.")
        records = (
            s.query(EHRRecord)
            .filter_by(subject_id=subj.id)
            .order_by(EHRRecord.logical_id, EHRRecord.version.desc())
            .all()
        )
        current: dict[str, dict] = {}
        for r in records:
            if r.status == STATUS_VOID:
                continue
            if r.logical_id not in current:  # first seen = highest version
                current[r.logical_id] = store.to_dict(r)
        return to_jsonable(
            {"subject": store.to_dict(subj), "ehr_records": list(current.values())}
        )


@mcp.tool()
def add_ehr_record(
    subject_external_id: str,
    resource_type: str,
    fhir: dict,
    actor: str,
    note: str | None = None,
) -> dict:
    """Add an EHR record (a FHIR resource such as Condition or Observation).

    Creates version 1 of a new logical record. Use amend_ehr_record to change it.

    Args:
        subject_external_id: The subject this record belongs to.
        resource_type: FHIR resourceType, e.g. 'Condition', 'Observation'.
        fhir: The FHIR resource body as a dict.
        actor: Clinician/author id (recorded, audited).
        note: Optional context for the entry.
    """
    with store.get_session() as s:
        subj = s.query(Subject).filter_by(external_id=subject_external_id).one_or_none()
        if not subj:
            raise ValueError(f"No subject '{subject_external_id}'.")
        rec = EHRRecord(
            logical_id=store.new_logical_id(),
            version=1,
            status=STATUS_ACTIVE,
            subject_id=subj.id,
            resource_type=resource_type,
            fhir=fhir,
            author=actor,
            note=note,
        )
        s.add(rec)
        s.flush()
        store.record_audit(
            s, actor=actor, action="create", target_table="ehr_records",
            target_id=rec.id, before=None, after=store.to_dict(rec),
        )
        return to_jsonable({"outcome": "created", **store.to_dict(rec)})


@mcp.tool()
def amend_ehr_record(
    logical_id: str, fhir: dict, actor: str, note: str | None = None
) -> dict:
    """Amend an EHR record: create a new audited version with an updated FHIR body.

    The prior version is retained (status 'amended') and remains in the history;
    this is how a clinician corrects or updates a record without destroying the
    original. Returns the new current version.

    Args:
        logical_id: The logical id of the record to amend (stable across versions).
        fhir: The updated FHIR resource body.
        actor: Clinician making the amendment (audited).
        note: Reason for the amendment (recommended).
    """
    with store.get_session() as s:
        new_row = store.amend_versioned(
            s, EHRRecord, logical_id, actor=actor, changes={"fhir": fhir},
            note=note, table_name="ehr_records",
            copy_fields=["subject_id", "resource_type"],
        )
        return to_jsonable({"outcome": "amended", **store.to_dict(new_row)})


@mcp.tool()
def get_ehr_history(logical_id: str) -> dict:
    """Return every version of an EHR record, oldest first (full audit trail)."""
    with store.get_session() as s:
        versions = store.history(s, EHRRecord, logical_id)
        return to_jsonable({"logical_id": logical_id, "versions": versions})


@mcp.tool()
def void_ehr_record(logical_id: str, actor: str, note: str) -> dict:
    """Soft-void an EHR record (mark 'entered-in-error'). It is kept, not deleted.

    Args:
        logical_id: Record to void.
        actor: Clinician performing the retraction (audited).
        note: Reason (required for a void).
    """
    with store.get_session() as s:
        row = store.void_versioned(
            s, EHRRecord, logical_id, actor=actor, note=note, table_name="ehr_records"
        )
        return to_jsonable({"outcome": "voided", **store.to_dict(row)})


# --------------------------------------------------------------------------- #
# Datasets & recordings (BIDS)
# --------------------------------------------------------------------------- #
@mcp.tool()
def register_dataset(
    name: str, source: str | None = None, metadata: dict | None = None
) -> dict:
    """Register a dataset (a named collection of recordings)."""
    with store.get_session() as s:
        existing = s.query(Dataset).filter_by(name=name).one_or_none()
        if existing:
            return to_jsonable({"outcome": "exists", **store.to_dict(existing)})
        cfg = get_config()
        ds = Dataset(
            name=name, source=source, bids_root=str(cfg.bids_root),
            dataset_metadata=metadata or {},
        )
        s.add(ds)
        s.flush()
        return to_jsonable({"outcome": "created", **store.to_dict(ds)})


@mcp.tool()
def import_recording(
    file_path: str,
    subject_external_id: str,
    task: str = "rest",
    dataset_name: str | None = None,
    session_id: str = "default",
    load_into_session: bool = True,
) -> dict:
    """Import a recording into the BIDS store and register it in the database.

    Loads the file with MNE, writes it into the BIDS tree under the subject, and
    inserts a recordings row. Optionally loads it into an in-memory processing
    session so you can immediately run filter_neuro/epoch_neuro/etc.

    Args:
        file_path: Path to the recording (EDF/FIF/SET/BDF/BrainVision/…).
        subject_external_id: Subject to attach the recording to (created if missing).
        task: BIDS task label.
        dataset_name: Optional dataset to group under (created if missing).
        session_id: Processing session id to load into.
        load_into_session: If True, populate the processing session for analysis.
    """
    cfg = get_config()
    raw = mne.io.read_raw(file_path, preload=True)
    bids_path = import_to_bids(
        raw, cfg.bids_root, subject=_bids_label(subject_external_id), task=task
    )
    with store.get_session() as s:
        subj = s.query(Subject).filter_by(external_id=subject_external_id).one_or_none()
        if not subj:
            subj = Subject(external_id=subject_external_id, demographics={})
            s.add(subj)
            s.flush()
        dataset_id = None
        if dataset_name:
            ds = s.query(Dataset).filter_by(name=dataset_name).one_or_none()
            if not ds:
                ds = Dataset(name=dataset_name, bids_root=str(cfg.bids_root),
                             dataset_metadata={})
                s.add(ds)
                s.flush()
            dataset_id = ds.id
        rec = Recording(
            dataset_id=dataset_id,
            subject_id=subj.id,
            bids_path=bids_path,
            source_path=file_path,
            modality="eeg",
            sfreq=float(raw.info["sfreq"]),
            n_channels=len(raw.ch_names),
            duration_sec=float(raw.times[-1]),
            provenance={"imported_from": file_path},
        )
        s.add(rec)
        s.flush()
        store.record_audit(
            s, actor="system", action="create", target_table="recordings",
            target_id=rec.id, before=None, after=store.to_dict(rec),
        )
        result = store.to_dict(rec)

    if load_into_session:
        sess = session_store.get_or_create(session_id)
        sess.raw = raw
        sess.source_path = file_path
        sess.log(f"Imported recording {result['id']} from {file_path}")

    return to_jsonable({"outcome": "imported", "session_id": session_id, **result})


@mcp.tool()
def query_datasets() -> dict:
    """List all registered datasets with recording counts."""
    with store.get_session() as s:
        out = []
        for ds in s.query(Dataset).all():
            n = s.query(Recording).filter_by(dataset_id=ds.id).count()
            d = store.to_dict(ds)
            d["n_recordings"] = n
            out.append(d)
        return to_jsonable({"datasets": out, "bids": summarize_bids(get_config().bids_root)})


@mcp.tool()
def list_recordings(
    subject_external_id: str | None = None, dataset_name: str | None = None
) -> dict:
    """List recordings, optionally filtered by subject or dataset."""
    with store.get_session() as s:
        q = s.query(Recording)
        if subject_external_id:
            subj = s.query(Subject).filter_by(external_id=subject_external_id).one_or_none()
            q = q.filter_by(subject_id=subj.id if subj else -1)
        if dataset_name:
            ds = s.query(Dataset).filter_by(name=dataset_name).one_or_none()
            q = q.filter_by(dataset_id=ds.id if ds else -1)
        return to_jsonable({"recordings": [store.to_dict(r) for r in q.all()]})


# --------------------------------------------------------------------------- #
# Annotations (versioned, like EHR)
# --------------------------------------------------------------------------- #
@mcp.tool()
def add_annotation(
    recording_id: int,
    onset: float,
    label: str,
    actor: str,
    duration: float = 0.0,
    channels: list[str] | None = None,
    payload: dict | None = None,
    source: str = "mne",
) -> dict:
    """Add a clinician/algorithm annotation to a recording (version 1)."""
    with store.get_session() as s:
        if not s.get(Recording, recording_id):
            raise ValueError(f"No recording id {recording_id}.")
        ann = Annotation(
            logical_id=store.new_logical_id(),
            version=1,
            status=STATUS_ACTIVE,
            recording_id=recording_id,
            author=actor,
            onset=onset,
            duration=duration,
            label=label,
            channels=channels or [],
            payload=payload or {},
            source=source,
        )
        s.add(ann)
        s.flush()
        store.record_audit(
            s, actor=actor, action="create", target_table="annotations",
            target_id=ann.id, before=None, after=store.to_dict(ann),
        )
        return to_jsonable({"outcome": "created", **store.to_dict(ann)})


@mcp.tool()
def update_annotation(
    logical_id: str,
    actor: str,
    onset: float | None = None,
    duration: float | None = None,
    label: str | None = None,
    channels: list[str] | None = None,
    payload: dict | None = None,
    note: str | None = None,
) -> dict:
    """Edit an annotation by creating a new audited version (original retained)."""
    changes: dict[str, Any] = {}
    if onset is not None:
        changes["onset"] = onset
    if duration is not None:
        changes["duration"] = duration
    if label is not None:
        changes["label"] = label
    if channels is not None:
        changes["channels"] = channels
    if payload is not None:
        changes["payload"] = payload
    if not changes:
        raise ValueError("No changes provided to update_annotation.")
    with store.get_session() as s:
        new_row = store.amend_versioned(
            s, Annotation, logical_id, actor=actor, changes=changes, note=note,
            table_name="annotations",
            copy_fields=["recording_id", "onset", "duration", "label",
                         "channels", "payload", "source"],
        )
        return to_jsonable({"outcome": "updated", **store.to_dict(new_row)})


@mcp.tool()
def list_annotations(recording_id: int, include_voided: bool = False) -> dict:
    """List the *current* version of each annotation on a recording."""
    with store.get_session() as s:
        rows = (
            s.query(Annotation)
            .filter_by(recording_id=recording_id)
            .order_by(Annotation.logical_id, Annotation.version.desc())
            .all()
        )
        current: dict[str, dict] = {}
        for r in rows:
            if r.logical_id in current:
                continue
            if r.status == STATUS_VOID and not include_voided:
                current[r.logical_id] = None  # mark seen, skip
                continue
            current[r.logical_id] = store.to_dict(r)
        return to_jsonable(
            {"recording_id": recording_id,
             "annotations": [v for v in current.values() if v is not None]}
        )


@mcp.tool()
def void_annotation(logical_id: str, actor: str, note: str) -> dict:
    """Soft-void an annotation (mark 'entered-in-error'); kept, not deleted."""
    with store.get_session() as s:
        row = store.void_versioned(
            s, Annotation, logical_id, actor=actor, note=note, table_name="annotations"
        )
        return to_jsonable({"outcome": "voided", **store.to_dict(row)})


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_audit_log(
    target_table: str | None = None, target_id: int | None = None, limit: int = 50
) -> dict:
    """Return recent audit-log entries, optionally filtered by target."""
    from .db.models import AuditLog

    with store.get_session() as s:
        q = s.query(AuditLog)
        if target_table:
            q = q.filter_by(target_table=target_table)
        if target_id is not None:
            q = q.filter_by(target_id=target_id)
        rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
        return to_jsonable({"entries": [store.to_dict(r) for r in rows]})


def _bids_label(external_id: str) -> str:
    """BIDS subject labels must be alphanumeric; sanitize the external id."""
    return "".join(ch for ch in external_id if ch.isalnum()) or "unknown"
