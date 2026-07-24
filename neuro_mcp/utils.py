"""Shared helpers: frequency bands, plot encoding, and JSON-safe conversion."""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np

# Canonical EEG frequency bands (Hz). Used for band-power summaries.
FREQ_BANDS: dict[str, tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy types/arrays into plain JSON-serializable Python."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        val = float(obj)
        return None if (np.isnan(val) or np.isinf(val)) else val
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    return obj


def figure_to_data_uri(fig, dpi: int = 100, close: bool = True) -> str:
    """Render a matplotlib Figure to a base64-encoded PNG data URI."""
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    if close:
        plt.close(fig)
    return f"data:image/png;base64,{encoded}"


def trapz(y, x, axis: int = -1):
    """Trapezoidal integration that works on both numpy 1.x and 2.x.

    numpy 2.0 renamed ``trapz`` to ``trapezoid``; keep a single call site.
    """
    fn = getattr(np, "trapezoid", None) or np.trapz
    return fn(y, x=x, axis=axis)


def band_from_name(band: str) -> tuple[float, float]:
    """Resolve a band name (e.g. 'alpha') to its (fmin, fmax) range."""
    key = band.lower().strip()
    if key not in FREQ_BANDS:
        raise ValueError(
            f"Unknown band '{band}'. Choose from: {', '.join(FREQ_BANDS)}."
        )
    return FREQ_BANDS[key]
