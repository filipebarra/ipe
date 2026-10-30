"""Mostra um pedaço do catálogo para traduzir: python tools/i18n_show.py <de> <ate> [lang]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOC = Path(__file__).resolve().parent.parent / "src" / "ipe" / "locale"


def main() -> int:
    a, b = int(sys.argv[1]), int(sys.argv[2])
    lang = sys.argv[3] if len(sys.argv) > 3 else "en"
    cat = json.loads((LOC / "pt-BR.json").read_text(encoding="utf-8"))
    items = cat["strings"] + cat["patterns"]
    done = json.loads((LOC / f"{lang}.json").read_text(encoding="utf-8")) if (LOC / f"{lang}.json").exists() else {}
    todo = [s for s in items if not done.get(s)]
    print(f"# {len(todo)} sem tradução em {lang} (total {len(items)}); mostrando {a}..{b}")
    for s in todo[a:b]:
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
