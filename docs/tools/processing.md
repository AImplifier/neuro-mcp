# Processing (MNE)

24 tools in `neuro_mcp/tools_core.py`. All operate on an in-memory
`Session` keyed by `session_id` — call `load_neuro` first, then chain the
rest against the same key.

## Session management

### `load_neuro(file_path, session_id="default", preload=True)`
Load an EEG recording (`.fif`, `.edf`, `.bdf`, `.gdf`, `.set`, `.vhdr`,
`.cnt`, `.egi`/`.mff`, and anything else MNE auto-detects by extension).
Creates or resets the session and clears any derived state (epochs, ICA,
events). Returns channel count/types, sampling rate, duration, and current
`bads`.

### `session_info(session_id="default")`
Current state of a session: what's loaded and the step history.

### `list_sessions()`
IDs of all active sessions.

### `reset_session(session_id="default")`
Discard a session and free its memory.

## Preprocessing

### `filter_neuro(session_id, l_freq=1.0, h_freq=40.0, notch_freqs=None)`
Band-pass filter in place, plus an optional notch (e.g. `[50.0]` for EU line
noise, `[60.0]` for US). `l_freq`/`h_freq` may be `None` to skip that edge.

### `resample_neuro(session_id, sfreq=250.0)`
Resample to a new rate, in place.

### `set_montage(session_id, montage="standard_1020")`
Assign a standard electrode montage (3D positions), needed for topomaps and
source imaging. Common values: `standard_1020`, `standard_1005`,
`biosemi64`, `GSN-HydroCel-128`.

### `set_reference(session_id, ref_channels="average")`
Re-reference — `"average"` for common average reference, or a list of
channel names (e.g. `["M1", "M2"]` for linked mastoids).

### `detect_bad_channels(session_id, z_threshold=3.0, mark=True)`
Fast robust-variance-outlier heuristic (median/MAD z-score on
log-variance) — not a substitute for RANSAC/autoreject, but dependency-free.
`mark=True` adds flagged channels to `raw.info["bads"]`.

### `interpolate_bads(session_id)`
Interpolate currently-bad channels from neighbors. Requires a montage.

## ICA / artifact removal

### `run_ica(session_id, n_components=20, method="fastica", random_state=97)`
Fit ICA (`fastica`, `infomax`, or `picard`). `n_components` can be an int or
a float in (0, 1] for explained-variance target. Inspect with
`plot_ica_components`, then remove artifacts via `apply_ica`.

### `detect_artifact_components(session_id, eog_ch=None, ecg_ch=None)`
Score ICA components against EOG/ECG channels to suggest likely
blink/heartbeat components. Requires `run_ica` first.

### `apply_ica(session_id, exclude=None)`
Zero out the listed component indices, in place.

## Events and epoching

### `find_events(session_id, stim_channel=None)`
Extract events from a stim channel (tried first) or annotations (fallback).
Stores the result for `epoch_neuro`.

### `epoch_neuro(session_id, tmin=-0.2, tmax=0.5, baseline_start=None, baseline_end=0.0, reject_uv=150.0)`
Segment into epochs around events. Calls `find_events` implicitly if none are
cached. `reject_uv` drops epochs whose EEG peak-to-peak exceeds that many
microvolts (`None` to disable).

## Spectral / ERP / time-frequency

### `compute_psd(session_id, fmin=1.0, fmax=45.0, use_epochs=False)`
Power spectral density, summarized into `delta`/`theta`/`alpha`/`beta`/`gamma`
band power (absolute + relative, mean across channels and per-channel).
`use_epochs=True` computes on the averaged epochs instead of continuous raw —
useful for feature extraction (see
[Research Preprocessing & Spectral Pipeline](../examples/research-preprocessing-spectral.md)).

### `compute_erp(session_id, condition=None, pick_channel=None)`
Average epochs into an ERP; reports peak channel, latency (ms), and amplitude
(µV). `pick_channel=None` uses the global-field-power peak.

### `time_frequency(session_id, fmin=4.0, fmax=40.0, n_freqs=20, pick_channel=None, condition=None)`
Morlet-wavelet time-frequency decomposition of epochs, summarized as mean
band power per canonical band. Requires `epoch_neuro` first.

## Plots (PNG, base64 data URI)

All return `{"session_id", "image": "data:image/png;base64,...", "kind": ...}`
— an agent can hand the `image` value directly to a UI that renders data
URIs.

- `plot_raw(session_id, start=0.0, duration=10.0, n_channels=20)`
- `plot_psd(session_id, fmin=1.0, fmax=45.0)`
- `plot_topomap(session_id, band="alpha")` — requires a montage
- `plot_erp(session_id, condition=None, pick_channel=None)` — requires epochs
- `plot_ica_components(session_id)` — requires `run_ica`

## Export

### `export_data(session_id, out_path="processed_raw.fif", what="raw")`
Save the session's `raw` or `epochs` to disk (`what="raw"` or `"epochs"`).
