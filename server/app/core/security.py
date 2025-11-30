from typing import Optional
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Request, status

from .config import get_settings


@dataclass
class CurrentUser:
    id: str
    email: Optional[str] = None


def decode_token(token: str) -> CurrentUser:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.auth.jwt_secret, algorithms=["HS256"], options={"verify_aud": False, "leeway": 60})
    except jwt.PyJWTError as exc:  # type: ignore[attr-defined]
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(exc)}") from exc

    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return CurrentUser(id=str(user_id), email=email)


def get_current_user(request: Request) -> CurrentUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    token = auth_header.split(" ", 1)[1]
    return decode_token(token)
