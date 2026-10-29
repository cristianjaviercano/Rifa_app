import os
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET = os.environ.get("SGRS_JWT_SECRET", "dev-only-change-me")
_bearer = HTTPBearer()


def issue_token(user_id: UUID, role: str, ttl: int = 900) -> str:
    import time
    now = int(time.time())
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + ttl},
                      SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    try:
        p = jwt.decode(cred.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "TOKEN_INVALID")
    return {"id": UUID(p["sub"]), "role": p["role"]}
