"""In-memory session state for the EEG MCP server.

An EEG pipeline is inherently stateful: load -> filter -> epoch -> analyze, in
sequence. MCP tool calls are individually stateless, so we keep the working
objects (Raw, Epochs, ICA, ...) in a process-local registry keyed by a
``session_id`` the client passes between calls.

This is deliberately simple and single-process: it suits a local, single-user
server. If you later need multi-user or persistence, swap this out for a store
that checkpoints to ``.fif`` files on disk.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import mne


@dataclass
class Session:
    """Everything we hold for one analysis session."""

    session_id: str
    raw: mne.io.BaseRaw | None = None
    epochs: mne.BaseEpochs | None = None
    ica: mne.preprocessing.ICA | None = None
    events: Any = None  # np.ndarray (n_events, 3)
    event_id: dict[str, int] | None = None
    source_path: str | None = None
    # Source-imaging (ESI) state.
    subjects_dir: str | None = None
    subject: str = "fsaverage"
    trans: Any = None  # transform or "fsaverage"
    src: Any = None  # SourceSpaces
    bem: Any = None  # BEM solution
    forward: Any = None  # Forward
    noise_cov: Any = None  # Covariance
    inverse_operator: Any = None
    stc: Any = None  # SourceEstimate
    history: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def log(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.history.append(f"[{stamp}] {message}")


class SessionStore:
    """Thread-safe registry of active sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> Session:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = Session(session_id=session_id)
            return self._sessions[session_id]

    def get(self, session_id: str) -> Session:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(
                    f"No session '{session_id}'. Call load_neuro first to create one."
                )
            return self._sessions[session_id]

    def require_raw(self, session_id: str) -> tuple[Session, mne.io.BaseRaw]:
        session = self.get(session_id)
        if session.raw is None:
            raise ValueError(
                f"Session '{session_id}' has no loaded recording. Call load_neuro first."
            )
        return session, session.raw

    def require_epochs(self, session_id: str) -> tuple[Session, mne.BaseEpochs]:
        session = self.get(session_id)
        if session.epochs is None:
            raise ValueError(
                f"Session '{session_id}' has no epochs. Call epoch_neuro first."
            )
        return session, session.epochs

    def drop(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions)

    def summary(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        raw = session.raw
        return {
            "session_id": session_id,
            "source_path": session.source_path,
            "has_raw": raw is not None,
            "has_epochs": session.epochs is not None,
            "has_ica": session.ica is not None,
            "n_channels": len(raw.ch_names) if raw is not None else 0,
            "sfreq": float(raw.info["sfreq"]) if raw is not None else None,
            "duration_sec": float(raw.times[-1]) if raw is not None else None,
            "n_epochs": len(session.epochs) if session.epochs is not None else 0,
            "created_at": session.created_at.isoformat(),
            "history": session.history,
        }


# Single shared store for the running server process.
store = SessionStore()
