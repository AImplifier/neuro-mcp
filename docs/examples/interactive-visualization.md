# Example 4: Interactive Visualization Generation

Producing the three self-contained NEUROII-style HTML viewers — the sequence
`testing/verify_viz.py` and `testing/full_verify.py`'s `viz` section
exercise, including the self-containment checks (embedded Plotly, no
external references) both scripts run against the output files.

## 1. Prepare a session

`visualize_esi` needs the same prep as [source imaging](source-imaging-esi.md)
(montage + reference + epochs); the other two only need epochs or a loaded
recording respectively. Preparing the full chain once covers all three:

```python
load_neuro(file_path="/data/synthetic-raw.fif", session_id="esi")
set_montage(session_id="esi", montage="standard_1020")
set_reference(session_id="esi", ref_channels="average")
find_events(session_id="esi")
epoch_neuro(session_id="esi", tmin=-0.2, tmax=0.5, reject_uv=None)
```

## 2. RawView — stacked time series

```python
visualize_timeseries(session_id="esi", page_len=10.0, out_path="/out/ts.html")
# -> {"kind": "timeseries", "out_path": "/out/ts.html",
#     "n_channels": 20, "embedded_seconds": 60.0, "bytes": 12034048}
```

Opens as a self-contained page with page navigation (⏮ ◀ ▶ ⏭), a page-length
box, scroll-to-zoom amplitude, and a grid toggle — all client-side JavaScript,
no server needed to view it.

## 3. EvokedView — averaged ERP + topomap

```python
visualize_averaging(session_id="esi", n_frames=20, out_path="/out/av.html")
# -> {"kind": "averaging", "out_path": "/out/av.html",
#     "n_epochs": 29, "n_frames": 20, "bytes": 6283264}
```

A time slider scrubs both the stacked-channel ERP view (with a green cursor)
and the scalp topomap together; a sidebar reports `nave`/peak/`tmin`/`tmax`.

## 4. EsiView — volumetric source imaging

```python
visualize_esi(session_id="esi", n_frames=16, out_path="/out/esi.html")
# -> {"kind": "esi", "method": "dSPM", "out_path": "/out/esi.html",
#     "n_frames": 16, "peak_latency_ms": ..., "bytes": 13365248}
```

This tool computes its own volumetric source estimate internally — you don't
need to have called `apply_inverse` first, unlike the
[ESI pipeline example](source-imaging-esi.md). The output shows three MRI
slices (sagittal/coronal/axial) with an activation overlay and crosshair,
plus an ERP butterfly with a time cursor, below a mask-threshold slider and
a colormap-scale toggle.

## Verifying the output is really self-contained

This is exactly what `testing/verify_viz.py` checks: each file contains
`"Plotly"` and an embedded `id="vizdata"` payload, plus view-specific markers
(e.g. `"pagelen"` for the timeseries view, `"summary"` for averaging,
`"Mask threshold"` for ESI) — confirming the HTML has no external `<script
src=...>` dependency and will render offline.

## Full sequence at a glance

```
load_neuro -> set_montage -> set_reference -> find_events -> epoch_neuro ->
visualize_timeseries -> visualize_averaging -> visualize_esi
```
