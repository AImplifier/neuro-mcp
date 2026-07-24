# Data & EHR

15 tools in `neuro_mcp/tools_data.py`, backed by a persistent database
(SQLite by default, Postgres for production — see
[Configuration](../configuration.md)) plus a BIDS-on-disk recording tree.
This state is independent of the in-memory processing `session_id` and
survives process restarts.

Clinical records here are **versioned and audited** — see
[Clinical-safety model](../index.md#clinical-safety-model-ehr-annotations)
for the amend/void mechanics shared by EHR records and annotations.

## Subjects & EHR

### `register_subject(external_id, demographics=None, actor="system")`
Register a subject with FHIR-Patient-shaped `demographics` (e.g.
`{"gender": "female", "birthDate": "1990-01-01"}`). Idempotent by
`external_id`: a second call returns `{"outcome": "exists", ...}` rather than
erroring.

### `get_subject(external_id)`
The subject plus their *current* (non-voided, latest-version) EHR records.
Raises if the subject doesn't exist.

### `add_ehr_record(subject_external_id, resource_type, fhir, actor, note=None)`
Create version 1 of a new logical EHR record. `resource_type` is a FHIR
resource type (`"Condition"`, `"Observation"`, ...); `fhir` is the resource
body as a dict. Returns a `logical_id` — save it to amend or void this record
later.

### `amend_ehr_record(logical_id, fhir, actor, note=None)`
Create a new audited version with an updated FHIR body. The prior version is
retained with status `amended`. Returns the new current version.

### `get_ehr_history(logical_id)`
Every version of a record, oldest first — the full audit trail for one
logical record.

### `void_ehr_record(logical_id, actor, note)`
Soft-void (status `entered-in-error`); kept, not deleted. `note` is required.

## Datasets & recordings (BIDS)

### `register_dataset(name, source=None, metadata=None)`
Register a named collection of recordings. Idempotent by `name`.

### `import_recording(file_path, subject_external_id, task="rest", dataset_name=None, session_id="default", load_into_session=True)`
Load a file with MNE, write it into the BIDS tree under the subject, and
insert a `recordings` row — creating the subject and/or dataset if they don't
exist yet. When `load_into_session=True` (default) it **also** populates a
processing session, so one call gets you both a persisted, BIDS-organized
recording and a ready-to-analyze session — no separate `load_neuro` needed.

### `query_datasets()`
All registered datasets with recording counts, plus a BIDS-tree summary.

### `list_recordings(subject_external_id=None, dataset_name=None)`
Recordings, optionally filtered by subject or dataset.

## Annotations (versioned, like EHR)

### `add_annotation(recording_id, onset, label, actor, duration=0.0, channels=None, payload=None, source="mne")`
Add a clinician/algorithm annotation (version 1) to a recording. `onset`/
`duration` in seconds; `channels` is a list of channel names.

### `update_annotation(logical_id, actor, onset=None, duration=None, label=None, channels=None, payload=None, note=None)`
Edit by creating a new audited version (original retained). Raises if no
field is provided to change.

### `list_annotations(recording_id, include_voided=False)`
The current version of each annotation on a recording.

### `void_annotation(logical_id, actor, note)`
Soft-void; kept, not deleted.

## Audit

### `get_audit_log(target_table=None, target_id=None, limit=50)`
Recent audit-log entries (actor, action, before/after), optionally filtered
to one table/row. Every EHR and annotation mutation produces an entry here.

See [Clinical Review, Annotation & EHR Audit](../examples/clinical-review-ehr-audit.md)
for a full worked example.
