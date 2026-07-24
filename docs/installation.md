# Installation

neuro-mcp requires **Python ≥ 3.10**. The core install pulls in MNE-Python,
SciPy/NumPy/scikit-learn, matplotlib, and Plotly; several capabilities are
gated behind optional extras so you only pay for what you use.

## Core install

```bash
conda create -n neuro-mcp python=3.11 -y   # or any Python >=3.10 env
conda activate neuro-mcp
pip install -e .
```

This gives you processing (`tools_core.py`), source imaging
(`tools_source.py`), the data/EHR store on SQLite, and the neuroii
visualization/annotation tools (`tools_viz_neuroii.py`, `tools_neuroii.py`) —
everything except a production database driver and 3D brain rendering.

## Optional extras

| Extra | Installs | Unlocks |
|---|---|---|
| `postgres` | `psycopg[binary]>=3.1` | `DATABASE_URL=postgresql+psycopg://...` for a shared/production data store |
| `viz3d` | `pyvista`, `pyvistaqt`, `PySide6` | `plot_source_brain` renders a real 3D cortical surface instead of a "backend not available" note |
| `dev` | `pytest`, `build`, `twine` | Building/publishing the package, plus the `testing/` scripts (which don't require pytest to run, but the extra keeps the tooling handy) |
| `docs` | `mkdocs`, `mkdocs-material` | Building this documentation site locally |

```bash
pip install -e ".[postgres]"
pip install -e ".[viz3d]"
pip install -e ".[dev]"
pip install -e ".[docs]"
# combine as needed, e.g.:
pip install -e ".[postgres,dev]"
```

## Verify the install

```bash
python -c "import neuro_mcp; print(neuro_mcp.__version__)"
python -c "from neuro_mcp.server import main; print(main)"
```

Don't run `python -m neuro_mcp` or the `neuro-mcp` console script directly in
a shell you plan to keep using — it starts a blocking stdio MCP server with no
`--help` flag. Register it with an MCP host instead (see
[Configuration](configuration.md)), or drive it programmatically the way
`testing/verify.py` does, via FastMCP's in-memory `Client`.

## Run the test suite

```bash
python testing/verify.py        # fast smoke test
python testing/full_verify.py   # comprehensive, all 54 tools, writes testing/REPORT.md
```

See [Testing & Verification](testing.md) for the full picture.
