import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

def _secret() -> str:
    s = os.environ.get("SGRS_JWT_SECRET")
    if s:
        return s
    if os.environ.get("SGRS_ENV") == "production":  # nunca el valor de desarrollo en producción
        from .db import secret_fallback
        return secret_fallback()
    return "dev-only-change-me"


SECRET = _secret()
TOKEN_TTL = int(os.environ.get("SGRS_TOKEN_TTL", "28800"))  # 8 h; refresh token pendiente
_bearer = HTTPBearer()
_bearer_opt = HTTPBearer(auto_error=False)


def issue_token(user_id: UUID, role: str, ttl: int = TOKEN_TTL) -> str:
    import time
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + ttl},
                      SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        p = jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "TOKEN_INVALID") from None
    return {"id": UUID(p["sub"]), "role": p["role"]}


def optional_user(cred: HTTPAuthorizationCredentials = Depends(_bearer_opt)):
    """Usuario si envía un token válido; None si es anónimo."""
    if cred is None:
        return None
    return current_user(cred)
