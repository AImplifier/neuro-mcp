"""Client for the neuroii clinician annotation/visualization web app.

Integration is greenfield: neuroii exists as a UI but has no API contract wired
yet. This module *defines* the REST contract neuro-mcp expects and provides a
thin httpx client against it. Until ``NEUROII_API_URL`` is configured, the tool
layer surfaces :data:`CONTRACT` so the neuroii team can build to a fixed target.
"""

from __future__ import annotations

from typing import Any

import httpx

# The proposed REST contract neuroii should implement. Documented here so it is
# discoverable through the tools (and versioned with this repo).
CONTRACT: dict[str, Any] = {
    "base_url_env": "NEUROII_API_URL",
    "auth": "Bearer token via NEUROII_API_TOKEN (optional)",
    "endpoints": {
        "push_recording": {
            "method": "POST",
            "path": "/api/v1/recordings",
            "body": {
                "recording_id": "int (neuro-mcp id)",
                "bids_path": "str",
                "modality": "str",
                "derivatives": "list[{kind, uri, params}]",
            },
            "returns": {"neuroii_recording_id": "str", "url": "str"},
        },
        "create_viz_session": {
            "method": "POST",
            "path": "/api/v1/viz-sessions",
            "body": {"recording_id": "int", "layout": "str (optional)"},
            "returns": {"session_url": "str", "expires_at": "iso8601"},
        },
        "pull_annotations": {
            "method": "GET",
            "path": "/api/v1/recordings/{recording_id}/annotations",
            "returns": {
                "annotations": "list[{author, onset, duration, label, channels, payload}]"
            },
        },
    },
}


class NeuroiiNotConfigured(RuntimeError):
    pass


def not_configured_response(action: str) -> dict[str, Any]:
    """Uniform payload returned when NEUROII_API_URL is unset (not an error)."""
    return {
        "status": "not_configured",
        "action": action,
        "message": (
            "neuroii is not connected. Set NEUROII_API_URL (and optionally "
            "NEUROII_API_TOKEN) to enable this tool. The expected API contract is "
            "included below so the neuroii app can implement it."
        ),
        "contract": CONTRACT,
    }


class NeuroiiClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout)

    def push_recording(self, payload: dict) -> dict:
        r = self._client.post("/api/v1/recordings", json=payload)
        r.raise_for_status()
        return r.json()

    def create_viz_session(self, payload: dict) -> dict:
        r = self._client.post("/api/v1/viz-sessions", json=payload)
        r.raise_for_status()
        return r.json()

    def pull_annotations(self, recording_id: int) -> dict:
        r = self._client.get(f"/api/v1/recordings/{recording_id}/annotations")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._client.close()
