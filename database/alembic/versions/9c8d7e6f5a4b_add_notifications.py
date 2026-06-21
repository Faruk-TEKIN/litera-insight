"""add notifications

Revision ID: 9c8d7e6f5a4b
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9c8d7e6f5a4b"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("related_snapshot_key", sa.String(length=200), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "type", "related_snapshot_key", name="uq_notifications_user_type_snapshot"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_notifications_related_snapshot_key"),
        "notifications",
        ["related_snapshot_key"],
        unique=False,
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("external_message_id", sa.String(length=120), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_notification_delivery_channel"),
    )
    op.create_index(
        op.f("ix_notification_deliveries_notification_id"),
        "notification_deliveries",
        ["notification_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_deliveries_status_next_attempt",
        "notification_deliveries",
        ["status", "next_attempt_at"],
        unique=False,
    )

    op.create_table(
        "user_telegram_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=80), nullable=False),
        sa.Column("telegram_user_id", sa.String(length=80), nullable=True),
        sa.Column("telegram_username", sa.String(length=120), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_chat_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_telegram_accounts_user_id"), "user_telegram_accounts", ["user_id"], unique=True)

    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_telegram_link_tokens_user_id"), "telegram_link_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_telegram_link_tokens_user_id"), table_name="telegram_link_tokens")
    op.drop_table("telegram_link_tokens")
    op.drop_index(op.f("ix_user_telegram_accounts_user_id"), table_name="user_telegram_accounts")
    op.drop_table("user_telegram_accounts")
    op.drop_index("ix_notification_deliveries_status_next_attempt", table_name="notification_deliveries")
    op.drop_index(op.f("ix_notification_deliveries_notification_id"), table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
    op.drop_index(op.f("ix_notifications_related_snapshot_key"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")
