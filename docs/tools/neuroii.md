# neuroii Integration

3 tools in `neuro_mcp/tools_neuroii.py`. **neuroii integration is
greenfield** — the tools define and return the expected REST contract (see
`neuro_mcp/neuroii/client.py`) so the neuroii app has a fixed target to
implement against. Until [`NEUROII_API_URL`](../configuration.md) is set,
each tool returns `{"status": "not_configured", "contract": {...}}` instead
of erroring.

### `neuroii_push_recording(recording_id)`
Push a recording and its derivatives to neuroii for clinician viewing.
Calls `POST /api/v1/recordings` once configured; returns
`{"status": "pushed", "neuroii_recording_id": ..., "url": ...}`.

### `neuroii_create_viz_session(recording_id, layout=None)`
Create a shareable neuroii viz session. Calls
`POST /api/v1/viz-sessions` once configured; returns
`{"status": "created", "session_url": ..., "expires_at": ...}`.

### `neuroii_pull_annotations(recording_id, actor="neuroii")`
Pull clinician annotations from neuroii and persist each as a new,
independently-audited `Annotation` row with `source="neuroii"` (via the same
versioned-annotation mechanics as `add_annotation`). Calls
`GET /api/v1/recordings/{id}/annotations` once configured; returns
`{"status": "pulled", "n_pulled": N, "annotations": [...]}`. Pulled
annotations then show up through `list_annotations` like any other
annotation, tagged with their `source`.

## The REST contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/recordings` | Register a recording + derivatives for viewing |
| `POST` | `/api/v1/viz-sessions` | Create a shareable viz session |
| `GET` | `/api/v1/recordings/{id}/annotations` | Fetch clinician annotations to pull back |

The neuroii web app itself isn't live yet — until then, every call returns the
`not_configured` contract shown above rather than doing anything real.
