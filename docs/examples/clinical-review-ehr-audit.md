# Example 1: Clinical Review, Annotation & EHR Audit

A clinician's journey from a new patient through review, annotation, and a
versioned diagnosis — the workflow `testing/persona_clinician.py` simulates
and `testing/full_verify.py`'s `data`/`annot`/`audit` sections exercise
programmatically. Demonstrates the versioned/audited amend-and-void model
described in [Clinical-safety model](../index.md#clinical-safety-model-ehr-annotations).

## 1. Register the patient

```python
register_subject(
    external_id="JANE-1985",
    demographics={"name": "Jane D.", "birthDate": "1985-04-02"},
    actor="dr_smith",
)
# -> {"outcome": "created", "id": 1, "external_id": "JANE-1985", ...}
```

The clinician (or the agent on their behalf) invents a stable `external_id`
and supplies `actor` — there's no logged-in identity, so this must come from
the calling application.

## 2. Import her EEG recording

```python
import_recording(
    file_path="/data/jane_rest.fif",
    subject_external_id="JANE-1985",
    task="rest",
    dataset_name="clinic",
    session_id="jane",
)
# -> {"outcome": "imported", "session_id": "jane", "id": 1, "bids_path": "...", ...}
```

One call files the recording under the patient in BIDS **and** opens it in a
processing session (`load_into_session=True` by default) — no separate
`load_neuro` needed. Keep the returned `id` — it's the `recording_id` used
below.

## 3. Review and clean up

```python
plot_raw(session_id="jane", duration=5.0)
# -> {"image": "data:image/png;base64,...", "kind": "raw_traces"}

filter_neuro(session_id="jane", l_freq=1.0, h_freq=40.0, notch_freqs=[50.0])
# -> {"status": "filtered", "highpass": 1.0, "lowpass": 40.0, ...}

detect_bad_channels(session_id="jane", z_threshold=3.0)
# -> {"flagged": [...], "marked_as_bad": true, "current_bads": [...]}
```

Plots return inline PNG data URIs the agent can display without a second
round trip.

## 4. Annotate a finding

```python
add_annotation(
    recording_id=1, onset=5.0, label="suspected spike", actor="dr_smith",
    duration=0.2, channels=["Oz"],
)
# -> {"outcome": "created", "logical_id": "<uuid>", "version": 1, ...}
```

Save `logical_id` — it's what you'll use to correct this annotation later.

```python
update_annotation(
    logical_id="<uuid>", actor="dr_smith",
    label="sharp wave", note="reclassified on review",
)
# -> {"outcome": "updated", "version": 2, "label": "sharp wave", ...}
```

The original (`"suspected spike"`, v1) is retained with status `amended`;
`list_annotations` now shows only the current label. This is the same
edit-preserves-history model as EHR records.

## 5. Record a diagnosis, then update it

```python
add_ehr_record(
    subject_external_id="JANE-1985", resource_type="Condition",
    fhir={"resourceType": "Condition", "code": {"text": "focal epilepsy"}},
    actor="dr_smith", note="clinical impression",
)
# -> {"outcome": "created", "logical_id": "<ehr-uuid>", "version": 1, ...}

amend_ehr_record(
    logical_id="<ehr-uuid>",
    fhir={"resourceType": "Condition", "code": {"text": "focal epilepsy, left temporal"}},
    actor="dr_smith", note="localized after MRI",
)
# -> {"outcome": "amended", "version": 2, "status": "active", ...}
```

`fhir` is a raw FHIR resource dict — there's no schema validation on it, so
the calling agent is responsible for well-formed FHIR.

## 6. Read back the current state

```python
get_subject(external_id="JANE-1985")
# -> {"subject": {...}, "ehr_records": [{"version": 2, "fhir": {...}, ...}]}

get_ehr_history(logical_id="<ehr-uuid>")
# -> {"logical_id": "<ehr-uuid>", "versions": [
#       {"version": 2, "status": "active", ...},
#       {"version": 1, "status": "amended", ...},
#    ]}
```

`get_subject` hides superseded versions — the clinician sees the right "now"
state. `get_ehr_history` shows the full trail when you need it.

## 7. Who changed what, and when

```python
get_audit_log(target_table="ehr_records")
# -> {"entries": [
#       {"actor": "dr_smith", "action": "amend", "target_id": 1, ...},
#       {"actor": "dr_smith", "action": "create", "target_id": 1, ...},
#    ]}
```

A plain "who changed Jane's diagnosis" question maps directly to a real
audit trail with actor, action, and before/after payloads — every mutation
in steps 4–5 produced one of these rows automatically.

## Full sequence at a glance

```
register_subject -> import_recording -> plot_raw -> filter_neuro ->
detect_bad_channels -> add_annotation -> update_annotation ->
add_ehr_record -> amend_ehr_record -> get_subject -> get_ehr_history ->
get_audit_log
```
