import base64
import hashlib
import hmac
import json
import os
import secrets
import time


class InvalidToken(ValueError):
    pass


class TokenService:
    def __init__(self, key: bytes | None = None, ttl_seconds: int = 3600):
        self.key = key if key is not None else secrets.token_bytes(32)
        self.ttl_seconds = ttl_seconds

    def issue(self, kind: str, data: dict) -> str:
        raw = json.dumps({"kind": kind, "expires": int(time.time()) + self.ttl_seconds,
                          "data": data}, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        signature = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + "." + signature

    def read(self, token: str, kind: str, student_id: str) -> dict:
        try:
            encoded, signature = token.rsplit(".", 1)
            expected = hmac.new(self.key, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidToken("토큰 서명이 올바르지 않습니다.")
            value = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if value['kind'] != kind or value['expires'] <= time.time():
                raise InvalidToken("토큰 종류가 다르거나 만료되었습니다.")
            if value['data']['student_id'] != student_id:
                raise InvalidToken("학생과 토큰이 일치하지 않습니다.")
            return value['data']
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, InvalidToken):
                raise
            raise InvalidToken("토큰 형식을 확인해주세요.") from exc


# Shared secret is needed across workers/restarts; no key is committed.
configured_key = os.getenv("TUTOR_TOKEN_SECRET")
if configured_key and len(configured_key.encode()) < 32:
    raise ValueError("TUTOR_TOKEN_SECRET must be at least 32 bytes")
tokens = TokenService(configured_key.encode() if configured_key else None)
