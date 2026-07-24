# Example 2: Research Preprocessing & Spectral Pipeline

The full sensor-level MNE pipeline from a raw file to decodable spectral
features — the sequence `testing/full_verify.py`'s `preprocess`/`ica`/
`epoch`/`spectral` sections exercise, and the "STATEFUL PIPELINE" /
"FEATURE EXTRACTION" sections of `testing/persona_bci_researcher.py` walk
through from a researcher's perspective.

## 1. Load and clean

```python
load_neuro(file_path="/data/synthetic-raw.fif", session_id="proc")
# -> {"n_channels": 21, "duration_sec": 60.0, "sfreq": 250.0, ...}

filter_neuro(session_id="proc", l_freq=1.0, h_freq=40.0, notch_freqs=[50.0])
# -> {"status": "filtered", "highpass": 1.0, "lowpass": 40.0, ...}

set_montage(session_id="proc", montage="standard_1020")
# -> {"has_montage": true, ...}

resample_neuro(session_id="proc", sfreq=200.0)
# -> {"old_sfreq": 250.0, "new_sfreq": 200.0}

set_reference(session_id="proc", ref_channels="average")
# -> {"ref_channels": "average"}

detect_bad_channels(session_id="proc", z_threshold=3.0)
# -> {"flagged": [...8 channels in the synthetic-data run...], "marked_as_bad": true, ...}
```

## 2. Remove artifacts with ICA

```python
run_ica(session_id="proc", n_components=12)
# -> {"n_components": 12, "note": "Inspect with plot_ica_components, then apply_ica(exclude=[...])"}

detect_artifact_components(session_id="proc")
# -> {"suggested_exclude": [], "detail": {"eog": [], "ecg": []}}
# (empty here because the synthetic recording has no real EOG/ECG artifacts)

apply_ica(session_id="proc", exclude=[])
# -> {"removed_components": []}
```

Pass the indices `detect_artifact_components` (or your own visual review via
`plot_ica_components`) flags into `apply_ica`'s `exclude` list.

## 3. Epoch around events

```python
find_events(session_id="proc")
# -> {"source": "stim_channel", "n_events": 29, "code_counts": {"1": 29}}

epoch_neuro(session_id="proc", tmin=-0.2, tmax=0.5, reject_uv=None)
# -> {"n_epochs": 29, "n_dropped": 0, "tmin": -0.2, "tmax": 0.5, ...}
```

## 4. Extract spectral features

```python
compute_psd(session_id="proc", fmin=1.0, fmax=45.0)
# -> {"band_power": {"alpha": {"abs_power_mean": ..., "rel_power_mean": 0.434}, ...},
#     "per_channel_band_power": {"Fp1": {"delta": ..., "theta": ..., "alpha": ..., ...}, ...}}
```

The `testing/full_verify.py` evaluation pass confirms this isn't just
well-formed — it's *correct*: the synthetic recording has an injected 10 Hz
rhythm, and `alpha` (8–13 Hz) comes back as the dominant relative-power band.

```python
compute_erp(session_id="proc")
# -> {"peak": {"channel": "O1", "latency_ms": 220.0, "amplitude_uv": ...},
#     "n_epochs_averaged": 29, ...}

time_frequency(session_id="proc", fmin=4.0, fmax=40.0, n_freqs=10)
# -> {"mean_band_power": {"theta": ..., "alpha": ..., "beta": ..., "gamma": ...}, ...}
```

The ERP peak latency (220 ms here) falls within the epoch window, and the
alpha-band time-frequency power is finite and positive — both asserted by
`full_verify.py`'s numerical `evaluate()` pass, not just its happy-path
checks.

## 5. Feature vectors for a classifier

For a decoding pipeline rather than a summary report, compute PSD **per
epoch** instead of on continuous data:

```python
compute_psd(session_id="bci", fmin=1.0, fmax=45.0, use_epochs=True)
# -> per_channel_band_power: {n_channels} channels x 5 bands = a ready feature vector
```

`persona_bci_researcher.py` notes this is the fastest raw-file-to-features
path (~6 calls total: import → filter → montage → reference → events →
epoch → psd) but that it returns *summary scalars* (band-power means, one
ERP peak) rather than a raw per-trial tensor an agent could feed directly to
a classifier — there's no tool yet to export the epoch tensor as an array.

## 6. Export and clean up

```python
export_data(session_id="proc", out_path="/data/out-raw.fif", what="raw")
export_data(session_id="proc", out_path="/data/out-epo.fif", what="epochs")
reset_session(session_id="proc")
# -> {"session_id": "proc", "dropped": true}
```

## Full sequence at a glance

```
load_neuro -> filter_neuro -> set_montage -> resample_neuro -> set_reference ->
detect_bad_channels -> run_ica -> detect_artifact_components -> apply_ica ->
find_events -> epoch_neuro -> compute_psd -> compute_erp -> time_frequency ->
export_data -> reset_session
```
