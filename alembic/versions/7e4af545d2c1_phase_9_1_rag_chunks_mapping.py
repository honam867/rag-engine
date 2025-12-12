"""Phase 9.1 – rag_chunks_mapping table

Revision ID: 7e4af545d2c1
Revises: 3e4f672f43e5
Create Date: 2025-12-07 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7e4af545d2c1"
down_revision: Union[str, Sequence[str], None] = "3e4f672f43e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create rag_chunks_mapping table if it does not exist.

    This keeps application models and the Supabase schema in sync for
    Phase 9.1 source attribution v2.
    """
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.rag_chunks_mapping (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
            chunk_id text NOT NULL,
            document_id uuid NOT NULL REFERENCES public.documents(id),
            page_start integer NOT NULL,
            page_end integer NOT NULL,
            segment_start_index integer,
            segment_end_index integer,
            char_start integer,
            char_end integer,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_rag_chunks_mapping_workspace_chunk
                UNIQUE (workspace_id, chunk_id)
        );
        """
    )


def downgrade() -> None:
    """Drop rag_chunks_mapping table (if exists)."""
    op.execute(
        """
        DROP TABLE IF EXISTS public.rag_chunks_mapping;
        """
    )

