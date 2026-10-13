"""Revocable local Bee bridge authorization and consent-gated evidence import."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.exceptions import (
    AuthenticationError,
    InvalidExpectationError,
    ResourceNotFoundError,
)
from app.db.models import (
    BeeCliCredential,
    BeeCliPairing,
    BeeExpectationBinding,
    BeeImportCandidate,
    Evidence,
)
from app.db.models.integration import IntegrationConnection
from app.repositories import audit
from app.schemas.evidence import EvidenceCreate
from app.services import evaluation_service, evidence_service
from app.services.expectation_service import get_expectation

PAIR_TTL = timedelta(minutes=10)
TOKEN_TTL = timedelta(days=90)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_pairing(db, user_id):
    now = datetime.now(timezone.utc)
    code = secrets.token_urlsafe(32)
    db.add(BeeCliPairing(user_id=user_id, code_digest=_digest(code), expires_at=now + PAIR_TTL))
    audit.record(db, user_id, "integration", user_id, "bee_cli.pairing_created")
    db.commit()
    return code, now + PAIR_TTL


def pair(db, payload):
    now = datetime.now(timezone.utc)
    code = payload.pairing_code.get_secret_value()
    pairing = db.scalar(
        select(BeeCliPairing)
        .where(
            BeeCliPairing.code_digest == _digest(code),
            BeeCliPairing.used_at.is_(None),
            BeeCliPairing.expires_at > now,
        )
        .with_for_update()
    )
    if pairing is None:
        raise ResourceNotFoundError("BEE_PAIRING_INVALID", "Pairing code is invalid or expired")
    account_digest = _digest(payload.bee_account_ref)
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == pairing.user_id,
            IntegrationConnection.provider == "bee",
            IntegrationConnection.connection_type == "wearable",
            IntegrationConnection.connection_metadata["demo"].astext != "true",
        )
    )
    if connection is None:
        connection = IntegrationConnection(
            user_id=pairing.user_id,
            provider="bee",
            connection_type="wearable",
            external_account_id=account_digest,
            display_name="Bee CLI (local)",
            status="connected",
            scopes=["changes:read", "evidence:stage"],
            connection_metadata={"connector": "official_cli", "demo": False},
            connected_at=now,
        )
        db.add(connection)
        db.flush()
    else:
        connection.external_account_id = account_digest
        connection.status = "connected"
        connection.scopes = ["changes:read", "evidence:stage"]
        connection.connected_at, connection.revoked_at, connection.failure_status = now, None, None
    existing = db.scalar(
        select(BeeCliCredential).where(BeeCliCredential.connection_id == connection.id).with_for_update()
    )
    token = secrets.token_urlsafe(48)
    if existing is None:
        existing = BeeCliCredential(connection_id=connection.id, user_id=pairing.user_id, token_digest=_digest(token), cli_version=payload.cli_version, expires_at=now + TOKEN_TTL)
        db.add(existing)
    else:
        existing.token_digest = _digest(token)
        existing.cli_version = payload.cli_version
        existing.expires_at = now + TOKEN_TTL
        existing.revoked_at = None
        existing.last_error = None
    pairing.used_at = now
    audit.record(
        db, pairing.user_id, "integration", connection.id, "provider.authorized",
        actor_type="USER", source_provider="BEE", source_type="BEE_CLI",
        source_provenance="LIVE_BEE_CLI", source_reference=account_digest,
        idempotency_key=f"SOURCE_AUTHORIZED:{connection.id}:{pairing.id}",
    )
    db.commit()
    return token, connection.id, existing.expires_at


def authenticate_connector(db, token: str):
    now = datetime.now(timezone.utc)
    credential = db.scalar(
        select(BeeCliCredential).where(
            BeeCliCredential.token_digest == _digest(token),
            BeeCliCredential.revoked_at.is_(None),
            BeeCliCredential.expires_at > now,
        )
    )
    if credential is None:
        raise AuthenticationError()
    credential.last_seen_at = now
    return credential


def stage(db, credential, payload):
    now = datetime.now(timezone.utc)
    accepted = 0
    for candidate in payload.candidates:
        row = db.scalar(select(BeeImportCandidate).where(BeeImportCandidate.connection_id == credential.connection_id, BeeImportCandidate.external_id == candidate.external_id))
        values = {
            "version": candidate.version,
            "category": candidate.category,
            "summary": candidate.summary,
            "fact": {"completed": candidate.completed} if candidate.completed is not None else {},
            "observed_at": candidate.observed_at,
            "confidence": candidate.confidence,
        }
        if row is None:
            row = BeeImportCandidate(connection_id=credential.connection_id, user_id=credential.user_id, external_id=candidate.external_id, **values)
            db.add(row)
            accepted += 1
        elif row.status == "pending" and row.version != candidate.version:
            for key, value in values.items():
                setattr(row, key, value)
            accepted += 1
    credential.checkpoint = payload.next_cursor or credential.checkpoint
    credential.last_sync_at = now
    credential.last_error = None
    connection = db.get(IntegrationConnection, credential.connection_id)
    if connection:
        connection.last_synced_at = now
        connection.failure_status = None
    db.commit()
    return {"accepted": accepted, "checkpoint": credential.checkpoint}


def status(db, user_id):
    connection = db.scalar(select(IntegrationConnection).where(IntegrationConnection.user_id == user_id, IntegrationConnection.provider == "bee", IntegrationConnection.connection_type == "wearable", IntegrationConnection.connection_metadata["demo"].astext != "true").order_by(IntegrationConnection.created_at.desc()))
    if connection is None:
        return {"simulator_available": True, "state": "not_paired", "pending_candidates": 0}
    credential = db.scalar(select(BeeCliCredential).where(BeeCliCredential.connection_id == connection.id, BeeCliCredential.user_id == user_id))
    pending = db.scalar(select(func.count()).select_from(BeeImportCandidate).where(BeeImportCandidate.connection_id == connection.id, BeeImportCandidate.user_id == user_id, BeeImportCandidate.status == "pending")) or 0
    if connection.status == "disconnected" or credential is None or credential.revoked_at:
        state = "disconnected"
    elif credential.last_error:
        state = "error"
    elif pending:
        state = "import_enabled"
    else:
        state = "paired"
    return {"simulator_available": True, "state": state, "connection_id": connection.id, "cli_version": credential.cli_version if credential else None, "last_sync_at": credential.last_sync_at if credential else None, "last_error": credential.last_error if credential else None, "pending_candidates": pending}


def candidates(db, user_id):
    return list(db.scalars(select(BeeImportCandidate).where(BeeImportCandidate.user_id == user_id, BeeImportCandidate.status == "pending").order_by(BeeImportCandidate.observed_at.desc()).limit(100)))


def import_candidates(db, user_id, payload):
    expectation = get_expectation(db, payload.expectation_id, user_id)
    rows = list(db.scalars(select(BeeImportCandidate).where(BeeImportCandidate.id.in_(payload.candidate_ids), BeeImportCandidate.user_id == user_id, BeeImportCandidate.status == "pending").with_for_update()))
    if len(rows) != len(set(payload.candidate_ids)):
        raise ResourceNotFoundError("BEE_CANDIDATE_NOT_FOUND", "One or more Bee records are unavailable")
    connection_ids = {row.connection_id for row in rows}
    if len(connection_ids) != 1:
        raise InvalidExpectationError("Select records from one Bee connection")
    connection_id = connection_ids.pop()
    connection = db.scalar(select(IntegrationConnection).where(IntegrationConnection.id == connection_id, IntegrationConnection.user_id == user_id, IntegrationConnection.status == "connected"))
    credential = db.scalar(select(BeeCliCredential).where(BeeCliCredential.connection_id == connection_id, BeeCliCredential.user_id == user_id, BeeCliCredential.revoked_at.is_(None)))
    if connection is None or credential is None:
        raise ResourceNotFoundError("BEE_CONNECTION_UNAVAILABLE", "Bee CLI is disconnected")
    binding = db.scalar(select(BeeExpectationBinding).where(BeeExpectationBinding.connection_id == connection_id, BeeExpectationBinding.expectation_id == expectation.id))
    if binding is None:
        binding = BeeExpectationBinding(connection_id=connection_id, expectation_id=expectation.id, user_id=user_id)
        db.add(binding)
        db.flush()
    if "bee" not in expectation.evidence_sources:
        expectation.evidence_sources = list(dict.fromkeys([*expectation.evidence_sources, "bee"]))
    imported = duplicate = 0
    evaluation_ids = []
    now = datetime.now(timezone.utc)
    for row in rows:
        completed = row.fact.get("completed")
        supports_outcome = row.category == "todo" and completed is True
        evidence_payload = EvidenceCreate(
            external_event_id=f"bee:{row.external_id}:{row.version}",
            source="bee",
            metric=expectation.metric if supports_outcome else "bee_context",
            value={"value": True, "category": row.category, "summary": row.summary} if supports_outcome else {"category": row.category, "summary": row.summary, "context_only": True},
            observed_at=row.observed_at,
            confidence=row.confidence,
            raw_data={"provenance": "LIVE_BEE_CLI", "connection_id": str(connection_id), "provider_record_ref": row.external_id, "category": row.category},
        )
        before = db.scalar(select(Evidence.id).where(Evidence.expectation_id == expectation.id, Evidence.source == "bee", Evidence.external_event_id == evidence_payload.external_event_id))
        evidence_service.add_evidence(db, expectation.id, evidence_payload, user_id, commit=False)
        imported += int(before is None)
        duplicate += int(before is not None)
        row.status, row.imported_at = "imported", now
        evaluation = evaluation_service.evaluate_expectation(db, expectation.id, user_id, idempotency_key=f"bee-import:{row.id}:{row.version}", commit=False)
        evaluation_ids.append(evaluation.id)
    audit.record(db, user_id, "expectation", expectation.id, "bee_cli.evidence_imported", metadata={"count": imported, "connection_id": str(connection_id)})
    db.commit()
    return {"imported": imported, "duplicate": duplicate, "evaluation_ids": evaluation_ids, "binding_id": binding.id}


def disconnect(db, user_id):
    now = datetime.now(timezone.utc)
    credentials = list(db.scalars(select(BeeCliCredential).where(BeeCliCredential.user_id == user_id, BeeCliCredential.revoked_at.is_(None)).with_for_update()))
    for credential in credentials:
        credential.revoked_at = now
        connection = db.get(IntegrationConnection, credential.connection_id)
        if connection:
            connection.status, connection.scopes = "disconnected", []
            connection.revoked_at, connection.failure_status = now, None
            audit.record(
                db, user_id, "integration", connection.id, "provider.disconnected",
                actor_type="USER", source_provider="BEE", source_type="BEE_CLI",
                source_provenance="LIVE_BEE_CLI",
                source_reference=connection.external_account_id,
                idempotency_key=f"SOURCE_DISCONNECTED:{connection.id}:{now.isoformat()}",
            )
    db.commit()
    return {"disconnected": True, "local_action": "Run bee logout separately if you also want to revoke the Bee CLI's local Bee session."}
