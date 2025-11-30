import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

metadata = sa.MetaData(schema="public")

workspaces = sa.Table(
    "workspaces",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("user_id", UUID(as_uuid=True), nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
)

documents = sa.Table(
    "documents",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("public.workspaces.id"), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("source_type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("docai_full_text", sa.Text),
    sa.Column("docai_raw_r2_key", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
)

files = sa.Table(
    "files",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("public.documents.id"), nullable=False),
    sa.Column("r2_key", sa.Text, nullable=False),
    sa.Column("original_filename", sa.Text, nullable=False),
    sa.Column("mime_type", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("checksum", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)

parse_jobs = sa.Table(
    "parse_jobs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("public.documents.id"), nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("parser_type", sa.Text, nullable=False, server_default=sa.text("'gcp_docai'")),
    sa.Column("error_message", sa.Text),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

rag_documents = sa.Table(
    "rag_documents",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("public.documents.id"), nullable=False),
    sa.Column("rag_doc_id", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)

conversations = sa.Table(
    "conversations",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("public.workspaces.id"), nullable=False),
    sa.Column("user_id", UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
)

messages = sa.Table(
    "messages",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("public.conversations.id"), nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("metadata", sa.JSON),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)
