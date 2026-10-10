"""Lossless packaging of native HTML; the model and source facts never change."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path

FORMAT = "sudograph-packed-html/v1"
MARKER = "<script>\nconst SG_PACKED_HTML = "
TEMPLATE = Path(__file__).resolve().parents[1] / "app" / "packed.html"


def pack(html: str, *, language: str) -> str:
    if MARKER in html:
        raise ValueError("HTML is already packed")
    raw = html.encode("utf-8")
    payload = {
        "format": FORMAT,
        "encoding": "gzip-base64",
        "language": language,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "data": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii"),
    }
    template = TEMPLATE.read_text(encoding="utf-8")
    return template.replace("__LANGUAGE__", language).replace(
        "__PACKED_HTML__", json.dumps(payload, separators=(",", ":"))
    )


def unpack(html: str) -> str:
    """Auditors read plain and packed exports through the same native bundle."""
    if MARKER not in html:
        return html
    payload = json.JSONDecoder().raw_decode(html.split(MARKER, 1)[1])[0]
    if payload["format"] != FORMAT or payload["encoding"] != "gzip-base64":
        raise ValueError("unsupported packed HTML format")
    raw = gzip.decompress(base64.b64decode(payload["data"], validate=True))
    if len(raw) != payload["bytes"] or hashlib.sha256(raw).hexdigest() != payload["sha256"]:
        raise ValueError("packed HTML size/hash differs from its native content")
    text = raw.decode("utf-8")
    if MARKER in text:
        raise ValueError("nested packed HTML is not supported")
    return text
