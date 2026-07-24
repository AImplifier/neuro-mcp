# neuro-mcp

<!-- mcp-name: io.github.AImplifier/neuro-mcp -->

A MCP for **NeuroAgents** that assist clinicians and researchers. It gives an
AI agent one interface over the whole workflow: signal processing and source
imaging (via [MNE-Python](https://mne.tools)), a persistent dataset + **EHR**
store (Postgres + [BIDS](https://bids.neuroimaging.io)), and **NeuroII** web
visualization.

It builds on the processing core of `eeg-mcp` (copied in and rebranded
`eeg`→`neuro`) and adds the data, EHR, and visualization layers around it.

## Architecture

```
                       neuro-mcp  (FastMCP "neuro-analysis", 54 tools)
 ┌──────────────────────┬────────────────────────┬──────────────────────┐
 │ processing            │ data + EHR store       │ neuroii              │
 │ (MNE + ESI)           │ (Postgres + BIDS)      │ (web visualization)  │
 └──────────────────────┴────────────────────────┴──────────────────────┘
   in-memory                SQLAlchemy +               HTTP client
   session                  BIDS-on-disk               (stub contract)
```

## Actors & workflows

- **Clinician** — reviews a recording, adds/edits **annotations**, and **amends
  EHR** (records a diagnosis/observation, corrects a value), then signs off.
- **Researcher** — discovers datasets, imports to BIDS, runs MNE processing +
  source imaging.
- **Agent** — orchestrates the above via tool calls.

### Clinical-safety model (EHR & annotations)

EHR records and annotations are **versioned, never overwritten or hard-deleted**:

- **Amend = a new audited version.** `amend_ehr_record` / `update_annotation`
  insert a new version; the prior one is retained with status `amended`. So a
  clinician *can* modify the EHR — the current view updates while the original
  and its author are preserved.
- **Retract = soft void.** `void_ehr_record` / `void_annotation` set status
  `entered-in-error`; the record stays in the history.
- **Every mutation is audited** (`audit_log`: actor, action, before/after).
- Mutating tools take an explicit `actor` so authorship is on the record.
  (Auth/RBAC enforcement is planned for v0.2; the fields and trail are in place.)

Each tool returns an `outcome` field for the operation (created/amended/voided/…)
distinct from the record's clinical `status`, so the two never collide.

## Tools (54)

- **Processing** (`load_neuro`, `filter_neuro`, `resample_neuro`, `set_montage`,
  `set_reference`, `detect_bad_channels`, `run_ica`/`apply_ica`, `find_events`,
  `epoch_neuro`, `compute_psd`, `compute_erp`, `time_frequency`, `plot_*`) and
  **source imaging / ESI** (`fetch_template_head` … `extract_label_timecourses`).
- **Data/EHR**: `register_subject`, `get_subject`, `add_ehr_record`,
  `amend_ehr_record`, `get_ehr_history`, `void_ehr_record`; `import_recording`,
  `register_dataset`, `query_datasets`, `list_recordings`; `add_annotation`,
  `update_annotation`, `list_annotations`, `void_annotation`; `get_audit_log`.
- **neuroii**: `neuroii_push_recording`, `neuroii_create_viz_session`,
  `neuroii_pull_annotations`.
- **neuroii visualizations** (standalone interactive HTML, Plotly): `visualize_timeseries`
  (stacked multi-channel EEG with scroll + amplitude buttons), `visualize_averaging`
  (ERP butterfly + scalp topomap scrubbed by a time slider), `visualize_esi`
  (source-estimate ROI time courses + per-time activation bars).

## Install

```bash
conda activate eeg-mcp            # or any Python >=3.10 env
pip install -e .                  # core
pip install -e ".[postgres]"      # + PostgreSQL driver (LGPL-3.0)
pip install -e ".[viz3d]"         # + 3D source rendering (PySide6, LGPL-3.0)
```

## Configure (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///~/.neuro-mcp/neuro_mcp.db` | Store. Prod: `postgresql+psycopg://user:pass@host/db` |
| `BIDS_ROOT` | `~/.neuro-mcp/bids` | Root of the BIDS-on-disk recording tree |
| `NEUROII_API_URL` | *(unset)* | neuroii base URL; unset → tools return the documented contract |
| `NEUROII_API_TOKEN` | *(unset)* | Optional bearer token for neuroii |
| `NEURO_MCP_HOME` | `~/.neuro-mcp` | Base dir for the SQLite + BIDS defaults |

The default (SQLite + a scratch BIDS dir) runs with **zero setup**; point
`DATABASE_URL` at Postgres for a multi-user/clinical deployment.

## Run / register with an MCP host

```bash
python -m neuro_mcp     # stdio transport
```

```json
{
  "mcpServers": {
    "neuro-analysis": {
      "command": "/path/to/envs/eeg-mcp/bin/python",
      "args": ["-m", "neuro_mcp"],
      "env": { "DATABASE_URL": "sqlite:////data/neuro_mcp.db", "BIDS_ROOT": "/data/bids" }
    }
  }
}
```

## neuroii web visualization

Three tools port NEUROII's main views into **self-contained interactive HTML**
files (Plotly, embedded — no server, works offline). Each returns the `.html`
path; interaction runs client-side:

- `visualize_timeseries` (RawView) — MNE-style stacked channels with page
  navigation (⏮ ◀ ▶ ⏭), a page-length box, scroll-to-zoom amplitude, and a grid
  toggle.
- `visualize_averaging` (EvokedView) — the averaged ERP as stacked channels with
  a green time cursor + a scalp topomap; a time slider scrubs both, plus a
  summary sidebar (nave / peak / tmin / tmax).
- `visualize_esi` (EsiView) — a **volumetric** source estimate (fsaverage
  template) rendered to canvas on three orthogonal MRI slices
  (sagittal/coronal/axial) with a black-blue-white-red activation overlay,
  crosshair, L/R and MNI-coordinate labels; the cut planes recentre on each
  frame's peak. Below, the ERP butterfly carries a red current-time cursor and a
  blue half-peak marker. Controls: time slider, global/frame colormap-scale
  toggle, and a mask-threshold slider. Faithful port of NEUROII's views; needs
  epochs (`epoch_neuro` + `set_montage`).

```
visualize_averaging(session_id="s") -> {"out_path": ".../averaging_s.html", ...}
```

## neuroii integration (greenfield)

neuroii integration is not wired yet. The tools define and return the expected
REST contract (see `neuro_mcp/neuroii/client.py`); until `NEUROII_API_URL` is
set they respond `{"status": "not_configured", "contract": {…}}` so the neuroii
app has a fixed target to implement (`POST /api/v1/recordings`,
`POST /api/v1/viz-sessions`, `GET /api/v1/recordings/{id}/annotations`).

## Testing

```bash
python testing/verify.py     # in-memory MCP client, temp SQLite + BIDS, synthetic EEG
```
Covers rename integrity, the processing core, the full clinician EHR/annotation
lifecycle (add → amend → history → void, with audit), and the neuroii stub.
For a full-stack run against Postgres, use `testing/docker-compose.yml`.

## Licensing

neuro-mcp is **BSD-3-Clause** and bundles no third-party source. All required
dependencies are permissive (BSD/MIT/Apache-2.0/PSF). Optional extras carry
their own terms — psycopg (LGPL-3.0), PySide6 (LGPL-3.0, chosen over GPL
PyQt6). Full attribution and compliance notes are in [NOTICE](NOTICE).

## License

BSD-3-Clause — see [LICENSE](LICENSE).
