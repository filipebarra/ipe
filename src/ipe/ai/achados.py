"""Achado de IA como objeto revisável (0.99.46) — a base comum das IAs que apontam achados.

Toda IA que aponta alguma coisa (nódulo pulmonar agora; tumor da RM de mama, cálcio, aorta depois)
devolve **candidatos**, e cada candidato é guardado no banco (tabela `achado_ia`) com:

- **posição** em mm (coordenadas do paciente), para o clique levar até ele em qualquer série do exame;
- **números com unidade** ({chave: {"v": valor, "u": unidade, "n": nome}});
- **de onde veio**: ferramenta, modelo e versão, série usada, e a **elegibilidade** — por que a série
  serviu e o que pede cuidado (corte grosso, contraste…);
- **estado**: sugerido → confirmado / corrigido / descartado, com quem revisou e quando.

Regras:
- **nada vai sozinho ao laudo**: o texto para o laudo só leva o que foi confirmado ou corrigido;
- rodar a IA de novo troca só os **sugeridos**: o que o médico já revisou fica;
- o confirmado pode virar **lesão acompanhada** (com a medida no exame, para o seguimento).

Sem Qt.
"""
from __future__ import annotations

ESTADOS = {"sugerido": "Sugerido", "confirmado": "Confirmado", "corrigido": "Corrigido",
           "descartado": "Descartado"}
CORES = {"sugerido": "#e3b341", "confirmado": "#3fb950", "corrigido": "#58a6ff", "descartado": "#8b949e"}
VALEM = ("confirmado", "corrigido")


def numero(v, u: str, n: str) -> dict:
    return {"v": v, "u": u, "n": n}


def _fmt(d: dict) -> str:
    v, u = d.get("v"), d.get("u", "")
    if v is None:
        return "—"
    if isinstance(v, float):
        casas = 0 if abs(v) >= 100 or (abs(v) >= 10 and float(v).is_integer()) else 1
        txt = f"{v:.{casas}f}".replace(".", ",")
    elif isinstance(v, (list, tuple)):
        txt = " × ".join(f"{float(x):.1f}".replace(".", ",") for x in v)
    else:
        txt = str(v)
    return f"{txt} {u}".strip()


def numeros_validos(a: dict) -> dict:
    """Os números que valem: os corrigidos pelo médico por cima dos da IA."""
    out = dict(a.get("numeros") or {})
    for k, v in (a.get("corrigidos") or {}).items():
        base = dict(out.get(k) or {})
        base["v"] = v
        out[k] = base
    return out


def texto_dos_numeros(a: dict, chaves=None) -> str:
    nums = numeros_validos(a)
    chaves = chaves or list(nums)
    return "; ".join(f"{nums[k].get('n', k)} {_fmt(nums[k])}" for k in chaves if k in nums)


def resumo_curto(a: dict, chaves=None) -> str:
    """'N1 · lobo inferior direito · 6,2 mm · 98 mm³'."""
    nums = numeros_validos(a)
    chaves = chaves or list(nums)[:2]
    partes = [a.get("rotulo", ""), a.get("local", "")] + [_fmt(nums[k]) for k in chaves if k in nums]
    return " · ".join(p for p in partes if p)


def conciliar(novos: list, revisados: list[dict], distancia_mm=5.0) -> tuple[list, list]:
    """Uma rodada nova da IA contra o que o médico já revisou. `novos`: objetos com `.centro` (mm) e
    `.rotulo`; `revisados`: achados (dict) que não estão mais "sugerido".

    O candidato a menos de `distancia_mm` (ou da metade do diâmetro dele) de um revisado **é** aquele
    achado: herda o rótulo e não volta como sugestão. Os outros ganham rótulos que não repetem os já
    usados. Devolve (os que viram sugestão nova, todos com o rótulo final)."""
    import re

    import numpy as np
    usados = {a.get("rotulo", "") for a in revisados}
    prefixo = next((re.match(r"\D*", c.rotulo).group(0) for c in novos if getattr(c, "rotulo", "")), "N")
    livres = (f"{prefixo}{k}" for k in range(1, 10_000) if f"{prefixo}{k}" not in usados)
    sugestoes, todos = [], []
    for c in novos:
        p = np.asarray(c.centro, float)
        raio = 0.0
        try:
            raio = float(c.numeros.get("diametro_mm", {}).get("v") or 0) / 2
        except AttributeError:
            pass
        par = None
        for a in revisados:
            q = a.get("posicao")
            if q is not None and float(np.linalg.norm(p - np.asarray(q, float))) <= max(distancia_mm, raio):
                par = a
                break
        if par is not None:
            c.rotulo = par.get("rotulo", c.rotulo)
        else:
            c.rotulo = next(livres)
            sugestoes.append(c)
        todos.append(c)
    return sugestoes, todos


def contagem(achados: list[dict]) -> dict:
    out = {e: 0 for e in ESTADOS}
    for a in achados:
        out[a.get("estado", "sugerido")] = out.get(a.get("estado", "sugerido"), 0) + 1
    return out


def texto_do_laudo(achados: list[dict], frase=None) -> str:
    """Só o confirmado e o corrigido. `frase(achado) -> str` é a da ferramenta (uma linha por achado)."""
    valem = [a for a in achados if a.get("estado") in VALEM]
    if not valem:
        return ""
    linhas = [(frase(a) if frase else f"{a.get('tipo', 'Achado')} {resumo_curto(a)}") for a in valem]
    return "\n".join(f"- {x}" for x in linhas if x)


def quem_e_quando(a: dict) -> str:
    if a.get("estado", "sugerido") == "sugerido":
        return "proposto pela IA"
    q = a.get("revisado_em")
    data = q.strftime("%d/%m/%Y %H:%M") if hasattr(q, "strftime") else str(q or "")
    return f"{ESTADOS.get(a['estado'], a['estado']).lower()} por {a.get('revisor') or '?'} em {data}".strip()
