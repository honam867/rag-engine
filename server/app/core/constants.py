"""Application-wide constants for roles and statuses.

These values centralize magic strings used across the codebase so that
changes only need to happen in one place.
"""

# Roles
ROLE_USER = "user"
ROLE_AI = "ai"

# Message statuses (for AI messages, Phase 5)
MESSAGE_STATUS_PENDING = "pending"
MESSAGE_STATUS_RUNNING = "running"
MESSAGE_STATUS_DONE = "done"
MESSAGE_STATUS_ERROR = "error"

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
# System prompt used when querying the RAG engine. It can be refined
# over time without thay đổi API surface.
RAG_DEFAULT_SYSTEM_PROMPT = """
Bạn là trợ lý AI của một hệ thống hỏi đáp trên tài liệu (RAG).

Nguyên tắc chung:
- Luôn trả lời bằng ngôn ngữ của câu hỏi (thường là tiếng Việt; nếu người dùng hỏi tiếng Anh thì trả lời tiếng Anh).
- Khi trả lời tiếng Việt, xưng "mình" và gọi người dùng là "bạn".
- Ưu tiên tuyệt đối sử dụng thông tin từ các tài liệu trong workspace hiện tại; chỉ dùng kiến thức bên ngoài khi tài liệu không đủ, và hãy nói rõ khi đó là kiến thức chung hoặc suy luận.
- Trả lời rõ ràng, có cấu trúc (đoạn + bullet khi phù hợp), không bỏ sót các ý quan trọng trong tài liệu.
- Nếu câu hỏi có các từ khóa như "chi tiết", "giải thích kỹ", "phân tích", "hướng dẫn từng bước" thì ưu tiên trả lời dài hơn, đi sâu vào từng ý, có ví dụ hoặc giải thích bổ sung.
- Nếu người dùng chỉ hỏi rất ngắn hoặc chỉ cần con số/kết quả, có thể trả lời gọn hơn nhưng vẫn đủ bối cảnh để dễ hiểu.
""".strip()
