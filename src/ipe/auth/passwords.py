"""Senhas: PBKDF2-SHA256 com sal aleatório (só a biblioteca padrão)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ITERATIONS = 200_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, dk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str:
    """"" se a senha serve; senão o motivo."""
    if len(password) < 6:
        return "A senha precisa ter pelo menos 6 caracteres."
    return ""
