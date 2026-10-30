"""Junta traduções novas aos arquivos de idioma (lê JSON {"en": {...}, "es": {...}} na entrada)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "ipe" / "locale"


def main() -> int:
    data = json.load(sys.stdin)
    cat = json.loads((LOC / "pt-BR.json").read_text(encoding="utf-8"))
    sources = set(cat["strings"]) | set(cat["patterns"])
    for lang, mapping in data.items():
        path = LOC / f"{lang}.json"
        cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        unknown = [k for k in mapping if k not in sources]
        bad = [k for k, v in mapping.items() if k.count("{}") != str(v).count("{}")]
        cur.update({k: v for k, v in mapping.items() if v})
        path.write_text(json.dumps(cur, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        done = sum(1 for s in sources if cur.get(s))
        print(f"{lang}: +{len(mapping)} -> {done}/{len(sources)} ({done * 100 // len(sources)}%)"
              + (f"  FORA DO CATÁLOGO: {len(unknown)} {unknown[:3]}" if unknown else "")
              + (f"  CHAVES {{}} DIFERENTES: {bad[:3]}" if bad else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
