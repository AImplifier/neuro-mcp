# Visualization

3 tools in `neuro_mcp/tools_viz_neuroii.py`. These port NEUROII's main views
into **self-contained interactive HTML** files (Plotly, embedded — no server,
works offline). Each tool writes the file to disk and returns its path;
interaction runs entirely client-side in the browser.

```json
visualize_averaging(session_id="s") -> {"out_path": ".../averaging_s.html", "kind": "averaging", ...}
```

### `visualize_timeseries(session_id, page_len=10.0, n_channels=30, max_seconds=60.0, out_path=None)`
**RawView** — stacked EEG channels on one amplitude scale, with NEUROII's
controls: page navigation (⏮ ◀ ▶ ⏭), a page-length box, scroll-to-zoom
amplitude, and a grid toggle. Requires a loaded recording (`load_neuro` /
`import_recording`). `max_seconds` bounds how much of the recording is
embedded in the HTML.

### `visualize_averaging(session_id, condition=None, n_frames=40, out_path=None)`
**EvokedView** — the averaged ERP as stacked channels with a green time
cursor (left pane) plus a scalp topomap at the cursor time (right pane). A
time slider scrubs both; a sidebar reports `nave`/peak/`tmin`/`tmax`.
Requires epochs (`epoch_neuro`) with a montage (`set_montage`).

### `visualize_esi(session_id, method="dSPM", n_frames=40, out_path=None)`
**EsiView** — a volumetric source estimate (fsaverage template) rendered to
canvas on three orthogonal MRI slices (sagittal/coronal/axial) with a
black-blue-white-red activation overlay, crosshair, and L/R + MNI-coordinate
labels; cut planes recentre on each frame's peak. Below, an ERP butterfly
plot carries a red current-time cursor and a blue half-peak marker. Controls:
time slider, global/frame colormap-scale toggle, mask-threshold slider. A
faithful port of NEUROII's view — computes its own volumetric source estimate
internally (independent of any prior `apply_inverse` call); needs epochs
(`epoch_neuro` + `set_montage`).

## Why standalone HTML

Every output is a single `.html` file with Plotly embedded inline — no
running server, no network access needed to view it, safe to email or drop
in a shared folder. An agent can generate one, hand the `out_path` to the
user, and the visualization keeps working indefinitely.

See [Interactive Visualization Generation](../examples/interactive-visualization.md)
for a full worked example including the self-contained-HTML verification
pattern used in `testing/verify_viz.py`.
