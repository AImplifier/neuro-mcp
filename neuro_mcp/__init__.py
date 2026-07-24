"""neuro-mcp: an MCP for NeuroAgents that assist clinicians and researchers.

Composes MNE processing + source imaging, a Postgres/BIDS data & EHR store,
and NeuroII web visualization — over MCP.
"""

from .app import mcp

__version__ = "0.1.1"
__all__ = ["mcp"]
