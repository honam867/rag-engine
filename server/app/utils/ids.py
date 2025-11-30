import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
