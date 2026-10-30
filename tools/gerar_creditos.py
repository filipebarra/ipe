"""Gera CREDITOS.md e HISTORIA*.md na raiz do repositório (0.99.13).

As fontes ficam dentro do programa: `src/ipe/creditos.py` (a lista) e `src/ipe/ajuda/historia.*.md`
(a história, nos três idiomas). Rode depois de mexer em qualquer uma delas:

    python tools/gerar_creditos.py

O teste `test_creditos.py` reprova quando os arquivos da raiz ficam diferentes das fontes.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

HISTORIAS = {"historia.pt-BR.md": "HISTORIA.md", "historia.en.md": "HISTORIA.en.md",
             "historia.es.md": "HISTORIA.es.md"}


def arquivos() -> dict[Path, str]:
    from ipe import creditos
    out = {RAIZ / "CREDITOS.md": creditos.markdown()}
    pasta = RAIZ / "src" / "ipe" / "ajuda"
    for origem, destino in HISTORIAS.items():
        out[RAIZ / destino] = (pasta / origem).read_text(encoding="utf-8")
    return out


def main() -> int:
    for caminho, texto in arquivos().items():
        caminho.write_text(texto, encoding="utf-8")
        print(f"gravado: {caminho.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
