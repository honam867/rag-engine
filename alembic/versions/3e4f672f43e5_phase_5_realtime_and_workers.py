"""Phase 5 – realtime & worker columns

Revision ID: 3e4f672f43e5
Revises: 4612949e1adb
Create Date: 2025-12-03 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3e4f672f43e5"
down_revision: Union[str, Sequence[str], None] = "4612949e1adb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 5.

    - Add retry_count column to parse_jobs.
    - Add status column to messages.

    We use IF NOT EXISTS so this migration is idempotent in case the
    columns were added manually on Supabase beforehand.
    """
    op.execute(
        """
        ALTER TABLE public.parse_jobs
        ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
        """
    )
    op.execute(
        """
        ALTER TABLE public.messages
        ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'done';
        """
    )


def downgrade() -> None:
    """Downgrade schema for Phase 5."""
    op.execute(
        """
        ALTER TABLE public.messages
        DROP COLUMN IF EXISTS status;
        """
    )
    op.execute(
        """
        ALTER TABLE public.parse_jobs
        DROP COLUMN IF EXISTS retry_count;
        """
    )

