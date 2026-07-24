"""Volumetric ESI brain-slice computation, ported from NEUROII (workflow_api.py).

Computes a volume source estimate on the fsaverage template and, for each time
frame, extracts three orthogonal MRI slices (sagittal/coronal/axial) with an
activation overlay, the peak-voxel cut planes, crosshair, and MNI coordinates —
matching NEUROII's esi_slice_data. Slices are encoded exactly as NEUROII does
(_enc transpose/flip conventions) and downsampled so the whole time course can be
embedded in a standalone HTML file for client-side canvas rendering.
"""

from __future__ import annotations

import base64
import os

import mne
import numpy as np
from scipy.ndimage import gaussian_filter

_geo_cache: dict = {}
_stc_cache: dict = {}  # session_id -> (VolSourceEstimate, method)


def _slice_geo():
    """fsaverage T1 (normalized grayscale) + source-vertex→voxel mapping + affine."""
    if "geo" in _geo_cache:
        return _geo_cache["geo"]
    import nibabel as nib
    from nibabel.affines import apply_affine

    fs_dir = mne.datasets.fetch_fsaverage(verbose=False)
    src_path = os.path.join(fs_dir, "bem", "fsaverage-vol-5-src.fif")
    src = mne.read_source_spaces(src_path, verbose=False)
    t1 = nib.load(os.path.join(fs_dir, "mri", "T1.mgz"))
    brain = t1.get_fdata().astype(np.float32)
    p995 = float(np.percentile(brain, 99.5)) or 1.0
    brain = np.clip(brain / p995, 0.0, 1.0)

    rr_mm = src[0]["rr"][src[0]["vertno"]] * 1000.0
    vox = np.round(apply_affine(np.linalg.inv(t1.affine), rr_mm)).astype(np.int32)
    vox = np.clip(vox, 0, np.array(brain.shape[:3]) - 1)
    geo = {"brain": brain, "vox": vox, "shape": tuple(int(s) for s in brain.shape[:3]),
           "affine": t1.affine, "src_path": src_path}
    _geo_cache["geo"] = geo
    return geo


def compute_volume_stc(session, session_id, method="dSPM"):
    """Compute (and cache per session) a volume source estimate for the ERP."""
    cached = _stc_cache.get(session_id)
    if cached and cached[1] == method:
        return cached[0]
    if session.epochs is None:
        raise ValueError("No epochs available. Run epoch_neuro first.")
    from mne.minimum_norm import apply_inverse, make_inverse_operator

    geo = _slice_geo()
    fs_dir = mne.datasets.fetch_fsaverage(verbose=False)
    bem = os.path.join(fs_dir, "bem", "fsaverage-5120-5120-5120-bem-sol.fif")
    evoked = session.epochs.average()
    if not any(p["desc"].startswith("Average EEG") for p in evoked.info["projs"]):
        evoked.set_eeg_reference("average", projection=True)
    evoked.apply_proj()

    fwd = mne.make_forward_solution(evoked.info, trans="fsaverage",
                                    src=geo["src_path"], bem=bem, eeg=True,
                                    mindist=5.0, verbose=False)
    cov = mne.compute_covariance(session.epochs, tmax=0.0, verbose=False)
    inv = make_inverse_operator(evoked.info, fwd, cov, verbose=False)
    stc = apply_inverse(evoked, inv, method=method, verbose=False)
    _stc_cache[session_id] = (stc, method)
    return stc


def _make_act_slice(vox, values, slice_dim, slice_idx, shape, threshold, sigma=3.0):
    """Project sources ≥ threshold to a volume, 3-D Gaussian smooth, extract slice."""
    vol = np.zeros(shape, dtype=np.float32)
    mask = np.abs(values) >= threshold
    if not mask.any():
        dims2 = [d for d in range(3) if d != slice_dim]
        return np.zeros((shape[dims2[0]], shape[dims2[1]]), dtype=np.float32)
    vol[vox[mask, 0], vox[mask, 1], vox[mask, 2]] = values[mask]
    vol = gaussian_filter(vol, sigma=sigma)
    sl = [slice(None)] * 3
    sl[slice_dim] = slice_idx
    return vol[tuple(sl)]


def _enc(arr2d, transpose=False, flip_lr=False, flip_ud=False, down=2):
    """Encode a 2D float32 slice as base64 (NEUROII _enc conventions + downsample)."""
    a = arr2d.T if transpose else arr2d
    if flip_lr:
        a = a[:, ::-1]
    if flip_ud:
        a = a[::-1, :]
    a = np.ascontiguousarray(a[::down, ::down].astype(np.float32))
    return {"data": base64.b64encode(a.tobytes()).decode("ascii"),
            "rows": int(a.shape[0]), "cols": int(a.shape[1])}


def build_esi_payload(stc, n_frames=20, down=2, pct=96.0):
    """Per-frame MRI + activation slices, cut planes, crosshair, and MNI coords.

    Cut planes recenter on each frame's peak voxel (as NEUROII does). Returns a
    JSON-serializable dict consumed by the standalone HTML canvas renderer.
    """
    from nibabel.affines import apply_affine

    geo = _slice_geo()
    brain, vox, shape, affine = geo["brain"], geo["vox"], geo["shape"], geo["affine"]
    data = stc.data.astype(np.float32)
    times = stc.times
    threshold = float(np.percentile(np.abs(data).ravel(), pct))

    peak_tidx = int(np.argmax(np.abs(data).max(axis=0)))
    frame_idx = np.linspace(0, len(times) - 1, min(n_frames, len(times))).astype(int)

    frames = []
    global_vmax = 0.0
    for fi in frame_idx:
        vals = data[:, fi]
        act_t = np.zeros(shape, dtype=np.float32)
        act_t[vox[:, 0], vox[:, 1], vox[:, 2]] = vals
        cx, cy, cz = [int(v) for v in np.unravel_index(int(np.argmax(np.abs(act_t))), shape)]

        sl_sag = _make_act_slice(vox, vals, 0, cx, shape, threshold)
        sl_cor = _make_act_slice(vox, vals, 2, cz, shape, threshold)
        sl_axi = _make_act_slice(vox, vals, 1, cy, shape, threshold)
        act = {
            "sagittal": _enc(sl_sag, transpose=False, down=down),
            "coronal": _enc(sl_cor, flip_lr=True, down=down),
            "axial": _enc(sl_axi, flip_lr=True, flip_ud=True, down=down),
        }
        mri = {
            "sagittal": _enc(brain[cx, :, :], transpose=False, down=down),
            "coronal": _enc(brain[:, :, cz], flip_lr=True, down=down),
            "axial": _enc(brain[:, cy, :], flip_lr=True, flip_ud=True, down=down),
        }
        vmax_frame = float(max(np.abs(sl_sag).max(), np.abs(sl_cor).max(),
                               np.abs(sl_axi).max())) or 1e-12
        global_vmax = max(global_vmax, vmax_frame)
        peak_mm = [round(float(v), 1) for v in apply_affine(affine, [cx, cy, cz])]
        frames.append({
            "t": float(times[fi]),
            "mri": mri, "act": act,
            "peak": [cx // down, cy // down, cz // down],  # downsampled voxel indices
            "peak_mm": peak_mm,
            "vmax_frame": vmax_frame,
        })

    return {
        "frames": frames,
        "global_vmax": float(global_vmax),
        "peak_time": float(times[peak_tidx]),
        "tmin": float(times[0]),
        "tmax": float(times[-1]),
        "n_times": int(len(times)),
    }
