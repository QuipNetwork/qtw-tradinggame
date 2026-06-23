"""Per-agent capability-token auth.

Each agent gets a high-entropy token at creation, returned exactly once and stored
only as a SHA-256 hash. Owner-scoped routes require `Authorization: Bearer <token>`
matching that agent — the QR link the attendee scans carries the token in its URL
fragment. See docs/superpowers/specs/2026-06-22-security-hardening-design.md.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import Header, HTTPException

from ..persistence.agents import AgentRecord, get_agent_store


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_agent_token() -> tuple[str, str]:
    """Return (plaintext token, sha256 hex). Persist only the hash; return the token once."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an `Authorization: Bearer <token>` header, or None."""
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def token_matches(token: str | None, token_hash: str | None) -> bool:
    """Constant-time check that `token` hashes to `token_hash`. False if either is unset."""
    if not token or not token_hash:
        return False
    return secrets.compare_digest(hash_token(token), token_hash)


def require_agent_token(
    agent_id: str, authorization: str | None = Header(default=None)
) -> AgentRecord:
    """FastAPI dependency: authorize the caller as the owner of `agent_id`.

    404 if no such agent, 401 if the bearer token is missing/malformed, 403 if it
    doesn't match. Returns the record so handlers can reuse it.
    """
    record = get_agent_store().get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail="agent not found")
    token = bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="missing bearer token")
    if not token_matches(token, record.token_hash):
        raise HTTPException(status_code=403, detail="invalid token")
    return record
