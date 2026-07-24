"""EEG source imaging (ESI) tools: the full source-localization pipeline.

Because subject MRIs are usually unavailable, this uses MNE's fsaverage
template head model (a standard, well-validated approach for EEG source
imaging). Pipeline:

    fetch_template_head        # download + register fsaverage BEM/source space
    compute_forward            # leadfield from sensor montage -> cortical sources
    compute_noise_covariance   # noise statistics (from epoch baselines)
    make_inverse_operator      # MNE / dSPM / sLORETA / eLORETA operator
    apply_inverse              # distributed source estimate for an ERP
    apply_lcmv_beamformer      # (alternative) LCMV beamformer source estimate
    extract_label_timecourses  # ROI time courses over an atlas parcellation
    plot_source_timecourses    # matplotlib plot of ROI activity

All state is threaded through the same session objects as the sensor-level tools.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")

import mne
import numpy as np

from .app import mcp
from .session import store
from .utils import figure_to_data_uri, to_jsonable

# Map a target SNR to the regularization parameter lambda^2.
def _lambda2(snr: float) -> float:
    return 1.0 / max(snr, 1e-3) ** 2


def _evoked_for_inverse(session, condition: str | None):
    """Build an average-referenced Evoked from the session's epochs.

    Minimum-norm inverse modeling assumes an EEG average reference; we add it as
    a projection so the forward/inverse are consistent.
    """
    if session.epochs is None:
        raise ValueError("No epochs available. Run epoch_neuro first.")
    epochs = session.epochs[condition] if condition else session.epochs
    evoked = epochs.average()
    if not any(p["desc"].startswith("Average EEG") for p in evoked.info["projs"]):
        evoked.set_eeg_reference("average", projection=True)
        evoked.apply_proj()
    return evoked


@mcp.tool()
def fetch_template_head(session_id: str = "default", spacing: str = "ico5") -> dict:
    """Download and register the fsaverage template head model for source imaging.

    Sets up the template subject (BEM, source space, and MRI-head transform) so a
    forward model can be built without a subject-specific MRI. The first call
    downloads the fsaverage dataset (cached afterwards).

    Args:
        session_id: Session key. A recording must already be loaded.
        spacing: Source-space resolution: 'ico5' (~20k sources, standard) or 'oct6'.
    """
    from mne.datasets import fetch_fsaverage

    session = store.get(session_id)
    fs_dir = fetch_fsaverage()
    subjects_dir = os.path.dirname(fs_dir)
    subject = "fsaverage"

    bem_path = os.path.join(fs_dir, "bem", "fsaverage-5120-5120-5120-bem-sol.fif")
    if spacing == "oct6":
        # Build an oct6 source space on the fly (ico5 ships prebuilt).
        src = mne.setup_source_space(
            subject, spacing="oct6", subjects_dir=subjects_dir, add_dist=False
        )
    else:
        src = mne.read_source_spaces(
            os.path.join(fs_dir, "bem", "fsaverage-ico-5-src.fif")
        )

    session.subjects_dir = subjects_dir
    session.subject = subject
    session.trans = "fsaverage"  # MNE ships the fsaverage MRI-head transform
    session.src = src
    session.bem = bem_path
    session.log(f"Fetched fsaverage template head (spacing={spacing})")
    n_sources = sum(len(s["vertno"]) for s in src)
    return {
        "session_id": session_id,
        "subject": subject,
        "subjects_dir": subjects_dir,
        "spacing": spacing,
        "n_sources": int(n_sources),
        "note": "Template head model ready. Next: compute_forward.",
    }


@mcp.tool()
def compute_forward(session_id: str = "default", mindist: float = 5.0) -> dict:
    """Compute the forward solution (leadfield) mapping cortical sources to sensors.

    Requires a loaded recording with an electrode montage (call set_montage) and
    a template head model (call fetch_template_head).

    Args:
        mindist: Minimum distance (mm) of sources from the inner skull surface.
    """
    session, raw = store.require_raw(session_id)
    if session.src is None or session.bem is None:
        raise ValueError("No head model. Call fetch_template_head first.")
    if raw.info.get("dig") is None:
        raise ValueError("No montage set. Call set_montage first (e.g. standard_1020).")

    fwd = mne.make_forward_solution(
        raw.info,
        trans=session.trans,
        src=session.src,
        bem=session.bem,
        eeg=True,
        meg=False,
        mindist=mindist,
    )
    session.forward = fwd
    n_sources = fwd["nsource"]
    session.log(f"Computed forward solution ({n_sources} sources)")
    return {
        "session_id": session_id,
        "n_sources": int(n_sources),
        "n_channels": int(fwd["nchan"]),
        "note": "Leadfield ready. Next: compute_noise_covariance.",
    }


@mcp.tool()
def compute_noise_covariance(
    session_id: str = "default",
    method: str = "empirical",
    tmax: float | None = 0.0,
) -> dict:
    """Estimate the sensor noise covariance from epoch baseline periods.

    Uses the pre-stimulus interval (up to ``tmax``, default 0 s = event onset) of
    the epochs as the noise estimate. Requires epoch_neuro first.

    Args:
        method: 'empirical', 'shrunk', or 'auto' (regularized estimators).
        tmax: End of the baseline window used for noise, in seconds.
    """
    session, epochs = store.require_epochs(session_id)
    cov = mne.compute_covariance(epochs, tmax=tmax, method=method)
    session.noise_cov = cov
    session.log(f"Computed noise covariance (method={method}, tmax={tmax})")
    return {
        "session_id": session_id,
        "method": method,
        "n_channels": len(cov.ch_names),
        "rank": int(cov["dim"]),
        "note": "Noise covariance ready. Next: make_inverse_operator.",
    }


@mcp.tool()
def make_inverse_operator(
    session_id: str = "default", loose: float = 0.2, depth: float = 0.8
) -> dict:
    """Assemble the inverse operator from the forward solution and noise covariance.

    Requires compute_forward and compute_noise_covariance. The operator is reused
    by apply_inverse for any distributed method (MNE/dSPM/sLORETA/eLORETA).

    Args:
        loose: Loose-orientation constraint in [0, 1] (0.2 typical for surface src).
        depth: Depth weighting exponent (0.8 typical) to counter the bias toward
            superficial sources.
    """
    from mne.minimum_norm import make_inverse_operator as _make_inv

    session = store.get(session_id)
    if session.forward is None:
        raise ValueError("No forward solution. Call compute_forward first.")
    if session.noise_cov is None:
        raise ValueError("No noise covariance. Call compute_noise_covariance first.")
    evoked = _evoked_for_inverse(session, condition=None)
    inv = _make_inv(evoked.info, session.forward, session.noise_cov, loose=loose, depth=depth)
    session.inverse_operator = inv
    session.log(f"Built inverse operator (loose={loose}, depth={depth})")
    return {
        "session_id": session_id,
        "loose": loose,
        "depth": depth,
        "note": "Inverse operator ready. Next: apply_inverse.",
    }


@mcp.tool()
def apply_inverse(
    session_id: str = "default",
    method: Literal["MNE", "dSPM", "sLORETA", "eLORETA"] = "dSPM",
    snr: float = 3.0,
    condition: str | None = None,
    save_stc: str | None = None,
) -> dict:
    """Estimate distributed cortical source activity for the ERP.

    Averages the epochs (optionally for one condition) and applies the inverse
    operator, then reports the peak-activation vertex, hemisphere, and latency.

    Args:
        method: 'MNE', 'dSPM', 'sLORETA', or 'eLORETA'.
        snr: Assumed signal-to-noise ratio (sets regularization lambda^2 = 1/snr^2).
        condition: Event-id name to localize (None = all epochs averaged).
        save_stc: If given, save the source estimate to this path stem (.stc/.h5).
    """
    from mne.minimum_norm import apply_inverse as _apply_inv

    session = store.get(session_id)
    if session.inverse_operator is None:
        raise ValueError("No inverse operator. Call make_inverse_operator first.")
    evoked = _evoked_for_inverse(session, condition=condition)
    stc = _apply_inv(evoked, session.inverse_operator, lambda2=_lambda2(snr), method=method)
    session.stc = stc

    # Peak activation across space and time.
    vtx, t_peak = stc.get_peak(vert_as_index=False, time_as_index=False)
    hemi = "lh" if vtx in stc.vertices[0] else "rh"
    peak_val = float(np.abs(stc.data).max())

    saved = None
    if save_stc:
        stc.save(save_stc, overwrite=True)
        saved = save_stc
    session.log(f"Applied inverse method={method} snr={snr} condition={condition}")
    return to_jsonable(
        {
            "session_id": session_id,
            "method": method,
            "snr": snr,
            "condition": condition,
            "n_sources": int(stc.data.shape[0]),
            "time_range_s": [float(stc.times[0]), float(stc.times[-1])],
            "peak": {
                "vertex": int(vtx),
                "hemisphere": hemi,
                "latency_ms": float(t_peak * 1000),
                "amplitude": peak_val,
            },
            "saved_stc": saved,
        }
    )


@mcp.tool()
def apply_lcmv_beamformer(
    session_id: str = "default",
    condition: str | None = None,
    reg: float = 0.05,
    save_stc: str | None = None,
) -> dict:
    """Localize sources with an LCMV beamformer (an alternative to minimum-norm).

    Uses the epoch data covariance for the spatial filter and the noise
    covariance for whitening. Requires compute_forward and
    compute_noise_covariance.

    Args:
        condition: Event-id name to localize (None = all epochs).
        reg: Diagonal loading (regularization) of the data covariance.
        save_stc: Optional path stem to save the source estimate.
    """
    from mne.beamformer import apply_lcmv, make_lcmv

    session, epochs = store.require_epochs(session_id)
    if session.forward is None:
        raise ValueError("No forward solution. Call compute_forward first.")
    if session.noise_cov is None:
        raise ValueError("No noise covariance. Call compute_noise_covariance first.")

    selected = epochs[condition] if condition else epochs
    data_cov = mne.compute_covariance(selected, tmin=0.0, method="empirical")
    evoked = _evoked_for_inverse(session, condition=condition)
    filters = make_lcmv(
        evoked.info,
        session.forward,
        data_cov,
        reg=reg,
        noise_cov=session.noise_cov,
        pick_ori="max-power",
        weight_norm="unit-noise-gain",
    )
    stc = apply_lcmv(evoked, filters)
    session.stc = stc
    vtx, t_peak = stc.get_peak(vert_as_index=False, time_as_index=False)
    hemi = "lh" if vtx in stc.vertices[0] else "rh"

    saved = None
    if save_stc:
        stc.save(save_stc, overwrite=True)
        saved = save_stc
    session.log(f"Applied LCMV beamformer condition={condition} reg={reg}")
    return to_jsonable(
        {
            "session_id": session_id,
            "method": "LCMV",
            "condition": condition,
            "n_sources": int(stc.data.shape[0]),
            "peak": {
                "vertex": int(vtx),
                "hemisphere": hemi,
                "latency_ms": float(t_peak * 1000),
            },
            "saved_stc": saved,
        }
    )


@mcp.tool()
def extract_label_timecourses(
    session_id: str = "default",
    parcellation: str = "aparc",
    mode: str = "mean_flip",
    top_n: int = 10,
) -> dict:
    """Extract ROI (atlas-region) time courses from the current source estimate.

    Reads an anatomical parcellation on fsaverage and summarizes source activity
    per region, ranking regions by peak absolute amplitude. Requires a source
    estimate (apply_inverse or apply_lcmv_beamformer first).

    Args:
        parcellation: 'aparc' (Desikan-Killiany, 68 regions) or 'aparc.a2009s'.
        mode: How to collapse sources within a label ('mean_flip', 'mean', 'pca_flip').
        top_n: How many strongest regions to return.
    """
    session = store.get(session_id)
    if session.stc is None:
        raise ValueError("No source estimate. Run apply_inverse or apply_lcmv_beamformer.")
    if session.src is None or session.subjects_dir is None:
        raise ValueError("No head model. Call fetch_template_head first.")

    labels = mne.read_labels_from_annot(
        session.subject, parc=parcellation, subjects_dir=session.subjects_dir
    )
    labels = [lab for lab in labels if "unknown" not in lab.name.lower()]
    label_ts = mne.extract_label_time_course(
        session.stc, labels, session.src, mode=mode, allow_empty=True
    )
    peak_amp = np.abs(label_ts).max(axis=1)
    peak_time_idx = np.abs(label_ts).argmax(axis=1)
    order = np.argsort(peak_amp)[::-1][:top_n]

    regions = []
    for i in order:
        regions.append(
            {
                "region": labels[i].name,
                "hemisphere": labels[i].hemi,
                "peak_amplitude": float(peak_amp[i]),
                "peak_latency_ms": float(session.stc.times[peak_time_idx[i]] * 1000),
            }
        )
    session.log(f"Extracted {len(labels)} label time courses ({parcellation})")
    return to_jsonable(
        {
            "session_id": session_id,
            "parcellation": parcellation,
            "n_regions": len(labels),
            "top_regions": regions,
        }
    )


@mcp.tool()
def plot_source_timecourses(
    session_id: str = "default", parcellation: str = "aparc", top_n: int = 5
) -> dict:
    """Plot the time courses of the strongest ROIs as a PNG (base64 data URI).

    A 2D matplotlib summary of source activity that works headlessly (no 3D
    brain rendering required). Requires a source estimate.
    """
    import matplotlib.pyplot as plt

    session = store.get(session_id)
    if session.stc is None:
        raise ValueError("No source estimate. Run apply_inverse or apply_lcmv_beamformer.")

    labels = mne.read_labels_from_annot(
        session.subject, parc=parcellation, subjects_dir=session.subjects_dir
    )
    labels = [lab for lab in labels if "unknown" not in lab.name.lower()]
    label_ts = mne.extract_label_time_course(
        session.stc, labels, session.src, mode="mean_flip", allow_empty=True
    )
    peak_amp = np.abs(label_ts).max(axis=1)
    order = np.argsort(peak_amp)[::-1][:top_n]
    times_ms = session.stc.times * 1000

    fig, ax = plt.subplots(figsize=(8, 5))
    for i in order:
        ax.plot(times_ms, label_ts[i], label=labels[i].name)
    ax.axvline(0, color="k", lw=0.8, ls="--")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Source amplitude (a.u.)")
    ax.set_title(f"Top {top_n} ROI source time courses ({parcellation})")
    ax.legend(fontsize=7, loc="best")
    uri = figure_to_data_uri(fig)
    return {"session_id": session_id, "image": uri, "kind": "source_timecourses"}


@mcp.tool()
def plot_source_brain(
    session_id: str = "default", time_ms: float | None = None, hemi: str = "both"
) -> dict:
    """Render the source estimate on a 3D cortical surface at its peak time.

    Requires an offscreen 3D backend (pyvista + a software/GL renderer). If that
    is unavailable in the environment, returns a clear message instead of failing
    — use plot_source_timecourses for a dependency-free 2D summary.
    """
    session = store.get(session_id)
    if session.stc is None:
        raise ValueError("No source estimate. Run apply_inverse or apply_lcmv_beamformer.")
    try:
        mne.viz.set_3d_backend("pyvistaqt")
    except Exception:
        try:
            import pyvista  # noqa: F401
        except Exception:
            return {
                "session_id": session_id,
                "image": None,
                "note": (
                    "3D rendering backend not available in this environment. "
                    "Use plot_source_timecourses for a 2D ROI summary."
                ),
            }
    if time_ms is None:
        _, t_peak = session.stc.get_peak(time_as_index=False)
        time_ms = float(t_peak * 1000)
    try:
        brain = session.stc.plot(
            subject=session.subject,
            subjects_dir=session.subjects_dir,
            hemi=hemi,
            initial_time=time_ms / 1000.0,
            time_unit="s",
            background="white",
            size=(800, 600),
        )
        screenshot = brain.screenshot()
        brain.close()
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 6))
        ax.imshow(screenshot)
        ax.axis("off")
        uri = figure_to_data_uri(fig)
        return {"session_id": session_id, "image": uri, "kind": "source_brain",
                "time_ms": time_ms}
    except Exception as exc:
        return {
            "session_id": session_id,
            "image": None,
            "note": f"3D render failed ({exc}). Use plot_source_timecourses instead.",
        }
