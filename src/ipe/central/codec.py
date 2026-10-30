"""JSON com tipos que o banco devolve: datas, bytes, tuplas, conjuntos e as linhas (dataclasses)."""

from __future__ import annotations

import base64
import dataclasses
import json
from datetime import date, datetime


def _classes() -> dict:
    from ipe.db import repository as R
    return {c.__name__: c for c in (R.StudyRow, R.SeriesRow)}


def encode(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {"__dc__": type(obj).__name__, "f": {f.name: encode(getattr(obj, f.name))
                                                    for f in dataclasses.fields(obj)}}
    if isinstance(obj, datetime):
        return {"__dt__": obj.isoformat()}
    if isinstance(obj, date):
        return {"__d__": obj.isoformat()}
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return {"__b__": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, tuple):
        return {"__t__": [encode(v) for v in obj]}
    if isinstance(obj, (set, frozenset)):
        return {"__s__": [encode(v) for v in obj]}
    if isinstance(obj, dict):
        return {"__m__": [[encode(k), encode(v)] for k, v in obj.items()]} \
            if any(not isinstance(k, str) for k in obj) else {k: encode(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [encode(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):          # números numpy
        return obj.item()
    return obj


def decode(obj):
    if isinstance(obj, list):
        return [decode(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    if "__dc__" in obj:
        cls = _classes().get(obj["__dc__"])
        fields = {k: decode(v) for k, v in obj["f"].items()}
        if cls is None:
            return fields
        # campo que esta versão não conhece (servidor mais novo que o cliente) fica de fora
        conhecidos = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in fields.items() if k in conhecidos})
    if "__dt__" in obj:
        return datetime.fromisoformat(obj["__dt__"])
    if "__d__" in obj:
        return date.fromisoformat(obj["__d__"])
    if "__b__" in obj:
        return base64.b64decode(obj["__b__"])
    if "__t__" in obj:
        return tuple(decode(v) for v in obj["__t__"])
    if "__s__" in obj:
        return {decode(v) for v in obj["__s__"]}
    if "__m__" in obj:
        return {decode(k): decode(v) for k, v in obj["__m__"]}
    return {k: decode(v) for k, v in obj.items()}


def dumps(obj) -> bytes:
    return json.dumps(encode(obj), ensure_ascii=False).encode("utf-8")


def loads(data: bytes):
    return decode(json.loads(data.decode("utf-8")))
