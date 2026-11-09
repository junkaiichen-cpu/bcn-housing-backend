import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)
TOKEN_TTL_SECONDS = 8 * 60 * 60


def _token_secret() -> bytes:
    secret = os.getenv("ADMIN_TOKEN_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator authentication is not configured",
        )
    return secret.encode("utf-8")


def create_admin_token(username: str) -> str:
    payload = json.dumps(
        {"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(_token_secret(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode('ascii')}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Administrator authentication required")
    try:
        encoded_text, signature_text = credentials.credentials.split(".", 1)
        encoded = encoded_text.encode("ascii")
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        expected = hmac.new(_token_secret(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid token signature")
        payload_bytes = base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
        payload = json.loads(payload_bytes)
        if not isinstance(payload.get("sub"), str) or payload.get("exp", 0) < int(time.time()):
            raise ValueError("Expired token")
        return payload["sub"]
    except HTTPException:
        raise
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired administrator token")


def authenticate_admin(username: str, password: str) -> bool:
    expected_username = os.getenv("ADMIN_USERNAME", "")
    expected_password = os.getenv("ADMIN_PASSWORD", "")
    if not expected_username or len(expected_password) < 12:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator credentials are not securely configured",
        )
    return hmac.compare_digest(username.encode(), expected_username.encode()) and hmac.compare_digest(
        password.encode(), expected_password.encode()
    )
