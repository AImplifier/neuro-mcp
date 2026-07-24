# Example 5: neuroii Integration

The neuroii annotation round-trip — both the default (`not_configured`) and
live paths. Grounded in `testing/full_verify.py`'s `neuroii` section, which
exercises both via a mock HTTP server.

## Not configured (`NEUROII_API_URL` unset, the default)

```python
neuroii_push_recording(recording_id=1)
# -> {"status": "not_configured", "contract": {...}}

neuroii_create_viz_session(recording_id=1)
# -> {"status": "not_configured", "contract": {...}}

neuroii_pull_annotations(recording_id=1)
# -> {"status": "not_configured", "contract": {...}}
```

`persona_clinician.py` notes this is a dead end for a non-technical user —
"send this to neuroii" returns a developer-facing contract blob rather than
a viewer link — until the neuroii app implements the documented endpoints
(see [neuroii Integration](../tools/neuroii.md)).

## Configured (`NEUROII_API_URL` set to a live neuroii instance)

```python
neuroii_push_recording(recording_id=1)
# -> {"status": "pushed", "neuroii_recording_id": "nii-42",
#     "url": "http://neuroii.example/view/42"}

neuroii_create_viz_session(recording_id=1)
# -> {"status": "created", "session_url": "http://neuroii.example/viz/abc",
#     "expires_at": "2026-12-31T00:00:00Z"}

neuroii_pull_annotations(recording_id=1)
# -> {"status": "pulled", "n_pulled": 2, "annotations": [...]}

list_annotations(recording_id=1)
# -> {"annotations": [{"source": "neuroii", ...}, ...]}
```

Pulled annotations are persisted as ordinary, independently-audited
`Annotation` rows tagged `source="neuroii"` — they flow through
`list_annotations`/`update_annotation`/`void_annotation` exactly like
annotations added locally via `add_annotation`.

## Full sequence at a glance

```
neuroii_push_recording -> neuroii_create_viz_session -> neuroii_pull_annotations -> list_annotations
```
