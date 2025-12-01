"""Application-wide constants for roles and statuses.

These values centralize magic strings used across the codebase so that
changes only need to happen in one place.
"""

# Roles
ROLE_USER = "user"
ROLE_AI = "ai"

# Document statuses
DOCUMENT_STATUS_PENDING = "pending"
DOCUMENT_STATUS_PARSED = "parsed"
DOCUMENT_STATUS_INGESTED = "ingested"
DOCUMENT_STATUS_ERROR = "error"

# Parse job statuses
PARSE_JOB_STATUS_QUEUED = "queued"
PARSE_JOB_STATUS_RUNNING = "running"
PARSE_JOB_STATUS_SUCCESS = "success"
PARSE_JOB_STATUS_FAILED = "failed"

# Parser types
PARSER_TYPE_GCP_DOCAI = "gcp_docai"

