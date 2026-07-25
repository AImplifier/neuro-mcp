# Configuration

neuro-mcp is configured entirely through environment variables (see
`neuro_mcp/config.py`), so the same binary works for a zero-setup local run
and a shared clinical deployment without code changes.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///~/.neuro-mcp/neuro_mcp.db` | The data/EHR store. Production: `postgresql+psycopg://user:pass@host/db` (requires the `postgres` extra). |
| `BIDS_ROOT` | `~/.neuro-mcp/bids` | Root of the BIDS-on-disk recording tree that `import_recording` writes into. |
| `NEUROII_API_URL` | *(unset)* | Base URL of a neuroii instance. Unset → the `neuroii_*` tools return the documented `not_configured` contract instead of calling out. |
| `NEUROII_API_TOKEN` | *(unset)* | Optional bearer token for `NEUROII_API_URL`. |
| `NEURO_MCP_HOME` | `~/.neuro-mcp` | Base directory used to derive the default SQLite path and BIDS root when `DATABASE_URL`/`BIDS_ROOT` aren't set. |

The default (SQLite + a scratch BIDS dir under `~/.neuro-mcp`) runs with
**zero setup** — good for local development and the `testing/` scripts (which
override `DATABASE_URL`/`BIDS_ROOT` with temp directories so they never touch
your real data home). Point `DATABASE_URL` at Postgres for a multi-user or
clinical deployment.

## Registering with an MCP host

See [Installation → Connect it to an agent](installation.md#4-connect-it-to-an-agent)
for exact steps for Claude Code, Codex CLI, and any other MCP host — this
page covers what to configure, that page covers how to wire it up.

## neuroii integration status

neuroii integration is greenfield: the tools in
[neuroii Integration](tools/neuroii.md) define and return the expected REST
contract (see `neuro_mcp/neuroii/client.py`). Until `NEUROII_API_URL` is set,
they respond `{"status": "not_configured", "contract": {...}}` so the neuroii
app has a fixed target to implement against:

- `POST /api/v1/recordings`
- `POST /api/v1/viz-sessions`
- `GET /api/v1/recordings/{id}/annotations`
