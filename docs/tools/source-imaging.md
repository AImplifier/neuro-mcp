# Source Imaging (ESI)

9 tools in `neuro_mcp/tools_source.py`. Because subject-specific MRIs are
usually unavailable, this uses MNE's **fsaverage template head model** — a
standard, well-validated approach for EEG source imaging without individual
anatomy. All state threads through the same `session_id` as the processing
tools; run this pipeline after `epoch_neuro`.

```
fetch_template_head -> compute_forward -> compute_noise_covariance ->
make_inverse_operator -> apply_inverse (or apply_lcmv_beamformer) ->
extract_label_timecourses -> plot_source_timecourses / plot_source_brain
```

### `fetch_template_head(session_id, spacing="ico5")`
Download and register the fsaverage template (BEM, source space, MRI-head
transform). The first call downloads the fsaverage dataset (cached
afterwards — later calls are fast). `spacing`: `"ico5"` (~20k sources,
standard) or `"oct6"`. Requires a recording already loaded.

### `compute_forward(session_id, mindist=5.0)`
Leadfield mapping cortical sources to sensors. Requires a montage
(`set_montage`) and a template head (`fetch_template_head`). `mindist` is the
minimum source distance (mm) from the inner skull surface.

### `compute_noise_covariance(session_id, method="empirical", tmax=0.0)`
Noise covariance from epoch baselines (pre-stimulus interval up to `tmax`).
Requires `epoch_neuro`. `method`: `"empirical"`, `"shrunk"`, or `"auto"`.

### `make_inverse_operator(session_id, loose=0.2, depth=0.8)`
Assemble the inverse operator from the forward solution + noise covariance.
Requires both. `loose` is the loose-orientation constraint (0.2 typical for
surface source spaces); `depth` counters bias toward superficial sources
(0.8 typical).

### `apply_inverse(session_id, method="dSPM", snr=3.0, condition=None, save_stc=None)`
Distributed source estimate for the (averaged) ERP. `method`: `"MNE"`,
`"dSPM"`, `"sLORETA"`, or `"eLORETA"`. `snr` sets the regularization
(`lambda2 = 1/snr^2`). Returns the peak vertex, hemisphere, latency, and
amplitude. `save_stc` optionally writes the estimate to a `.stc`/`.h5` path
stem.

### `apply_lcmv_beamformer(session_id, condition=None, reg=0.05, save_stc=None)`
LCMV beamformer alternative to minimum-norm. Uses the epoch data covariance
for the spatial filter (`reg` is diagonal loading) and the noise covariance
for whitening. Requires `compute_forward` and `compute_noise_covariance`.

### `extract_label_timecourses(session_id, parcellation="aparc", mode="mean_flip", top_n=10)`
ROI time courses from an anatomical parcellation (`"aparc"` = Desikan-Killiany,
68 regions, or `"aparc.a2009s"`), ranked by peak absolute amplitude. Requires
a source estimate (`apply_inverse` or `apply_lcmv_beamformer`).

### `plot_source_timecourses(session_id, parcellation="aparc", top_n=5)`
2D matplotlib summary (PNG data URI) of the strongest ROI time courses — works
headlessly, no 3D backend needed.

### `plot_source_brain(session_id, time_ms=None, hemi="both")`
3D cortical surface render at a given (or peak) time. Requires an offscreen
3D backend (`pip install neuro-mcp[viz3d]` + a working PyVista/Qt renderer);
if unavailable it returns `{"image": None, "note": "..."}` instead of
failing — use `plot_source_timecourses` for a dependency-free 2D summary.

See [Source Imaging (ESI) Pipeline](../examples/source-imaging-esi.md) for a
full worked example with real output shapes.
