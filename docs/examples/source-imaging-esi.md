# Example 3: Source Imaging (ESI) Pipeline

Localizing cortical sources from scalp EEG using MNE's fsaverage template
head — the sequence `testing/full_verify.py`'s `esi` section exercises in
full, including both inverse methods.

## 1. Prepare a session (through epoching)

Source imaging needs a montage, a reference, and epochs — the same prep as
the [processing pipeline](research-preprocessing-spectral.md), condensed:

```python
load_neuro(file_path="/data/synthetic-raw.fif", session_id="esi")
set_montage(session_id="esi", montage="standard_1020")
set_reference(session_id="esi", ref_channels="average")
find_events(session_id="esi")
epoch_neuro(session_id="esi", tmin=-0.2, tmax=0.5, reject_uv=None)
```

## 2. Build the head model and forward solution

```python
fetch_template_head(session_id="esi", spacing="ico5")
# -> {"subject": "fsaverage", "spacing": "ico5", "n_sources": 20484,
#     "note": "Template head model ready. Next: compute_forward."}
```

The first call downloads the fsaverage dataset; it's cached on disk for every
call after that.

```python
compute_forward(session_id="esi")
# -> {"n_sources": 20484, "n_channels": 20,
#     "note": "Leadfield ready. Next: compute_noise_covariance."}
```

## 3. Noise covariance and the inverse operator

```python
compute_noise_covariance(session_id="esi", method="empirical")
# -> {"method": "empirical", "rank": 20, ...}

make_inverse_operator(session_id="esi")
# -> {"loose": 0.2, "depth": 0.8, "note": "Inverse operator ready. Next: apply_inverse."}
```

## 4. Localize sources

```python
apply_inverse(session_id="esi", method="dSPM", snr=3.0)
# -> {"n_sources": 20484, "peak": {
#       "vertex": ..., "hemisphere": "lh", "latency_ms": 72.0, "amplitude": 8.08
#    }, ...}
```

`full_verify.py`'s evaluation pass confirms the peak amplitude is finite and
positive — a sanity check that the inverse actually localized something,
not just that the call didn't error.

Alternative — a beamformer instead of minimum-norm:

```python
apply_lcmv_beamformer(session_id="esi", reg=0.05)
# -> {"method": "LCMV", "peak": {"hemisphere": "lh", "latency_ms": ..., ...}}
```

## 5. Map onto named anatomical regions

```python
extract_label_timecourses(session_id="esi", top_n=5)
# -> {"n_regions": 68, "top_regions": [
#       {"region": "isthmuscingulate-rh", "hemisphere": "rh",
#        "peak_amplitude": ..., "peak_latency_ms": ...},
#       ...
#    ]}
```

Regions come from the Desikan-Killiany atlas (`parcellation="aparc"`, 68
named cortical regions) — human-readable ROI names, not raw vertex indices.

## 6. Visualize

```python
plot_source_timecourses(session_id="esi", top_n=5)
# -> {"image": "data:image/png;base64,...", "kind": "source_timecourses"}

plot_source_brain(session_id="esi")
# -> {"image": None, "note": "3D rendering backend not available in this
#      environment. Use plot_source_timecourses for a 2D ROI summary."}
#    (or a real screenshot PNG if `pip install neuro-mcp[viz3d]` is installed
#     with a working offscreen renderer)
```

`plot_source_timecourses` works everywhere (pure matplotlib, headless);
`plot_source_brain` degrades gracefully instead of failing when no 3D
backend is available — check for `image: null` and fall back rather than
treating it as an error.

## Full sequence at a glance

```
load_neuro -> set_montage -> set_reference -> find_events -> epoch_neuro ->
fetch_template_head -> compute_forward -> compute_noise_covariance ->
make_inverse_operator -> apply_inverse (or apply_lcmv_beamformer) ->
extract_label_timecourses -> plot_source_timecourses / plot_source_brain
```

For an interactive, self-contained-HTML version of this same source estimate
(volumetric slices + ERP butterfly, no separate `apply_inverse` call needed —
it computes its own), see
[Interactive Visualization Generation](interactive-visualization.md)'s
`visualize_esi`.
