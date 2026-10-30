"""Calibração GSDF do monitor (DICOM PS3.14).

A ideia da GSDF: passos iguais de cinza têm de parecer passos iguais de brilho. O monitor
comum não faz isso (ele segue mais ou menos um gama 2,2), então montamos uma tabela que
corrige a saída — o mesmo que os monitores de laudo fazem por dentro.

Sem fotômetro não dá para medir o monitor: o usuário informa o preto (L mín), o branco
(L máx) e o gama aproximado, e os padrões de teste mostram se ficou bom.
"""

from __future__ import annotations

import numpy as np

# constantes da curva de Barten, PS3.14 (índice de JND -> luminância)
_A, _B, _C, _D = -1.3011877, -2.5840191e-2, 8.0242636e-2, -1.0320229e-1
_E, _F, _G, _H = 1.3646699e-1, 2.8745620e-2, -2.5468404e-2, -3.1978977e-3
_K, _M = 1.2992634e-4, 1.3635334e-3

JND_MIN, JND_MAX = 1.0, 1023.0


def luminance(jnd) -> np.ndarray:
    """Luminância (cd/m²) de um índice de JND, pela fórmula do padrão."""
    j = np.clip(np.asarray(jnd, dtype=np.float64), JND_MIN, JND_MAX)
    ln = np.log(j)
    p = [ln ** n for n in range(1, 6)]
    num = _A + _C * p[0] + _E * p[1] + _G * p[2] + _M * p[3]
    den = 1.0 + _B * p[0] + _D * p[1] + _F * p[2] + _H * p[3] + _K * p[4]
    return np.power(10.0, num / den)


_TABELA_J = np.linspace(JND_MIN, JND_MAX, 20000)
_TABELA_L = luminance(_TABELA_J)


def jnd_index(lum) -> np.ndarray:
    """Índice de JND de uma luminância (inverso da curva, por interpolação)."""
    l = np.clip(np.asarray(lum, dtype=np.float64), _TABELA_L[0], _TABELA_L[-1])
    return np.interp(l, _TABELA_L, _TABELA_J)


def native_luminance(levels, l_min: float, l_max: float, gamma: float = 2.2) -> np.ndarray:
    """Brilho que o monitor dá para cada nível de cinza, sem correção."""
    x = np.clip(np.asarray(levels, dtype=np.float64) / 255.0, 0.0, 1.0)
    return l_min + (l_max - l_min) * np.power(x, gamma)


def lut(l_min: float = 0.5, l_max: float = 300.0, gamma: float = 2.2, size: int = 256) -> np.ndarray:
    """Tabela 0–255 que deixa a escala de cinza perceptualmente uniforme neste monitor."""
    l_min = max(0.05, float(l_min))
    l_max = max(l_min * 1.5, float(l_max))
    j0, j1 = jnd_index(l_min), jnd_index(l_max)
    alvo = luminance(np.linspace(j0, j1, size))            # brilho que cada passo deveria ter
    niveis = np.arange(256)
    nativo = native_luminance(niveis, l_min, l_max, gamma)
    saida = np.interp(alvo, nativo, niveis)                # qual nível dá aquele brilho
    return np.clip(np.round(saida), 0, 255).astype(np.uint8)


def deviation(table: np.ndarray, l_min: float, l_max: float, gamma: float = 2.2,
              steps: int = 18) -> float:
    """Maior desvio (%) entre os passos de JND, medido em 18 pontos como manda o teste do padrão.

    Zero seria perfeito; até ~10% é o que se aceita num monitor de laudo. Com 8 bits e preto
    muito baixo sobra sempre algum desvio na ponta escura — é limitação do monitor, não do cálculo.
    """
    idx = np.linspace(0, len(table) - 1, max(3, int(steps))).round().astype(int)
    lum = native_luminance(table[idx].astype(np.float64), l_min, l_max, gamma)
    passos = np.diff(jnd_index(lum))
    if passos.size == 0 or passos.mean() <= 0:
        return 100.0
    return float(np.max(np.abs(passos - passos.mean())) / passos.mean() * 100.0)


def apply(gray: np.ndarray, table: np.ndarray | None) -> np.ndarray:
    """Aplica a tabela numa imagem de 8 bits (cinza ou RGB)."""
    if table is None:
        return gray
    return table[gray]


# ---------------------------------------------------------------------------
# padrões de teste (desenhados por nós)
# ---------------------------------------------------------------------------

def pattern(kind: str = "steps", width: int = 1024, height: int = 768) -> np.ndarray:
    """Figuras para conferir a calibração a olho, em 8 bits."""
    w, h = max(64, int(width)), max(64, int(height))
    img = np.zeros((h, w), dtype=np.uint8)
    if kind == "ramp":
        img[:] = (np.linspace(0, 255, w)[None, :]).astype(np.uint8)
        return img
    if kind == "lines":                       # pares de linhas: resolução e nitidez
        img[:] = 128
        meio = h // 2
        img[:meio:2, :] = 255
        img[:meio + 1:2, :] = img[:meio + 1:2, :]
        img[meio:, ::2] = 255
        return img
    if kind == "contrast":                    # quadrados de 5% perto do preto e do branco
        img[:] = 0
        img[h // 4:h // 2, w // 4:w // 2] = 13            # ~5% sobre o preto
        img[h // 2:3 * h // 4, w // 4:w // 2] = 0
        img[h // 4:h // 2, w // 2:3 * w // 4] = 255
        img[h // 2:3 * h // 4, w // 2:3 * w // 4] = 242   # ~5% abaixo do branco
        return img
    # padrão: 16 degraus, cada um com um quadrado 5% mais claro no meio
    n = 16
    for i in range(n):
        x0, x1 = int(i * w / n), int((i + 1) * w / n)
        base = int(round(i * 255 / (n - 1)))
        img[:, x0:x1] = base
        dy, dx = h // 6, (x1 - x0) // 4
        img[h // 2 - dy:h // 2 + dy, x0 + dx:x1 - dx] = min(255, base + 13)
    return img


PATTERNS = {"steps": "16 degraus com quadrado de 5%", "ramp": "Rampa contínua",
            "contrast": "Contraste perto do preto e do branco", "lines": "Pares de linhas"}


# ---------------------------------------------------------------------------
# configuração por monitor
# ---------------------------------------------------------------------------

def config(settings, screen: str) -> dict:
    todos = settings.get("monitors", {}) or {}
    return dict((todos.get(screen, {}) or {}).get("gsdf", {}) or {})


def save_config(settings, screen: str, cfg: dict) -> None:
    todos = dict(settings.get("monitors", {}) or {})
    dados = dict(todos.get(screen, {}) or {})
    dados["gsdf"] = cfg
    todos[screen] = dados
    settings.set("monitors", todos)
    settings.save()


def table_for(settings, screen: str) -> np.ndarray | None:
    """Tabela do monitor, ou None quando a calibração está desligada."""
    cfg = config(settings, screen)
    if not cfg.get("on"):
        return None
    return lut(float(cfg.get("lmin", 0.5)), float(cfg.get("lmax", 300.0)),
               float(cfg.get("gamma", 2.2)))
