"""neuroii visualization tools — generate self-contained interactive HTML that
reproduces the NEUROII views faithfully (no simplification).

  * visualize_timeseries — RawView: stacked channels, page navigation, scroll
                           amplitude, grid toggle
  * visualize_averaging  — EvokedView: stacked channels + green cursor + topomap,
                           time slider, summary sidebar
  * visualize_esi        — EsiView: volumetric source on 3 orthogonal MRI slices
                           (canvas, crosshair, L/R + MNI labels), ERP butterfly
                           with red cursor + blue half-peak marker, time slider,
                           global/frame scale toggle, mask-threshold slider

Figures reuse NEUROII's plotting conventions via neuro_mcp.viz.neuroii_plots and
the volumetric slice logic in neuro_mcp.viz.esi_slices; the HTML/JS shells live
in neuro_mcp.viz.html_views.
"""

from __future__ import annotations

import os
from pathlib import Path

import mne
import numpy as np
import plotly.graph_objects as go

from .app import mcp
from .config import get_config
from .session import store
from .viz.esi_slices import build_esi_payload, compute_volume_stc
from .viz.html_views import esi_html, evoked_html, raw_html
from .viz.neuroii_plots import (
    TOPO_COLORSCALE,
    auto_sigma,
    build_stacked_traces,
    head_outline_shapes,
    project_electrodes,
    topomap_zgrid,
    uniform_dx,
)

mne.set_log_level("ERROR")


def _viz_dir() -> Path:
    d = Path(get_config().bids_root).parent / "viz"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_out(out_path: str | None, default_name: str) -> str:
    if out_path:
        p = Path(out_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    return str(_viz_dir() / default_name)


def _write(html: str, out_path: str) -> int:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.getsize(out_path)


# --------------------------------------------------------------------------- #
# 1. RawView: stacked channels + paging + scroll-amplitude + grid toggle
# --------------------------------------------------------------------------- #
@mcp.tool()
def visualize_timeseries(
    session_id: str = "default",
    page_len: float = 10.0,
    n_channels: int = 30,
    max_seconds: float = 60.0,
    out_path: str | None = None,
) -> dict:
    """Render the RawView EEG time-series viewer as interactive HTML.

    Stacked channels on one amplitude scale, with NEUROII's controls: page
    navigation (⏮ ◀ ▶ ⏭), a page-length box, scroll-to-zoom amplitude, and a
    grid toggle. Requires a loaded recording (load_neuro / import_recording).

    Args:
        session_id: Processing session holding the recording.
        page_len: Initial page length in seconds.
        n_channels: Max EEG channels shown (from the top).
        max_seconds: How much of the recording to embed (from the start).
        out_path: Output .html (default <data>/viz/timeseries_<session>.html).
    """
    _, raw = store.require_raw(session_id)
    picks = mne.pick_types(raw.info, eeg=True, exclude=[])[:n_channels]
    ch_names = [raw.ch_names[i] for i in picks]
    sfreq = float(raw.info["sfreq"])
    embed_stop = min(max_seconds, float(raw.times[-1]))
    data = raw.get_data(picks=picks, start=0, stop=int(embed_stop * sfreq))
    times = raw.times[: int(embed_stop * sfreq)]
    sigma = auto_sigma(data)

    traces, yaxes, annotations = build_stacked_traces(
        data, ch_names, raw.info["bads"], sigma, x0=float(times[0]), dx=uniform_dx(times)
    )
    fig = go.Figure(data=[go.Scatter(**t) for t in traces])
    layout = dict(
        annotations=annotations, showlegend=False, plot_bgcolor="#ffffff",
        margin=dict(l=84, r=20, t=10, b=40), autosize=True,
        font=dict(size=14),
        xaxis=dict(title=dict(text="Time (s)", font=dict(size=15)),
                   tickfont=dict(size=13), showgrid=True, dtick=1.0,
                   gridcolor="#d5d5d5", gridwidth=1,
                   minor=dict(showgrid=True, dtick=0.2, gridcolor="#e8e8e8",
                              griddash="dash")),
    )
    layout.update(yaxes)
    fig.update_layout(**layout)

    html, favicon = raw_html(
        f"EEG time series — {len(ch_names)} channels", fig.to_dict(),
        duration=float(embed_stop), page_len=page_len,
    )
    out = _resolve_out(out_path, f"timeseries_{session_id}.html")
    size = _write(html, out)
    return {"session_id": session_id, "kind": "timeseries", "out_path": out,
            "n_channels": len(ch_names), "embedded_seconds": float(embed_stop), "bytes": size}


# --------------------------------------------------------------------------- #
# 2. EvokedView: stacked channels + green cursor + topomap + sidebar
# --------------------------------------------------------------------------- #
@mcp.tool()
def visualize_averaging(
    session_id: str = "default",
    condition: str | None = None,
    n_frames: int = 40,
    out_path: str | None = None,
) -> dict:
    """Render the EvokedView averaged-ERP viewer as interactive HTML.

    Left: the averaged ERP as stacked channels with a green time cursor. Right:
    the scalp topomap at the cursor time. A time slider scrubs both, and a
    sidebar shows nave / peak / tmin / tmax. Requires epochs (epoch_neuro) with a
    montage (set_montage).
    """
    session, epochs = store.require_epochs(session_id)
    selected = epochs[condition] if condition else epochs
    evoked = selected.average()
    picks = mne.pick_types(evoked.info, eeg=True, exclude="bads")
    evoked = evoked.copy().pick([evoked.ch_names[i] for i in picks])
    times = evoked.times
    data = evoked.get_data()
    sigma = auto_sigma(data)
    frame_idx = np.linspace(0, len(times) - 1, min(n_frames, len(times))).astype(int)
    proj = project_electrodes(evoked)
    t0 = float(times[frame_idx[0]])

    # ── Channel figure (left pane): stacked ERP channels + green cursor ──
    traces, yaxes, annotations = build_stacked_traces(
        data, evoked.ch_names, evoked.info["bads"], sigma,
        x0=float(times[0]), dx=uniform_dx(times)
    )
    ch_fig = go.Figure(data=[go.Scatter(**t) for t in traces])
    ch_layout = dict(
        showlegend=False, plot_bgcolor="#ffffff", margin=dict(l=64, r=10, t=10, b=36),
        autosize=True, annotations=annotations,
        xaxis=dict(title="Time (s)", anchor="y", showgrid=True, gridcolor="#eee"),
        shapes=[_green_cursor(t0)],
    )
    ch_layout.update(yaxes)
    ch_fig.update_layout(**ch_layout)

    # ── Topomap figure (right pane): its own square axes so resizing the pane
    #    never collapses it (each chart owns its layout). ──
    x, y, z, vmax = topomap_zgrid(evoked, t0, proj)
    dx_, dy_, dname, valid = proj
    topo_fig = go.Figure(data=[
        go.Contour(x=x.tolist(), y=y.tolist(), z=z.tolist(), connectgaps=True,
                   colorscale=TOPO_COLORSCALE, zmin=-vmax, zmax=vmax, zmid=0,
                   showscale=True, colorbar=dict(title="µV", len=0.7)),
        go.Scatter(x=dx_[valid].tolist(), y=dy_[valid].tolist(), mode="markers",
                   marker=dict(color="black", size=4), showlegend=False,
                   hoverinfo="text", hovertext=[n for n, v in zip(dname, valid) if v]),
    ])
    topo_fig.update_layout(
        autosize=True, margin=dict(l=6, r=6, t=10, b=6),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        xaxis=dict(range=[-1.2, 1.2], visible=False, constrain="domain"),
        yaxis=dict(range=[-1.2, 1.2], visible=False, scaleanchor="x", scaleratio=1,
                   constrain="domain"),
        shapes=head_outline_shapes(),
    )

    # Per-frame topomap data for the client-side slider.
    tframes = []
    for fi in frame_idx:
        tt = float(times[fi])
        _, _, zz, vm = topomap_zgrid(evoked, tt, proj)
        tframes.append({"t": tt, "z": zz.tolist(), "vmax": float(vm)})

    ch, lat, amp = evoked.get_peak(return_amplitude=True)
    summary = {
        "nave": int(evoked.nave),
        "peak": f"{lat * 1000:.0f} ms",
        "peak ch": ch,
        "tmin": f"{times[0]:.3f}s",
        "tmax": f"{times[-1]:.3f}s",
        "n epochs": len(selected),
    }
    html, favicon = evoked_html(
        f"Averaged ERP — {len(selected)} epochs"
        + (f", '{condition}'" if condition else ""),
        ch_fig.to_dict(), topo_fig.to_dict(), tframes, summary)
    out = _resolve_out(out_path, f"averaging_{session_id}.html")
    size = _write(html, out)
    return {"session_id": session_id, "kind": "averaging", "out_path": out,
            "n_epochs": len(selected), "n_frames": len(frame_idx), "bytes": size}


def _green_cursor(t):
    return dict(type="line", x0=t, x1=t, xref="x", y0=0, y1=1, yref="paper",
                line=dict(color="green", width=1, dash="dot"))


# --------------------------------------------------------------------------- #
# 3. EsiView: volumetric brain slices (canvas) + butterfly + full controls
# --------------------------------------------------------------------------- #
def _gfp_half_max_time(evoked) -> float | None:
    """Rising-edge 50%-of-max GFP time (as NEUROII computes tHalf)."""
    gfp = evoked.get_data().std(axis=0)
    if gfp.size == 0:
        return None
    pk = int(np.argmax(gfp))
    thr = 0.5 * gfp[pk]
    idx = pk
    for i in range(pk + 1):
        if gfp[i] >= thr:
            idx = i
            break
    return float(evoked.times[idx])


@mcp.tool()
def visualize_esi(
    session_id: str = "default",
    method: str = "dSPM",
    n_frames: int = 40,
    out_path: str | None = None,
) -> dict:
    """Render the EsiView source-imaging viewer as interactive HTML — NEUROII style.

    Computes a volumetric source estimate on the fsaverage template and shows it
    on three orthogonal MRI slices (sagittal / coronal / axial) rendered to
    canvas with a black-blue-white-red activation overlay, crosshair at the peak,
    L/R and MNI-coordinate labels; the cut planes recentre on each frame's peak.
    Below, the ERP butterfly carries a red current-time cursor and a blue
    half-peak marker. Controls: a time slider, a global/frame colormap-scale
    toggle, and a mask-threshold slider. Requires epochs (epoch_neuro) + montage.

    Args:
        session_id: Session holding the epochs.
        method: Inverse method ('dSPM', 'MNE', 'sLORETA', 'eLORETA').
        n_frames: Number of time points on the slider.
        out_path: Output .html (default <data>/viz/esi_<session>.html).
    """
    session = store.get(session_id)
    stc = compute_volume_stc(session, session_id, method=method)
    payload = build_esi_payload(stc, n_frames=n_frames)

    # ERP butterfly (all channels) from the source evoked.
    evoked = session.epochs.average()
    picks = mne.pick_types(evoked.info, eeg=True, exclude="bads")
    ev = evoked.copy().pick([evoked.ch_names[i] for i in picks])
    times = ev.times
    d_uv = ev.get_data() * 1e6
    butterfly = go.Figure(
        data=[go.Scatter(x=times.tolist(), y=d_uv[i].tolist(), mode="lines",
                         line=dict(width=1, color="rgba(60,60,60,0.5)"),
                         name=ev.ch_names[i], hovertemplate=f"{ev.ch_names[i]}<extra></extra>",
                         showlegend=False) for i in range(len(ev.ch_names))],
        layout=go.Layout(margin=dict(l=60, r=20, t=6, b=36), plot_bgcolor="#ffffff",
                         xaxis=dict(title="Time (s)", showgrid=True, gridcolor="#eee"),
                         yaxis=dict(title="µV", showgrid=True, gridcolor="#eee")),
    )
    t_half = _gfp_half_max_time(ev)

    html, favicon = esi_html(
        f"ESI ({method}) — volumetric source on MRI; peak @ "
        f"{payload['peak_time']*1000:.0f} ms", payload, butterfly.to_dict(), t_half)
    out = _resolve_out(out_path, f"esi_{session_id}.html")
    size = _write(html, out)
    return {"session_id": session_id, "kind": "esi", "out_path": out, "method": method,
            "n_frames": len(payload["frames"]), "peak_latency_ms": float(payload["peak_time"] * 1000),
            "bytes": size}
