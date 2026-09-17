"""company unique identity on (normalized_name, ownership)

Prevents the company resolver from ever facing two identical
normalized_name+ownership rows and compounding ambiguity by creating a
third.

Revision ID: 0005_company_unique_identity
Revises: 0004_url_candidates
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_company_unique_identity"
down_revision = "0004_url_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes("companies")}
    if "ix_companies_identity" in existing:
        op.drop_index("ix_companies_identity", table_name="companies")
    op.create_index(
        "ix_companies_identity",
        "companies",
        ["normalized_name", "ownership"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_companies_identity", table_name="companies")
    op.create_index("ix_companies_identity", "companies", ["normalized_name", "ownership"])
