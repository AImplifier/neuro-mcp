"""Sensor-level EEG analysis tools (I/O, preprocessing, ICA, epoching, spectral).

Each tool is a thin translation layer: it takes structured params, calls MNE
under the hood, mutates or reads a per-session state object, and returns
JSON-serializable results (with plots as base64 PNG data URIs).
"""

from __future__ import annotations

# Force a headless matplotlib backend before anything imports pyplot: the
# server typically runs without a display.
import matplotlib

matplotlib.use("Agg")

from typing import Any, Literal

import mne
import numpy as np

from .app import mcp
from .session import Session, store
from .utils import FREQ_BANDS, band_from_name, figure_to_data_uri, to_jsonable, trapz


def _ensure_events(session: Session, raw: mne.io.BaseRaw) -> str:
    """Populate session.events from a stim channel or annotations if not already set.

    Returns a short description of where the events came from.
    """
    if session.events is not None and len(session.events) > 0:
        return "cached"
    events = None
    event_id = None
    source = None
    try:
        events = mne.find_events(raw)
        source = "stim_channel"
    except Exception:
        events = None
    if events is None or len(events) == 0:
        events, event_id = mne.events_from_annotations(raw)
        source = "annotations"
    session.events = events
    session.event_id = event_id
    return source or "unknown"


# --------------------------------------------------------------------------- #
# I/O and session management
# --------------------------------------------------------------------------- #
@mcp.tool()
def load_neuro(file_path: str, session_id: str = "default", preload: bool = True) -> dict:
    """Load an EEG recording from disk and return its metadata.

    Supports the formats MNE auto-detects by extension: .fif, .edf, .bdf, .gdf,
    .set (EEGLAB), .vhdr (BrainVision), .cnt, .egi/.mff, and more. Creates (or
    resets) the given session and stores the loaded recording in it.

    Args:
        file_path: Absolute path to the recording file.
        session_id: Session key to store state under; reuse it in later calls.
        preload: Load sample data into memory (required for most processing).
    """
    raw = mne.io.read_raw(file_path, preload=preload)
    session = store.get_or_create(session_id)
    session.raw = raw
    session.source_path = file_path
    # Loading a fresh recording invalidates any derived state.
    session.epochs = None
    session.ica = None
    session.events = None
    session.event_id = None
    session.log(f"Loaded {file_path}")

    info = raw.info
    ch_types = {ch: raw.get_channel_types([ch])[0] for ch in raw.ch_names}
    type_counts: dict[str, int] = {}
    for t in ch_types.values():
        type_counts[t] = type_counts.get(t, 0) + 1

    return to_jsonable(
        {
            "session_id": session_id,
            "source_path": file_path,
            "n_channels": len(raw.ch_names),
            "channels": raw.ch_names,
            "channel_types": type_counts,
            "sfreq": info["sfreq"],
            "duration_sec": raw.times[-1],
            "n_samples": raw.n_times,
            "highpass": info["highpass"],
            "lowpass": info["lowpass"],
            "has_montage": info.get("dig") is not None,
            "bads": info["bads"],
        }
    )


@mcp.tool()
def session_info(session_id: str = "default") -> dict:
    """Return the current state of a session: what's loaded and the step history."""
    return to_jsonable(store.summary(session_id))


@mcp.tool()
def list_sessions() -> dict:
    """List the ids of all active analysis sessions."""
    return {"sessions": store.list_ids()}


@mcp.tool()
def reset_session(session_id: str = "default") -> dict:
    """Discard a session and free its memory."""
    dropped = store.drop(session_id)
    return {"session_id": session_id, "dropped": dropped}


# --------------------------------------------------------------------------- #
# Preprocessing
# --------------------------------------------------------------------------- #
@mcp.tool()
def filter_neuro(
    session_id: str = "default",
    l_freq: float | None = 1.0,
    h_freq: float | None = 40.0,
    notch_freqs: list[float] | None = None,
) -> dict:
    """Apply a band-pass (and optional notch) filter to the loaded recording, in place.

    Args:
        session_id: Session key.
        l_freq: High-pass edge in Hz (None to skip high-pass).
        h_freq: Low-pass edge in Hz (None to skip low-pass).
        notch_freqs: Frequencies to notch out, e.g. [50] or [60, 120] for line noise.
    """
    session, raw = store.require_raw(session_id)
    raw.filter(l_freq=l_freq, h_freq=h_freq)
    if notch_freqs:
        raw.notch_filter(freqs=notch_freqs)
    session.log(f"Filtered l_freq={l_freq} h_freq={h_freq} notch={notch_freqs}")
    return {
        "session_id": session_id,
        "status": "filtered",
        "l_freq": l_freq,
        "h_freq": h_freq,
        "notch_freqs": notch_freqs,
        "highpass": float(raw.info["highpass"]),
        "lowpass": float(raw.info["lowpass"]),
    }


@mcp.tool()
def resample_neuro(session_id: str = "default", sfreq: float = 250.0) -> dict:
    """Resample the recording to a new sampling frequency (Hz), in place."""
    session, raw = store.require_raw(session_id)
    old = float(raw.info["sfreq"])
    raw.resample(sfreq)
    session.log(f"Resampled {old} -> {sfreq} Hz")
    return {"session_id": session_id, "old_sfreq": old, "new_sfreq": float(raw.info["sfreq"])}


@mcp.tool()
def set_montage(session_id: str = "default", montage: str = "standard_1020") -> dict:
    """Assign a standard electrode montage so channels get 3D positions.

    Needed for topographic plots and some source/interpolation steps. Common
    choices: 'standard_1020', 'standard_1005', 'biosemi64', 'GSN-HydroCel-128'.
    """
    session, raw = store.require_raw(session_id)
    raw.set_montage(montage, on_missing="warn")
    session.log(f"Set montage {montage}")
    return {
        "session_id": session_id,
        "montage": montage,
        "has_montage": raw.info.get("dig") is not None,
    }


@mcp.tool()
def set_reference(
    session_id: str = "default",
    ref_channels: Literal["average"] | list[str] = "average",
) -> dict:
    """Re-reference the EEG. Use 'average' for common average reference, or a list
    of channel names (e.g. ['M1', 'M2'] for linked mastoids)."""
    session, raw = store.require_raw(session_id)
    raw.set_eeg_reference(ref_channels=ref_channels)
    session.log(f"Set reference to {ref_channels}")
    return {"session_id": session_id, "ref_channels": ref_channels}


@mcp.tool()
def detect_bad_channels(
    session_id: str = "default", z_threshold: float = 3.0, mark: bool = True
) -> dict:
    """Flag likely-bad channels by robust variance outlier detection.

    Computes each channel's variance, converts to a robust z-score (median /
    MAD), and flags channels beyond ``z_threshold``. This is a fast heuristic,
    not a substitute for RANSAC/autoreject, but works without extra deps.

    Args:
        session_id: Session key.
        z_threshold: Robust z-score cutoff; higher = more permissive.
        mark: If True, add the flagged channels to raw.info['bads'].
    """
    session, raw = store.require_raw(session_id)
    picks = mne.pick_types(raw.info, eeg=True, exclude=[])
    if len(picks) == 0:
        raise ValueError("No EEG channels found to evaluate.")
    data = raw.get_data(picks=picks)
    variances = np.var(data, axis=1)
    log_var = np.log(variances + 1e-30)
    median = np.median(log_var)
    mad = np.median(np.abs(log_var - median)) + 1e-30
    robust_z = 0.6745 * (log_var - median) / mad
    names = [raw.ch_names[i] for i in picks]
    flagged = [
        {"channel": names[i], "robust_z": float(robust_z[i])}
        for i in range(len(names))
        if abs(robust_z[i]) > z_threshold
    ]
    flagged_names = [f["channel"] for f in flagged]
    if mark and flagged_names:
        raw.info["bads"] = sorted(set(raw.info["bads"]) | set(flagged_names))
    session.log(f"Bad-channel scan flagged {flagged_names} (marked={mark})")
    return to_jsonable(
        {
            "session_id": session_id,
            "z_threshold": z_threshold,
            "flagged": flagged,
            "marked_as_bad": mark,
            "current_bads": raw.info["bads"],
        }
    )


@mcp.tool()
def interpolate_bads(session_id: str = "default") -> dict:
    """Interpolate channels currently marked bad using neighboring electrodes.
    Requires a montage (call set_montage first)."""
    session, raw = store.require_raw(session_id)
    bads = list(raw.info["bads"])
    if not bads:
        return {"session_id": session_id, "status": "no bad channels to interpolate"}
    raw.interpolate_bads(reset_bads=True)
    session.log(f"Interpolated {bads}")
    return {"session_id": session_id, "interpolated": bads}


# --------------------------------------------------------------------------- #
# ICA for artifact removal
# --------------------------------------------------------------------------- #
@mcp.tool()
def run_ica(
    session_id: str = "default",
    n_components: float | int | None = 20,
    method: str = "fastica",
    random_state: int = 97,
) -> dict:
    """Fit ICA on the loaded recording for artifact inspection/removal.

    Fitting on data high-passed at ~1 Hz is recommended. Returns per-component
    summaries; use apply_ica to zero out the components you identify as
    artifacts (blinks, heartbeat, muscle).

    Args:
        n_components: Number of components, or a float in (0,1] as explained variance.
        method: 'fastica', 'infomax', or 'picard'.
        random_state: Seed for reproducibility.
    """
    session, raw = store.require_raw(session_id)
    ica = mne.preprocessing.ICA(
        n_components=n_components, method=method, random_state=random_state
    )
    ica.fit(raw)
    session.ica = ica
    session.log(f"Fit ICA n_components={n_components} method={method}")

    summaries = []
    try:
        var_ratio = ica.get_explained_variance_ratio(raw)
    except Exception:
        var_ratio = None
    for i in range(ica.n_components_):
        summaries.append({"component": i})
    return to_jsonable(
        {
            "session_id": session_id,
            "n_components": int(ica.n_components_),
            "method": method,
            "explained_variance_ratio": var_ratio,
            "components": summaries,
            "note": (
                "Inspect components with plot_ica_components, then remove "
                "artifacts via apply_ica(exclude=[...])."
            ),
        }
    )


@mcp.tool()
def detect_artifact_components(
    session_id: str = "default",
    eog_ch: str | None = None,
    ecg_ch: str | None = None,
) -> dict:
    """Automatically score ICA components against EOG/ECG channels to find
    likely blink/heartbeat artifacts. Requires run_ica first and, ideally,
    EOG/ECG channels present in the data.

    Args:
        eog_ch: Name of an EOG channel (auto-detected if None and any exist).
        ecg_ch: Name of an ECG channel (auto-detected if None and any exist).
    """
    session = store.get(session_id)
    if session.ica is None:
        raise ValueError("No ICA fitted. Call run_ica first.")
    _, raw = store.require_raw(session_id)
    ica = session.ica
    found: dict[str, Any] = {"eog": [], "ecg": []}
    try:
        eog_idx, _ = ica.find_bads_eog(raw, ch_name=eog_ch)
        found["eog"] = eog_idx
    except Exception as exc:
        found["eog_error"] = str(exc)
    try:
        ecg_idx, _ = ica.find_bads_ecg(raw, ch_name=ecg_ch)
        found["ecg"] = ecg_idx
    except Exception as exc:
        found["ecg_error"] = str(exc)
    suggested = sorted(set(found.get("eog", []) or []) | set(found.get("ecg", []) or []))
    session.log(f"Artifact component scan suggested {suggested}")
    return to_jsonable(
        {"session_id": session_id, "suggested_exclude": suggested, "detail": found}
    )


@mcp.tool()
def apply_ica(session_id: str = "default", exclude: list[int] | None = None) -> dict:
    """Remove the listed ICA components from the recording, in place.
    Requires run_ica first."""
    session = store.get(session_id)
    if session.ica is None:
        raise ValueError("No ICA fitted. Call run_ica first.")
    _, raw = store.require_raw(session_id)
    exclude = exclude or []
    session.ica.exclude = exclude
    session.ica.apply(raw)
    session.log(f"Applied ICA, removed components {exclude}")
    return {"session_id": session_id, "removed_components": exclude}


# --------------------------------------------------------------------------- #
# Events and epoching
# --------------------------------------------------------------------------- #
@mcp.tool()
def find_events(session_id: str = "default", stim_channel: str | None = None) -> dict:
    """Extract events from a stimulus/trigger channel or from annotations.

    Tries stim-channel events first, then falls back to annotation-derived
    events. Stores the result for epoch_neuro to use.
    """
    session, raw = store.require_raw(session_id)
    # Reset so the helper re-detects (respecting an explicit stim_channel).
    session.events = None
    if stim_channel is not None:
        try:
            session.events = mne.find_events(raw, stim_channel=stim_channel)
            session.event_id = None
            source = "stim_channel"
        except Exception:
            session.events = None
    source = _ensure_events(session, raw) if session.events is None else "stim_channel"
    events = session.events
    event_id = session.event_id
    session.log(f"Found {len(events)} events from {source}")

    codes, counts = np.unique(events[:, 2], return_counts=True) if len(events) else ([], [])
    return to_jsonable(
        {
            "session_id": session_id,
            "source": source,
            "n_events": len(events),
            "event_id": event_id,
            "code_counts": {int(c): int(n) for c, n in zip(codes, counts)},
        }
    )


@mcp.tool()
def epoch_neuro(
    session_id: str = "default",
    tmin: float = -0.2,
    tmax: float = 0.5,
    baseline_start: float | None = None,
    baseline_end: float | None = 0.0,
    reject_uv: float | None = 150.0,
) -> dict:
    """Segment the recording into epochs around events.

    Call find_events first (or the tool will attempt it). Baseline correction
    uses (baseline_start, baseline_end); pass baseline_start=None for "from the
    start of the epoch". reject_uv drops epochs whose EEG peak-to-peak exceeds
    that many microvolts (None to disable).

    Args:
        tmin: Epoch start relative to event onset, in seconds.
        tmax: Epoch end relative to event onset, in seconds.
        baseline_start: Baseline window start (s), or None for epoch start.
        baseline_end: Baseline window end (s), or None for event onset.
        reject_uv: Peak-to-peak EEG rejection threshold in microvolts.
    """
    session, raw = store.require_raw(session_id)
    if session.events is None or len(session.events) == 0:
        _ensure_events(session, raw)
    if session.events is None or len(session.events) == 0:
        raise ValueError("No events available to epoch around. Check find_events output.")

    reject = {"eeg": reject_uv * 1e-6} if reject_uv else None
    baseline = (baseline_start, baseline_end)
    epochs = mne.Epochs(
        raw,
        events=session.events,
        event_id=session.event_id,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        reject=reject,
        preload=True,
    )
    session.epochs = epochs
    session.log(f"Epoched tmin={tmin} tmax={tmax} -> {len(epochs)} epochs")
    return to_jsonable(
        {
            "session_id": session_id,
            "n_epochs": len(epochs),
            "n_dropped": len(epochs.drop_log) - len(epochs),
            "tmin": tmin,
            "tmax": tmax,
            "baseline": baseline,
            "event_id": epochs.event_id,
        }
    )


# --------------------------------------------------------------------------- #
# Spectral / ERP / time-frequency analysis
# --------------------------------------------------------------------------- #
@mcp.tool()
def compute_psd(
    session_id: str = "default",
    fmin: float = 1.0,
    fmax: float = 45.0,
    use_epochs: bool = False,
) -> dict:
    """Compute the power spectral density and summarize band power.

    Returns absolute and relative power for each canonical band (delta, theta,
    alpha, beta, gamma), averaged across channels, plus per-channel band power.

    Args:
        fmin, fmax: Frequency range for the PSD, in Hz.
        use_epochs: Compute on epochs (averaged) instead of continuous raw.
    """
    session = store.get(session_id)
    if use_epochs:
        _, obj = store.require_epochs(session_id)
    else:
        _, obj = store.require_raw(session_id)
    spectrum = obj.compute_psd(fmin=fmin, fmax=fmax)
    # exclude=() keeps every channel so the data rows line up with ch_names
    # (get_data drops bads by default, while ch_names retains them).
    psds, freqs = spectrum.get_data(return_freqs=True, exclude=())
    # For epochs, average over the epoch axis first.
    if psds.ndim == 3:
        psds = psds.mean(axis=0)  # -> (n_channels, n_freqs)
    ch_names = spectrum.ch_names

    total_power = trapz(psds, freqs, axis=1)  # (n_channels,)
    bands: dict[str, Any] = {}
    per_channel_bands: dict[str, dict[str, float]] = {ch: {} for ch in ch_names}
    for name, (lo, hi) in FREQ_BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        if not mask.any():
            continue
        band_power = trapz(psds[:, mask], freqs[mask], axis=1)  # (n_channels,)
        rel = band_power / (total_power + 1e-30)
        bands[name] = {
            "abs_power_mean": float(np.mean(band_power)),
            "rel_power_mean": float(np.mean(rel)),
        }
        for i, ch in enumerate(ch_names):
            per_channel_bands[ch][name] = float(band_power[i])

    session.log(f"Computed PSD {fmin}-{fmax} Hz (epochs={use_epochs})")
    return to_jsonable(
        {
            "session_id": session_id,
            "fmin": fmin,
            "fmax": fmax,
            "n_channels": len(ch_names),
            "band_power": bands,
            "per_channel_band_power": per_channel_bands,
        }
    )


@mcp.tool()
def compute_erp(
    session_id: str = "default",
    condition: str | None = None,
    pick_channel: str | None = None,
) -> dict:
    """Average epochs into an ERP and report peak latency/amplitude.

    Args:
        condition: Event-id name to average (None = all epochs together).
        pick_channel: Channel to report peak for (None = the global-field-power peak).
    """
    session, epochs = store.require_epochs(session_id)
    selected = epochs[condition] if condition else epochs
    if len(selected) == 0:
        raise ValueError(f"No epochs for condition '{condition}'.")
    evoked = selected.average()

    result: dict[str, Any] = {
        "session_id": session_id,
        "condition": condition,
        "n_epochs_averaged": len(selected),
        "times_ms": [float(t * 1000) for t in (evoked.times[0], evoked.times[-1])],
    }
    if pick_channel:
        ch_name, latency, amplitude = evoked.copy().pick([pick_channel]).get_peak(
            return_amplitude=True
        )
    else:
        ch_name, latency, amplitude = evoked.get_peak(return_amplitude=True)
    result["peak"] = {
        "channel": ch_name,
        "latency_ms": float(latency * 1000),
        "amplitude_uv": float(amplitude * 1e6),
    }
    session.log(f"Computed ERP condition={condition} peak={ch_name}")
    return to_jsonable(result)


@mcp.tool()
def time_frequency(
    session_id: str = "default",
    fmin: float = 4.0,
    fmax: float = 40.0,
    n_freqs: int = 20,
    pick_channel: str | None = None,
    condition: str | None = None,
) -> dict:
    """Morlet-wavelet time-frequency decomposition of epochs.

    Returns the induced power averaged over epochs, summarized per frequency
    band and time. Requires epoch_neuro first.

    Args:
        fmin, fmax: Frequency range in Hz.
        n_freqs: Number of log-spaced frequencies.
        pick_channel: Restrict to one channel (recommended for a compact summary).
        condition: Event-id name to restrict to.
    """
    session, epochs = store.require_epochs(session_id)
    selected = epochs[condition] if condition else epochs
    if pick_channel:
        selected = selected.copy().pick([pick_channel])
    freqs = np.logspace(np.log10(fmin), np.log10(fmax), n_freqs)
    # A Morlet wavelet spans ~5*n_cycles/(pi*freq) seconds; cap n_cycles so the
    # lowest-frequency wavelet still fits inside the epoch (matters for short
    # epochs), keeping at least 1 cycle.
    sfreq = selected.info["sfreq"]
    epoch_dur = selected.times[-1] - selected.times[0]
    max_cycles = np.maximum(freqs * epoch_dur * np.pi / 5.0 * 0.9, 1.0)
    n_cycles = np.minimum(freqs / 2.0, max_cycles)
    power = selected.compute_tfr(
        method="morlet", freqs=freqs, n_cycles=n_cycles, average=True, return_itc=False
    )
    data = power.data  # (n_channels, n_freqs, n_times)
    mean_over_ch = data.mean(axis=0)  # (n_freqs, n_times)

    band_time_course = {}
    for name, (lo, hi) in FREQ_BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        if mask.any():
            band_time_course[name] = float(mean_over_ch[mask].mean())
    session.log(f"Time-frequency {fmin}-{fmax} Hz channel={pick_channel}")
    return to_jsonable(
        {
            "session_id": session_id,
            "freqs_hz": freqs,
            "times_s": [float(power.times[0]), float(power.times[-1])],
            "channels": power.ch_names,
            "mean_band_power": band_time_course,
        }
    )


# --------------------------------------------------------------------------- #
# Visualization
# --------------------------------------------------------------------------- #
@mcp.tool()
def plot_raw(
    session_id: str = "default",
    start: float = 0.0,
    duration: float = 10.0,
    n_channels: int = 20,
) -> dict:
    """Render a segment of the raw traces as a PNG image (base64 data URI)."""
    session, raw = store.require_raw(session_id)
    fig = raw.plot(
        start=start, duration=duration, n_channels=n_channels, show=False, show_scrollbars=False
    )
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "raw_traces"}


@mcp.tool()
def plot_psd(session_id: str = "default", fmin: float = 1.0, fmax: float = 45.0) -> dict:
    """Render the power spectral density plot as a PNG image (base64 data URI)."""
    session, raw = store.require_raw(session_id)
    spectrum = raw.compute_psd(fmin=fmin, fmax=fmax)
    fig = spectrum.plot(show=False)
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "psd"}


@mcp.tool()
def plot_topomap(session_id: str = "default", band: str = "alpha") -> dict:
    """Render a scalp topographic map of band power (base64 PNG data URI).
    Requires a montage (call set_montage first)."""
    session, raw = store.require_raw(session_id)
    lo, hi = band_from_name(band)
    spectrum = raw.compute_psd(fmin=lo, fmax=hi)
    fig = spectrum.plot_topomap(bands={f"{band} ({lo}-{hi} Hz)": (lo, hi)}, show=False)
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "topomap", "band": band}


@mcp.tool()
def plot_erp(
    session_id: str = "default",
    condition: str | None = None,
    pick_channel: str | None = None,
) -> dict:
    """Render the ERP (evoked average) as a PNG image (base64 data URI)."""
    session, epochs = store.require_epochs(session_id)
    selected = epochs[condition] if condition else epochs
    evoked = selected.average()
    if pick_channel:
        evoked = evoked.copy().pick([pick_channel])
    fig = evoked.plot(show=False, spatial_colors=True)
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "erp", "condition": condition}


@mcp.tool()
def plot_ica_components(session_id: str = "default") -> dict:
    """Render ICA component scalp topographies as a PNG image (base64 data URI).
    Requires run_ica and a montage."""
    session = store.get(session_id)
    if session.ica is None:
        raise ValueError("No ICA fitted. Call run_ica first.")
    figs = session.ica.plot_components(show=False)
    fig = figs[0] if isinstance(figs, list) else figs
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "ica_components"}


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
@mcp.tool()
def export_data(
    session_id: str = "default", out_path: str = "processed_raw.fif", what: str = "raw"
) -> dict:
    """Save processed data to disk.

    Args:
        out_path: Destination path. For raw use a *-raw.fif or .fif name; for
            epochs use *-epo.fif.
        what: 'raw' or 'epochs'.
    """
    session = store.get(session_id)
    if what == "raw":
        if session.raw is None:
            raise ValueError("No raw data to export.")
        session.raw.save(out_path, overwrite=True)
    elif what == "epochs":
        if session.epochs is None:
            raise ValueError("No epochs to export.")
        session.epochs.save(out_path, overwrite=True)
    else:
        raise ValueError("what must be 'raw' or 'epochs'.")
    session.log(f"Exported {what} to {out_path}")
    return {"session_id": session_id, "saved": out_path, "what": what}
