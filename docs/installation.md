# Installation

neuro-mcp requires **Python ≥ 3.10**. The core install pulls in MNE-Python,
SciPy/NumPy/scikit-learn, matplotlib, and Plotly; several capabilities are
gated behind optional extras so you only pay for what you use.

This page walks through everything from a bare Python environment to a
working tool call inside Claude Code or Codex CLI.

## 1. Create an environment

```bash
conda create -n neuro-mcp python=3.11 -y   # or any Python >=3.10 env
conda activate neuro-mcp
```

A virtualenv works equally well if you don't use conda.

## 2. Install neuro-mcp

```bash
pip install neuro-mcp
```

This installs from [PyPI](https://pypi.org/project/neuro-mcp/) and gives you
processing (`tools_core.py`), source imaging (`tools_source.py`), the
data/EHR store on SQLite, and the neuroii visualization/annotation tools
(`tools_viz_neuroii.py`, `tools_neuroii.py`) — everything except a production
database driver and 3D brain rendering.

### Optional extras

| Extra | Installs | Unlocks |
|---|---|---|
| `postgres` | `psycopg[binary]>=3.1` | `DATABASE_URL=postgresql+psycopg://...` for a shared/production data store |
| `viz3d` | `pyvista`, `pyvistaqt`, `PySide6` | `plot_source_brain` renders a real 3D cortical surface instead of a "backend not available" note |

```bash
pip install "neuro-mcp[postgres]"
pip install "neuro-mcp[viz3d]"
# combine as needed:
pip install "neuro-mcp[postgres,viz3d]"
```

### Installing from source instead (for contributors)

If you're working on neuro-mcp itself rather than just using it, clone the
repo and install in editable mode instead of step 2 above:

```bash
git clone https://github.com/AImplifier/neuro-mcp.git
cd neuro-mcp
pip install -e .                  # core
pip install -e ".[postgres]"      # + extras, same names as above
pip install -e ".[dev]"           # + pytest, build, twine
pip install -e ".[docs]"          # + mkdocs, mkdocs-material (build this site locally)
```

## 3. Verify the install

```bash
python -c "import neuro_mcp; print(neuro_mcp.__version__)"
python -c "from neuro_mcp.server import main; print(main)"
```

Don't run `python -m neuro_mcp` or the `neuro-mcp` console script directly in
a shell you plan to keep using — it starts a blocking stdio MCP server with no
`--help` flag. Register it with an MCP host instead (next step), or drive it
programmatically the way `testing/verify.py` does, via FastMCP's in-memory
`Client`.

## 4. Connect it to an agent

### Claude Code

```bash
claude mcp add neuro-mcp -- neuro-mcp
```
Everything after `--` is the command Claude Code runs to start the server;
stdio is the default transport for local commands.

With environment variables (see [Configuration](configuration.md) for the
full list):
```bash
claude mcp add neuro-mcp --env DATABASE_URL=<value> --env BIDS_ROOT=<value> -- neuro-mcp
```

Scope controls where it's available:
```bash
claude mcp add --scope user neuro-mcp -- neuro-mcp     # all your projects
claude mcp add --scope project neuro-mcp -- neuro-mcp  # shared via .mcp.json in the repo
claude mcp add --scope local neuro-mcp -- neuro-mcp    # this project only (default)
```

Verify and remove:
```bash
claude mcp list              # shows a connected status once it's up
claude mcp remove neuro-mcp
```

### Codex CLI

```bash
codex mcp add neuro-mcp -- neuro-mcp
```

Or edit `~/.codex/config.toml` directly:
```toml
[mcp_servers.neuro-mcp]
command = "neuro-mcp"
args = []

[mcp_servers.neuro-mcp.env]
DATABASE_URL = "..."
BIDS_ROOT = "..."
```

Note Codex uses snake_case `mcp_servers` in its TOML config, unlike Claude
Code's `mcpServers` JSON — don't mix the two formats up if you're copying
config between hosts.

### Other MCP hosts

Any host that reads a `mcpServers` JSON block works the same way:

```json
{
  "mcpServers": {
    "neuro-analysis": {
      "command": "/path/to/envs/neuro-mcp/bin/python",
      "args": ["-m", "neuro_mcp"],
      "env": {
        "DATABASE_URL": "sqlite:////data/neuro_mcp.db",
        "BIDS_ROOT": "/data/bids"
      }
    }
  }
}
```
Point `command` at the interpreter inside the environment where you installed
`neuro-mcp` — this sidesteps any `PATH` ambiguity between multiple Python
environments.

## 5. Try it

Once connected, ask your agent something like *"load this EEG recording and
show me the raw traces"* — no need to remember tool names, the agent handles
that. Walk through a full first session in the
[Tutorial: A Clinician's First EEG Review](examples/tutorial-first-eeg-review.md),
or jump straight to the [Tool Reference](tools/index.md) if you'd rather see
the raw call signatures.

## Run the test suite

```bash
python testing/verify.py        # fast smoke test
python testing/full_verify.py   # comprehensive, all 54 tools, writes testing/REPORT.md
```

See [Testing & Verification](testing.md) for the full picture.
