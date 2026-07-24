"""Database engine, session management, and clinical CRUD helpers.

Centralizes the versioning + audit discipline so the tool layer stays thin:
amendments go through :func:`amend_versioned`, soft-voids through
:func:`void_versioned`, and every mutation records an :class:`AuditLog` row.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_config
from .models import (
    STATUS_ACTIVE,
    STATUS_AMENDED,
    STATUS_VOID,
    AuditLog,
    Base,
)

_engine = None
_Session: sessionmaker | None = None


def init_db() -> None:
    """Create the engine (if needed) and ensure all tables exist."""
    global _engine, _Session
    if _engine is None:
        cfg = get_config()
        # For the default SQLite file, make sure the parent directory exists.
        if cfg.database_url.startswith("sqlite:///"):
            path = cfg.database_url.replace("sqlite:///", "", 1)
            if path and path != ":memory:":
                import os

                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        connect_args = {}
        if cfg.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(cfg.database_url, connect_args=connect_args, future=True)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(_engine)


def reset_engine() -> None:
    """Drop cached engine/session so a new config takes effect (used by tests)."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


@contextmanager
def get_session() -> Iterator[Session]:
    """Provide a transactional session scope."""
    if _Session is None:
        init_db()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def to_dict(obj: Any) -> dict:
    """Serialize an ORM row to a JSON-safe dict (columns only)."""
    if obj is None:
        return {}
    out: dict[str, Any] = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        out[col.name] = val
    return out


def new_logical_id() -> str:
    return uuid.uuid4().hex[:16]


def record_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    target_table: str,
    target_id: int,
    before: dict | None,
    after: dict | None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            target_table=target_table,
            target_id=target_id,
            before=before,
            after=after,
        )
    )


def current_version(session: Session, model, logical_id: str):
    """Return the highest-version, non-voided row for a logical id (or None)."""
    stmt = (
        select(model)
        .where(model.logical_id == logical_id)
        .order_by(model.version.desc())
    )
    for row in session.scalars(stmt):
        if row.status != STATUS_VOID:
            return row
    return None


def amend_versioned(
    session: Session,
    model,
    logical_id: str,
    *,
    actor: str,
    changes: dict,
    note: str | None,
    copy_fields: list[str],
    table_name: str,
):
    """Create a new version of a versioned record with ``changes`` applied.

    The prior current row is marked ``amended``; the new row is ``active`` and
    points back via ``supersedes_id``. Returns the new row.
    """
    prior = current_version(session, model, logical_id)
    if prior is None:
        raise ValueError(f"No active record with logical_id '{logical_id}'.")
    before = to_dict(prior)

    kwargs = {f: getattr(prior, f) for f in copy_fields}
    kwargs.update(changes)
    kwargs.update(
        {
            "logical_id": logical_id,
            "version": prior.version + 1,
            "supersedes_id": prior.id,
            "status": STATUS_ACTIVE,
            "author": actor,
            "note": note,
        }
    )
    new_row = model(**kwargs)
    prior.status = STATUS_AMENDED
    session.add(new_row)
    session.flush()  # assign new_row.id
    record_audit(
        session,
        actor=actor,
        action="amend",
        target_table=table_name,
        target_id=new_row.id,
        before=before,
        after=to_dict(new_row),
    )
    return new_row


def void_versioned(
    session: Session,
    model,
    logical_id: str,
    *,
    actor: str,
    note: str | None,
    table_name: str,
):
    """Soft-void the current version (status -> entered-in-error). Kept, not deleted."""
    prior = current_version(session, model, logical_id)
    if prior is None:
        raise ValueError(f"No active record with logical_id '{logical_id}'.")
    before = to_dict(prior)
    prior.status = STATUS_VOID
    prior.note = note
    session.flush()
    record_audit(
        session,
        actor=actor,
        action="void",
        target_table=table_name,
        target_id=prior.id,
        before=before,
        after=to_dict(prior),
    )
    return prior


def history(session: Session, model, logical_id: str) -> list[dict]:
    """Return all versions of a logical record, oldest first."""
    stmt = (
        select(model)
        .where(model.logical_id == logical_id)
        .order_by(model.version.asc())
    )
    return [to_dict(r) for r in session.scalars(stmt)]
