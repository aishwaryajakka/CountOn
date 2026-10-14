"""Extend audit history with linked, filterable governance fields.

Revision ID: d6a71c9e24f0
Revises: c592d04e8f41
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6a71c9e24f0"
down_revision: str | Sequence[str] | None = "c592d04e8f41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name, type_, default in (
        ("event_type", sa.String(50), "OPERATION_RECORDED"),
        ("actor_type", sa.String(10), "SYSTEM"),
    ):
        op.add_column(
            "audit_events",
            sa.Column(name, type_, nullable=False, server_default=default),
        )
    for name, type_ in (
        ("source_provider", sa.String(30)),
        ("source_type", sa.String(40)),
        ("source_provenance", sa.String(40)),
        ("source_reference", sa.String(80)),
        ("evidence_id", sa.UUID()),
        ("evaluation_id", sa.UUID()),
        ("result_status", sa.String(10)),
        ("idempotency_key", sa.String(128)),
    ):
        op.add_column("audit_events", sa.Column(name, type_))
    op.create_foreign_key(
        "fk_audit_evidence",
        "audit_events",
        "evidence",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_audit_evaluation",
        "audit_events",
        "evaluations",
        ["evaluation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_audit_actor_type",
        "audit_events",
        "actor_type IN ('USER','SYSTEM','PROVIDER')",
    )
    op.create_check_constraint(
        "ck_audit_result_status",
        "audit_events",
        "result_status IS NULL OR result_status IN ('MATCH','UNKNOWN','MISMATCH')",
    )
    op.create_unique_constraint(
        "uq_audit_owner_idempotency",
        "audit_events",
        ["user_id", "idempotency_key"],
    )
    op.create_index("ix_audit_events_evidence_id", "audit_events", ["evidence_id"])
    op.create_index("ix_audit_events_evaluation_id", "audit_events", ["evaluation_id"])
    op.create_index(
        "ix_audit_owner_source_created",
        "audit_events",
        ["user_id", "source_provider", "created_at"],
    )
    op.create_index(
        "ix_audit_owner_result_created",
        "audit_events",
        ["user_id", "result_status", "created_at"],
    )
    op.execute(
        """
        UPDATE audit_events SET event_type = CASE action
          WHEN 'expectation.created' THEN 'EXPECTATION_CREATED'
          WHEN 'expectation.evaluated' THEN 'EVALUATION_COMPLETED'
          WHEN 'evidence.ingested' THEN 'EVIDENCE_INGESTED'
          WHEN 'notification.created' THEN 'NOTIFICATION_CREATED'
          WHEN 'provider.authorized' THEN 'SOURCE_AUTHORIZED'
          WHEN 'provider.disconnected' THEN 'SOURCE_DISCONNECTED'
          ELSE 'OPERATION_RECORDED'
        END
        """
    )


def downgrade() -> None:
    op.drop_index("ix_audit_owner_result_created", table_name="audit_events")
    op.drop_index("ix_audit_owner_source_created", table_name="audit_events")
    op.drop_index("ix_audit_events_evaluation_id", table_name="audit_events")
    op.drop_index("ix_audit_events_evidence_id", table_name="audit_events")
    op.drop_constraint("uq_audit_owner_idempotency", "audit_events", type_="unique")
    op.drop_constraint("ck_audit_result_status", "audit_events", type_="check")
    op.drop_constraint("ck_audit_actor_type", "audit_events", type_="check")
    op.drop_constraint("fk_audit_evaluation", "audit_events", type_="foreignkey")
    op.drop_constraint("fk_audit_evidence", "audit_events", type_="foreignkey")
    for name in (
        "idempotency_key",
        "result_status",
        "evaluation_id",
        "evidence_id",
        "source_reference",
        "source_provenance",
        "source_type",
        "source_provider",
        "actor_type",
        "event_type",
    ):
        op.drop_column("audit_events", name)
