"""
utils/file_utils.py — Leitura, codificação e salvamento de arquivos.

Usa base64 para serializar arquivos binários dentro de um Message.content,
possibilitando envio tanto por fila de threads quanto por socket TCP.
"""
import base64
import os
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def read_as_b64(path: str) -> str:
    """Lê o arquivo e retorna o conteúdo codificado em base64."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def b64_to_bytes(b64: str) -> bytes:
    return base64.b64decode(b64)


def save_from_b64(b64: str, filename: str, dest_dir: str = ".") -> str:
    """Decodifica base64 e salva o arquivo em dest_dir. Retorna o caminho."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    with open(dest, "wb") as f:
        f.write(base64.b64decode(b64))
    return dest


def file_info(path: str) -> dict:
    p = Path(path)
    size = p.stat().st_size
    if size >= 1024 * 1024:
        size_str = f"{size / (1024*1024):.1f} MB"
    elif size >= 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size} B"
    return {"name": p.name, "size": size, "size_str": size_str, "ext": p.suffix.lower()}
