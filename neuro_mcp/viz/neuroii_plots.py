"""Plotting primitives adapted from the NEUROII web app (workflow/plotting_util.py).

Ported into neuro-mcp so the visualization tools can render the same MNE-style
figures (stacked multi-channel time series, azimuthal-equidistant scalp topomap)
without the Flask/React backend. The topomap head-projection is refactored into a
reusable z-grid function so a self-contained HTML file can scrub time client-side
via Plotly frames instead of re-querying a server.

Original logic and comments are from NEUROII (the user's own app); this is a
derivative for offline standalone-HTML rendering.
"""

from __future__ import annotations

import re

import mne
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator

_BAD_CH_LINE_COLOR = "lightgrey"
_DEFAULT_CH_LINE_COLOR = "black"
_SIGMA_SAMPLE_LIMIT = 200_000

# NEUROII activation colormap (blue-white-red) and topomap colormap.
ACT_COLORSCALE = [[0.0, "#1f77b4"], [0.5, "#ffffff"], [1.0, "#d62728"]]
TOPO_COLORSCALE = "RdBu_r"


def decide_ch_color(ch_name, bads):
    return _BAD_CH_LINE_COLOR if ch_name in bads else _DEFAULT_CH_LINE_COLOR


def auto_sigma(data):
    """Volts per channel row, following MNE's ``scalings='auto'`` (2 * IQR)."""
    arr = np.asarray(data, dtype=float)
    if arr.ndim == 1:
        arr = arr[np.newaxis, :]
    if arr.shape[-1] > _SIGMA_SAMPLE_LIMIT:
        step = int(np.ceil(arr.shape[-1] / _SIGMA_SAMPLE_LIMIT))
        arr = arr[..., ::step]
    arr = arr - np.nanmedian(arr, axis=-1, keepdims=True)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return 1.0
    q25, q75 = np.percentile(finite, [25, 75])
    sigma = 2.0 * float(q75 - q25)
    if not np.isfinite(sigma) or sigma <= 0:
        span = float(np.max(finite) - np.min(finite))
        sigma = span if np.isfinite(span) and span > 0 else 1.0
    return sigma


def uniform_dx(times):
    times = np.asarray(times, dtype=float)
    if times.size < 2:
        return 1.0
    return float((times[-1] - times[0]) / (times.size - 1))


def channel_row_fraction(ii, nchan):
    return 1.0 - (ii + 0.5) / nchan


def channel_axis_range(ii, nchan, sigma):
    q = channel_row_fraction(ii, nchan)
    span = nchan * sigma
    return [-q * span, (1.0 - q) * span]


def build_stacked_traces(data, ch_names, bads, sigma, x0, dx, remove_dc=True,
                         label_size=13):
    """Return (traces, yaxis_layout, annotations) for a stacked multi-channel plot.

    Split out from NEUROII's build_stacked_figure so the same stack can be placed
    on a specific subplot axis. ``data`` is (nchan, nsamples) in volts.
    ``label_size`` is the channel-name font size.
    """
    data = np.asarray(data, dtype=float)
    nchan = data.shape[0]
    if remove_dc:
        data = data - np.nanmean(data, axis=1, keepdims=True)

    yaxes = {}
    traces = []
    annotations = []
    for ii in range(nchan):
        axis_cfg = dict(
            range=channel_axis_range(ii, nchan, sigma),
            showticklabels=False, zeroline=False, showgrid=False, visible=False,
        )
        if ii == 0:
            axis_cfg.update(anchor="x")
        else:
            axis_cfg.update(overlaying="y")
        yaxes["yaxis" if ii == 0 else "yaxis%d" % (ii + 1)] = axis_cfg

        trace = dict(
            x0=x0, dx=dx, y=data[ii].tolist(), mode="lines",
            line={"color": decide_ch_color(ch_names[ii], bads), "width": 1},
            name=ch_names[ii], hovertemplate=f"{ch_names[ii]}<extra></extra>",
        )
        if ii:
            trace["yaxis"] = "y%d" % (ii + 1)
        traces.append(trace)

        annotations.append(dict(
            x=0, xanchor="right", xshift=-8,
            y=channel_row_fraction(ii, nchan),
            xref="paper", yref="paper", text=ch_names[ii], showarrow=False,
            font=dict(size=label_size),
        ))
    return traces, yaxes, annotations


# --- Scalp topomap (azimuthal-equidistant projection, from NEUROII head_figure) --
_RENAME_1020 = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}
_DUP_SUFFIX_RE = re.compile(r"-\d+$")


def project_electrodes(evoked):
    """Project 3-D electrode positions to the 2-D head disc (MNE topomap layout).

    Returns (data_x, data_y, names, valid) where invalid channels (no resolvable
    position) are marked False in ``valid``.
    """
    ch_loc = evoked.info["chs"]
    data_name = [c["ch_name"] for c in ch_loc]
    lookup_names = [_RENAME_1020.get(n, n) for n in data_name]

    montage = mne.channels.make_standard_montage("standard_1020")
    mpos = montage.get_positions()["ch_pos"]
    mpos_lower = {k.lower(): v for k, v in mpos.items()}

    locs3d = []
    for i, name in enumerate(lookup_names):
        key = name.lower()
        if key not in mpos_lower:
            stripped = _DUP_SUFFIX_RE.sub("", name).lower()
            if stripped in mpos_lower:
                key = stripped
        if key in mpos_lower:
            locs3d.append(mpos_lower[key])
        else:
            locs3d.append(ch_loc[i]["loc"][:3])
    locs3d = np.array(locs3d, dtype=float)

    norms = np.linalg.norm(locs3d, axis=1, keepdims=True)
    locs3d = locs3d / np.where(norms > 1e-10, norms, 1)
    x3, y3, z3 = locs3d[:, 0], locs3d[:, 1], locs3d[:, 2]
    theta = np.arccos(np.clip(z3, -1, 1))
    phi = np.arctan2(x3, y3)
    data_x = theta * np.sin(phi)
    data_y = theta * np.cos(phi)

    valid = np.isfinite(data_x) & np.isfinite(data_y)
    max_r = np.sqrt(data_x[valid] ** 2 + data_y[valid] ** 2).max() if valid.any() else 0
    if max_r > 0:
        data_x = data_x / max_r * 0.9
        data_y = data_y / max_r * 0.9
    return data_x, data_y, data_name, valid


def topomap_zgrid(evoked, time, proj, res=64):
    """Interpolated scalp potential grid at ``time`` (s). Returns (x, y, z, vmax)."""
    data_x, data_y, _, valid = proj
    frame_vals = evoked.get_data()[:, evoked.time_as_index(time).item()]
    real_pts = np.column_stack((data_x[valid], data_y[valid]))
    frame_vals_valid = frame_vals[valid]

    n_boundary = 16
    ang = np.linspace(0, 2 * np.pi, n_boundary, endpoint=False)
    boundary_pts = np.column_stack((np.cos(ang), np.sin(ang)))
    nearest = np.argmin(((boundary_pts[:, None, :] - real_pts[None, :, :]) ** 2).sum(axis=2), axis=1)
    intp = CloughTocher2DInterpolator(
        np.vstack((real_pts, boundary_pts)),
        np.concatenate((frame_vals_valid, frame_vals_valid[nearest])),
    )
    x = np.linspace(-1.2, 1.2, res)
    y = np.linspace(-1.2, 1.2, res)
    xv, yv = np.meshgrid(x, y)
    z = intp(np.column_stack((xv.reshape(-1), yv.reshape(-1)))).reshape(res, res)
    z[xv ** 2 + yv ** 2 > 1.0] = np.nan
    vmax = float(np.max(np.abs(frame_vals))) or 1.0
    return x, y, z, vmax


def head_outline_shapes():
    """Head circle + nose + ears as Plotly shapes (from NEUROII head_figure)."""
    return [
        {"type": "circle", "x0": -1, "y0": -1, "x1": 1, "y1": 1, "line": {"color": "black"}},
        {"type": "line", "x0": -0.1, "y0": 0.9949, "x1": 0, "y1": 1.1, "line": {"color": "black"}},
        {"type": "line", "x0": 0.1, "y0": 0.9949, "x1": 0, "y1": 1.1, "line": {"color": "black"}},
        {"type": "line", "x0": -0.9887, "y0": 0.15, "x1": -1.05, "y1": 0.15, "line": {"color": "black"}},
        {"type": "line", "x0": -1.05, "y0": 0.15, "x1": -1.05, "y1": -0.15, "line": {"color": "black"}},
        {"type": "line", "x0": -0.9887, "y0": -0.15, "x1": -1.05, "y1": -0.15, "line": {"color": "black"}},
        {"type": "line", "x0": 0.9887, "y0": 0.15, "x1": 1.05, "y1": 0.15, "line": {"color": "black"}},
        {"type": "line", "x0": 1.05, "y0": 0.15, "x1": 1.05, "y1": -0.15, "line": {"color": "black"}},
        {"type": "line", "x0": 0.9887, "y0": -0.15, "x1": 1.05, "y1": -0.15, "line": {"color": "black"}},
    ]
