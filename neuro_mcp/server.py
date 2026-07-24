"""neuro-mcp server entry point.

Imports the tool modules (registering their tools on the shared FastMCP
instance), initializes the database, and runs over stdio.

Run:  python -m neuro_mcp
"""

from __future__ import annotations

from .app import mcp
from .db import store

# Importing these registers their @mcp.tool() functions on `mcp`.
from . import tools_core  # noqa: E402,F401  (processing: I/O, preprocess, ICA, epoch, spectral)
from . import tools_source  # noqa: E402,F401  (source imaging / ESI)
from . import tools_data  # noqa: E402,F401  (subjects, EHR, datasets, annotations, audit)
from . import tools_neuroii  # noqa: E402,F401  (neuroii annotation/viz)
from . import tools_viz_neuroii  # noqa: E402,F401  (neuroii HTML visualizations)


def main() -> None:
    # Ensure tables exist before serving (idempotent).
    store.init_db()
    mcp.run()


if __name__ == "__main__":
    main()
