"""Versioned transport-neutral JARVIS protocol.

Windows stdio/TCP and Android use the same JSON envelope. Transport is the
only platform-specific layer.
"""
from __future__ import annotations
PROTOCOL_VERSION = 1

def request(req_id, kind: str, **payload) -> dict:
    return {"protocol": PROTOCOL_VERSION, "id": req_id, "type": kind, **payload}

def response(req_id, kind: str, **payload) -> dict:
    return {"protocol": PROTOCOL_VERSION, "id": req_id, "type": kind, **payload}

def event(kind: str, **payload) -> dict:
    return {"protocol": PROTOCOL_VERSION, "id": None, "type": kind, **payload}

def validate(message: dict) -> None:
    if not isinstance(message, dict):
        raise ValueError("Protocol message must be an object")
    version = message.get("protocol", PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ValueError(f"Unsupported JARVIS protocol version: {version}")
    if "type" not in message:
        raise ValueError("Protocol message has no type")
