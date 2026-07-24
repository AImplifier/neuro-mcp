"""Environment-driven configuration for neuro-mcp.

All settings come from environment variables so the same server binary works for
a local single-user setup (SQLite + a scratch BIDS dir) and a clinical
deployment (Postgres + a shared BIDS root) without code changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_home() -> Path:
    root = os.environ.get("NEURO_MCP_HOME")
    if root:
        return Path(root).expanduser()
    return Path.home() / ".neuro-mcp"


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    database_url: str
    bids_root: Path
    neuroii_api_url: str | None
    neuroii_api_token: str | None

    @classmethod
    def from_env(cls) -> "Config":
        home = _default_data_home()
        # Default: a serverless SQLite file under the data home. Production sets
        # DATABASE_URL to e.g. postgresql+psycopg://user:pass@host/dbname.
        database_url = os.environ.get(
            "DATABASE_URL", f"sqlite:///{home / 'neuro_mcp.db'}"
        )
        bids_root = Path(
            os.environ.get("BIDS_ROOT", str(home / "bids"))
        ).expanduser()
        return cls(
            database_url=database_url,
            bids_root=bids_root,
            neuroii_api_url=os.environ.get("NEUROII_API_URL") or None,
            neuroii_api_token=os.environ.get("NEUROII_API_TOKEN") or None,
        )


_config: Config | None = None


def get_config() -> Config:
    """Return the process-wide config, resolving it from the environment once."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Override the config (used by tests to point at a temp DB / BIDS root)."""
    global _config
    _config = config
