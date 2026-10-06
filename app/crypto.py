import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import settings


def _fernet():
    raw = settings.master_key
    if not raw:
        raise RuntimeError('MASTER_KEY precisa estar configurado. Execute o instalador para gerar uma chave segura.')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ''


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode() if value else ''
