"""Presets de janela por modalidade (0.99.22, plano AW item 10).

Os presets de fábrica (pulmão, mediastino, osso…) são de TC: na RM, na mamografia e no PET eles
não querem dizer nada. Cada modalidade pode ter a sua lista, feita pelo botão "Guardar a janela
atual como preset" do menu da janela. Modalidade sem lista própria usa a lista geral, como antes.
As teclas 1–9 aplicam o preset da modalidade do quadro ativo.
"""
from __future__ import annotations

CHAVE_GERAL = "viewer.wl_presets"
CHAVE_MOD = "viewer.wl_presets_mod"


def _todos_mod(settings) -> dict:
    d = settings.get(CHAVE_MOD, {}) if settings is not None else {}
    return d if isinstance(d, dict) else {}


def presets(settings, modalidade: str = "") -> dict:
    """tecla -> [nome, largura, nível] para esta modalidade."""
    mod = (modalidade or "").upper()
    proprio = _todos_mod(settings).get(mod) if mod else None
    if isinstance(proprio, dict) and proprio:
        return dict(proprio)
    geral = settings.get(CHAVE_GERAL, {}) if settings is not None else {}
    return dict(geral or {})


def tem_lista_propria(settings, modalidade: str) -> bool:
    p = _todos_mod(settings).get((modalidade or "").upper())
    return isinstance(p, dict) and bool(p)


def tecla_livre(settings, modalidade: str) -> str | None:
    usados = set(_todos_mod(settings).get((modalidade or "").upper(), {}) or {})
    return next((str(k) for k in range(1, 10) if str(k) not in usados), None)


def guardar(settings, modalidade: str, tecla: str, nome: str, largura: float, nivel: float) -> None:
    """Grava o preset na lista da modalidade (CT sem lista própria grava na geral)."""
    mod = (modalidade or "").upper()
    if not mod or (mod == "CT" and not tem_lista_propria(settings, "CT")):
        geral = dict(settings.get(CHAVE_GERAL, {}) or {})
        geral[str(tecla)] = [nome, round(float(largura), 1), round(float(nivel), 1)]
        settings.set(CHAVE_GERAL, geral)
    else:
        todos = {k: dict(v) for k, v in _todos_mod(settings).items() if isinstance(v, dict)}
        todos.setdefault(mod, {})[str(tecla)] = [nome, round(float(largura), 1), round(float(nivel), 1)]
        settings.set(CHAVE_MOD, todos)
    try:
        settings.save()
    except Exception:  # noqa: BLE001 - Settings de teste sem arquivo
        pass


def ler_wl(texto: str) -> tuple[float, float] | None:
    """'400 40', '400/40', 'W 400 L 40', '1500; -600' -> (largura, nível)."""
    import re
    nums = re.findall(r"-?\d+(?:[.,]\d+)?", texto or "")
    if len(nums) != 2:
        return None
    w, l = (float(n.replace(",", ".")) for n in nums)
    return (w, l) if w > 0 else None


def ler_zoom(texto: str) -> tuple[str, float] | None:
    """O zoom digitado (0.99.45, plano AW item 9).

    - '150', '150%', '1,5x' -> ("ajuste", 1.5): relativo a "ajustar à janela", o mesmo número do canto;
    - '1:1', 'pixel', '1 para 1' -> ("pixel", 1.0): 1 pixel da imagem = 1 pixel da tela;
    - '2:1' -> ("pixel", 2.0).
    Fora de 5% a 4000% devolve None."""
    import re
    t = (texto or "").strip().lower().replace(",", ".")
    if not t:
        return None
    if t in ("pixel", "px", "1 para 1", "1x1"):
        return ("pixel", 1.0)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", t)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        return ("pixel", a / b) if a > 0 and b > 0 and 0.05 <= a / b <= 40 else None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(%|x|×)?", t)
    if not m:
        return None
    v = float(m.group(1))
    f = v if m.group(2) in ("x", "×") else v / 100.0
    return ("ajuste", f) if 0.05 <= f <= 40 else None
