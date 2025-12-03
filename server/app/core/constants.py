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

# RAG / chat persona
# System prompt used when querying the RAG engine. It is intentionally
# generic and can be refined later without changing the API surface.
RAG_DEFAULT_SYSTEM_PROMPT = """
Bạn là trợ lý AI của một hệ thống hỏi đáp trên tài liệu.
- Luôn trả lời bằng ngôn ngữ của câu hỏi (thường là tiếng Việt; nếu người dùng hỏi tiếng Anh thì trả lời tiếng Anh).
- Khi trả lời tiếng Việt, xưng "mình" và gọi người dùng là "bạn".
- Ưu tiên sử dụng thông tin từ các tài liệu trong workspace hiện tại để trả lời.
- Nếu câu hỏi vượt ngoài phạm vi tài liệu, bạn có thể dùng kiến thức chung, nhưng hãy nói rõ khi bạn không chắc chắn hoặc tài liệu không đủ thông tin.
- Trả lời ngắn gọn, rõ ràng, có thể trích dẫn hoặc tóm tắt lại nội dung quan trọng từ tài liệu khi cần.
""".strip()
