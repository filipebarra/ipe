"""Renderização 3D por lançamento de raios em CPU (numpy): MIP / MinIP / média e
renderização de volume (VR) com função de transferência e sombreamento simples.

O volume é reamostrado numa grade isotrópica alinhada ao paciente (x = esquerda,
y = posterior, z = superior). A câmera é ortográfica; a vista inicial é anterior
(direita do paciente à esquerda da tela, superior em cima).

Além de desenhar, o renderizador guarda a profundidade de cada pixel da última
imagem: é isso que permite clicar numa lesão e saber em que ponto do paciente
(em mm) o raio bateu, para levar os cortes até lá."""

from __future__ import annotations

import numpy as np

from ipe.imaging import colormaps as CM
from ipe.imaging.volume import Volume, sample_trilinear

# presets de VR: (nome, mínimo, máximo, tabela de cores, opacidade máx. por mm) — valores em HU para TC
VR_PRESETS = {
    "bone": ("Osso", 180.0, 900.0, "vr_bone", 0.35),
    "vessels": ("Vasos (angio TC)", 130.0, 450.0, "vr_vessel", 0.30),
    "skin": ("Pele", -500.0, -150.0, "vr_skin", 0.12),
    "lung": ("Pulmão / vias aéreas", -950.0, -500.0, "vr_skin", 0.05),
    "soft": ("Tecidos moles", -50.0, 250.0, "vr_vessel", 0.08),
    "auto": ("Automático (RM / PET)", None, None, "hot", 0.12),
}


def rotation(az: float, el: float) -> np.ndarray:
    """Matriz 3×3 cujas linhas são (tela-direita u, tela-baixo v, direção de vista d)."""
    u0, v0, d0 = np.array([1.0, 0, 0]), np.array([0, 0, -1.0]), np.array([0, 1.0, 0])
    a, e = np.radians(az), np.radians(el)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    # elevação: gira em torno do eixo "tela-direita" já girado
    u = rz @ u0
    k = u / np.linalg.norm(u)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    re = np.eye(3) + np.sin(e) * kx + (1 - np.cos(e)) * (kx @ kx)
    m = re @ rz
    return np.stack([m @ u0, m @ v0, m @ d0])


def polygon_mask(poly, size: tuple[int, int]) -> np.ndarray:
    """Máscara booleana (h×w) do interior de um polígono dado em pixels da tela.

    Varredura por linha com a regra par/ímpar — o laço da escultura costuma ter
    dezenas de pontos, então o custo é a altura da imagem, não o número de voxels.
    """
    w, h = int(size[0]), int(size[1])
    m = np.zeros((h, w), bool)
    pts = np.asarray(poly, dtype=np.float64)
    if pts.ndim != 2 or len(pts) < 3:
        return m
    x, y = pts[:, 0], pts[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cols = np.arange(w, dtype=np.float64) + 0.5
    for row in range(h):
        yy = row + 0.5
        cruza = (y > yy) != (y2 > yy)
        if not cruza.any():
            continue
        ya, yb = y[cruza], y2[cruza]
        xs = x[cruza] + (yy - ya) * (x2[cruza] - x[cruza]) / (yb - ya)
        xs = np.sort(xs)
        m[row] = np.searchsorted(xs, cols, side="right") % 2 == 1
    return m


class Renderer3D:
    def __init__(self, vol: Volume, max_dim: int = 256, progress=None):
        nz, ny, nx = vol.shape
        corners = np.array([vol.voxel_to_patient(i, j, k) for i in (0, nx - 1) for j in (0, ny - 1)
                            for k in (0, nz - 1)])
        self.lo = corners.min(0)
        ext = corners.max(0) - self.lo
        self.step = max(float(ext.max()) / max_dim, min(vol.dx, vol.dy, vol.dz))
        shape = tuple(int(np.ceil(e / self.step)) + 1 for e in ext[::-1])      # (z, y, x)
        self.shape = shape
        minv = np.linalg.inv(vol.matrix())
        gz, gy, gx = shape
        ys, xs = np.mgrid[0:gy, 0:gx].astype(np.float32)
        data = np.empty(shape, np.float32)
        fill = float(vol.data.min())
        for z in range(gz):
            P = np.stack([self.lo[0] + xs * self.step, self.lo[1] + ys * self.step,
                          np.full_like(xs, self.lo[2] + z * self.step)], axis=-1)
            ijk = (P - vol.origin.astype(np.float32)) @ minv.T.astype(np.float32)
            sl = sample_trilinear(vol.data, ijk)
            data[z] = np.where(np.isnan(sl), fill, sl)
            if progress and z % 8 == 0 and progress(z, gz) is False:
                raise InterruptedError
        self.data = data
        self.fill = fill
        self.center = self.lo + ext / 2
        self.radius = float(np.linalg.norm(ext)) / 2
        self._grad = None
        sample = data[::2, ::2, ::2]
        self.p = {q: float(np.percentile(sample, q)) for q in (1, 50, 90, 99, 99.7)}
        self.window = (vol.window if vol.window else None)
        # recorte do volume em índices da grade (a grade é alinhada aos eixos do paciente)
        self.clip = [0, shape[2] - 1, 0, shape[1] - 1, 0, shape[0] - 1]   # x0,x1, y0,y1, z0,z1
        self.vol_origin = self.lo.copy()
        # plano de corte oblíquo: (normal em índices da grade, constante) — fica o que dá n·p <= c
        self.plane: tuple[np.ndarray, float] | None = None
        # escultura e remoção da maca: True = voxel visível
        self.mask: np.ndarray | None = None
        self._rev = 0                       # muda quando a máscara muda, para descartar caixas em cache
        self._boxes: dict = {}
        self.last_depth: np.ndarray | None = None
        self._last: dict | None = None

    # ------------------------------------------------------------------
    def gradient(self) -> np.ndarray:
        """Normais (int8 ×3) para o sombreamento, calculadas uma vez."""
        if self._grad is None:
            d = self.data
            g = np.empty(d.shape + (3,), np.int8)
            for z in range(d.shape[0]):
                z0, z1 = max(z - 1, 0), min(z + 1, d.shape[0] - 1)
                gz = d[z1] - d[z0]
                gy = np.gradient(d[z], axis=0)
                gx = np.gradient(d[z], axis=1)
                n = np.sqrt(gx * gx + gy * gy + gz * gz) + 1e-6
                g[z, ..., 0] = np.clip(gx / n * 127, -127, 127)
                g[z, ..., 1] = np.clip(gy / n * 127, -127, 127)
                g[z, ..., 2] = np.clip(gz / n * 127, -127, 127)
            self._grad = g
        return self._grad

    def _normal_at(self, pts: np.ndarray) -> np.ndarray:
        """Normal da superfície no ponto exato, por diferenças centrais interpoladas."""
        eixo = np.eye(3, dtype=np.float32)
        g = np.empty((len(pts), 3), np.float32)
        for a in range(3):
            mais = sample_trilinear(self.data, pts + eixo[a])
            menos = sample_trilinear(self.data, pts - eixo[a])
            g[:, a] = np.nan_to_num(mais - menos, nan=0.0)
        norma = np.linalg.norm(g, axis=1, keepdims=True)
        return g / np.maximum(norma, 1e-6)

    def auto_range(self) -> tuple[float, float]:
        return self.p[90], self.p[99.7]

    # ------------------------------------------------------------------ recorte
    def clip_reset(self) -> None:
        gz, gy, gx = self.shape
        self.clip = [0, gx - 1, 0, gy - 1, 0, gz - 1]

    def clip_full(self) -> bool:
        gz, gy, gx = self.shape
        return self.clip == [0, gx - 1, 0, gy - 1, 0, gz - 1]

    def untouched(self) -> bool:
        """Volume inteiro: sem caixa, sem plano e sem escultura."""
        return self.clip_full() and self.plane is None and self.mask is None

    def restore_all(self) -> None:
        self.clip_reset()
        self.plane = None
        self.mask = None
        self._rev += 1
        self._boxes.clear()

    def index_of(self, point_mm) -> tuple[float, float, float]:
        """Ponto em mm do paciente -> índice (x, y, z) na grade do 3D."""
        p = (np.asarray(point_mm, dtype=float) - self.lo) / self.step
        return float(p[0]), float(p[1]), float(p[2])

    def point_of(self, index_xyz) -> np.ndarray:
        """Índice (x, y, z) na grade -> ponto em mm do paciente."""
        return self.lo + np.asarray(index_xyz, dtype=float) * self.step

    def cut_at(self, point_mm, side: str) -> None:
        """Corta o volume a partir de um ponto, jogando fora um lado.

        `side`: "right"/"left" (eixo X do paciente), "anterior"/"posterior" (Y),
        "head"/"feet" (Z). Os nomes são anatômicos: "posterior" mantém o que está atrás.
        """
        gz, gy, gx = self.shape
        x, y, z = self.index_of(point_mm)
        limites = {"x": (0, gx - 1), "y": (0, gy - 1), "z": (0, gz - 1)}
        # LPS: +x = esquerda do paciente, +y = posterior, +z = cabeça
        onde = {"left": ("x", x, "min"), "right": ("x", x, "max"),
                "posterior": ("y", y, "min"), "anterior": ("y", y, "max"),
                "head": ("z", z, "min"), "feet": ("z", z, "max")}
        if side not in onde:
            return
        eixo, valor, lado = onde[side]
        i = {"x": 0, "y": 2, "z": 4}[eixo]
        lo_lim, hi_lim = limites[eixo]
        v = int(round(max(lo_lim, min(hi_lim, valor))))
        if lado == "min":
            self.clip[i] = v
        else:
            self.clip[i + 1] = v

    # ---------------------------------------------------------------- plano oblíquo
    def cut_plane(self, point_mm, normal_mm, keep: str = "back") -> None:
        """Plano de corte em qualquer ângulo, passando pelo ponto.

        `normal_mm` é a direção em mm do paciente — na tela, usa-se a direção de
        vista, e aí o plano fica paralelo ao monitor. `keep="back"` mantém o lado
        de onde a normal vem (com a normal no sentido do olhar, é o lado de cá, mais
        perto do observador); `keep="front"` mantém o lado oposto, ou seja, tira o
        que está na frente e mostra o miolo — que é o corte que se quer ver.
        """
        n = np.asarray(normal_mm, dtype=float)
        norma = float(np.linalg.norm(n))
        if norma < 1e-9:
            return
        n = n / norma
        # índices da grade: p_idx = (P - lo)/step, então n·P <= c vira (n)·p_idx <= (c - n·lo)/step
        p = np.asarray(point_mm, dtype=float)
        if keep == "front":
            n = -n
        c = float(n @ (p - self.lo)) / self.step
        self.plane = (n.astype(np.float32), c)

    def nudge_plane(self, mm: float) -> bool:
        """Empurra o plano de corte na direção da normal (arrastar o corte)."""
        if self.plane is None:
            return False
        n, c = self.plane
        self.plane = (n, c + float(mm) / self.step)
        return True

    def plane_depth_mm(self) -> float | None:
        """Onde o plano está, em mm ao longo da própria normal (para mostrar na tela)."""
        return None if self.plane is None else float(self.plane[1] * self.step)

    # ---------------------------------------------------------------- escultura
    def _ensure_mask(self) -> np.ndarray:
        if self.mask is None:
            self.mask = np.ones(self.shape, bool)
        return self.mask

    def _screen_of_voxels(self, z: int, cam: dict) -> tuple[np.ndarray, np.ndarray]:
        """Coluna/linha na tela de todos os voxels de um corte z da grade."""
        u, v = cam["u"], cam["v"]
        gz, gy, gx = self.shape
        xs = self.lo[0] + np.arange(gx, dtype=np.float64) * self.step
        ys = self.lo[1] + np.arange(gy, dtype=np.float64) * self.step
        zv = self.lo[2] + z * self.step
        base = cam["base_mm"]
        jj = ((xs - base[0]) * u[0])[None, :] + ((ys - base[1]) * u[1])[:, None] + (zv - base[2]) * u[2]
        ii = ((xs - base[0]) * v[0])[None, :] + ((ys - base[1]) * v[1])[:, None] + (zv - base[2]) * v[2]
        j = (jj - cam["pan"][0]) / cam["ps"] + cam["w"] / 2 - 0.5
        i = (ii - cam["pan"][1]) / cam["ps"] + cam["h"] / 2 - 0.5
        return j, i

    def _camera(self, az: float, el: float, size: tuple[int, int], zoom: float,
                pan: tuple[float, float]) -> dict:
        w, h = int(size[0]), int(size[1])
        u, v, d = rotation(az, el)
        ps = 2 * self.radius / (min(w, h) * zoom)
        return {"u": u, "v": v, "d": d, "ps": ps, "w": w, "h": h, "pan": pan,
                "base_mm": self.center - self.radius * d}

    def sculpt(self, poly, size: tuple[int, int], az: float, el: float, zoom: float = 1.0,
               pan: tuple[float, float] = (0.0, 0.0), keep_inside: bool = False) -> int:
        """Apaga o que está dentro do laço (ou guarda só o que está dentro).

        O laço é um polígono em pixels da imagem que o usuário está vendo; cada
        voxel é projetado na tela e consultado nessa máscara. Devolve quantos
        voxels sumiram.
        """
        pm = polygon_mask(poly, size)
        if not pm.any():
            return 0
        cam = self._camera(az, el, size, zoom, pan)
        mask = self._ensure_mask()
        gz, gy, gx = self.shape
        antes = int(mask.sum())
        for z in range(gz):
            j, i = self._screen_of_voxels(z, cam)
            jc = np.rint(j).astype(np.int32)
            ic = np.rint(i).astype(np.int32)
            dentro_tela = (jc >= 0) & (jc < cam["w"]) & (ic >= 0) & (ic < cam["h"])
            sel = np.zeros((gy, gx), bool)
            if dentro_tela.any():
                sel[dentro_tela] = pm[ic[dentro_tela], jc[dentro_tela]]
            if keep_inside:
                mask[z] &= sel
            else:
                mask[z] &= ~sel
        self._rev += 1
        self._boxes.clear()
        return antes - int(mask.sum())

    def remove_table(self, air: float = -300.0, max_thick_mm: float = 35.0,
                     min_gap_mm: float = 4.0) -> int:
        """Tira a maca da TC: a estrutura fina e isolada que vem antes do corpo, por trás.

        Em decúbito dorsal a mesa é a primeira coisa sólida que o olhar encontra
        vindo de trás (+y é posterior), é fina e tem ar entre ela e as costas. Onde
        esse desenho não aparece — paciente em pruno, RM, PET — nada é removido, e
        aí vale a escultura à mão.
        """
        if self.p[1] > -500:                      # não parece TC em HU
            return 0
        solido = self.data > air
        P = solido[:, ::-1, :]                    # y invertido: 0 = o mais posterior
        gz, gy, gx = self.shape
        idx = np.arange(gy, dtype=np.int32)[None, :, None]
        tem = P.any(1)
        f = P.argmax(1).astype(np.int32)                                   # 1º sólido
        depois_do_solido = np.where(idx >= f[:, None, :], ~P, False)
        g = depois_do_solido.argmax(1).astype(np.int32)                    # 1º ar depois
        achou_ar = depois_do_solido.any(1)
        depois_do_ar = np.where(idx >= g[:, None, :], P, False)
        h = depois_do_ar.argmax(1).astype(np.int32)                        # volta a ser sólido
        achou_corpo = depois_do_ar.any(1)
        espessura = (g - f) * self.step
        vao = (h - g) * self.step
        mesa = (tem & achou_ar & achou_corpo & (espessura > 0) & (espessura <= max_thick_mm)
                & (vao >= min_gap_mm))
        if int(mesa.sum()) < max(20, int(0.02 * gz * gx)):
            return 0
        # A faixa da mesa vale para o volume inteiro, não para cada coluna: a mesa passa por
        # baixo do paciente todo, mas só as colunas que têm corpo atrás mostram o desenho
        # completo. Por coluna, sobrariam orelhas de mesa nas bordas e nos cortes fora do corpo.
        a = int(np.percentile(f[mesa], 5))
        b = int(np.percentile(g[mesa], 95))
        if b <= a or (b - a) * self.step > 2 * max_thick_mm:
            return 0
        # guarda: onde o corpo encosta na mesa (sem ar logo à frente da faixa), não se mexe
        k = max(1, int(np.ceil(min_gap_mm / self.step)))
        livre = ~P[:, b:b + k, :].any(1) if b + 1 <= gy else np.zeros((gz, gx), bool)
        fora = np.zeros(P.shape, bool)
        fora[:, a:b, :] = P[:, a:b, :] & livre[:, None, :]
        if not fora.any():
            return 0
        fora = fora[:, ::-1, :]                   # de volta à orientação da grade
        mask = self._ensure_mask()
        antes_n = int(mask.sum())
        mask &= ~fora
        self._rev += 1
        self._boxes.clear()
        return antes_n - int(mask.sum())

    # ---------------------------------------------------------------- caixa útil
    def _limits(self) -> tuple[int, int, int, int, int, int]:
        gz, gy, gx = self.shape
        cx0, cx1, cy0, cy1, cz0, cz1 = self.clip
        return (max(0, cx0), min(gx - 1, cx1), max(0, cy0), min(gy - 1, cy1),
                max(0, cz0), min(gz - 1, cz1))

    def content_box(self, lo_value: float) -> tuple[int, int, int, int, int, int] | None:
        """Menor caixa que ainda contém tudo acima do limiar — é o que deixa o raio
        começar perto do objeto em vez de atravessar o vazio."""
        chave = (round(float(lo_value), 2), self._rev)
        if chave in self._boxes:
            return self._boxes[chave]
        m = self.data >= lo_value
        if self.mask is not None:
            m &= self.mask
        zs, ys, xs = m.any((1, 2)), m.any((0, 2)), m.any((0, 1))
        if not zs.any():
            caixa = None
        else:
            def faixa(a):
                w = np.nonzero(a)[0]
                return int(w[0]), int(w[-1])
            x0, x1 = faixa(xs)
            y0, y1 = faixa(ys)
            z0, z1 = faixa(zs)
            caixa = (x0, x1, y0, y1, z0, z1)
        self._boxes[chave] = caixa
        return caixa

    def _step_range(self, box, d: np.ndarray, st: float, nsteps: int) -> tuple[int, int]:
        """Primeiro e último passo do raio que ainda podem encostar na caixa."""
        x0, x1, y0, y1, z0, z1 = box
        if x1 < x0 or y1 < y0 or z1 < z0:
            return 0, 0
        cantos = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
        P = self.lo + cantos * self.step
        base = self.center - self.radius * d
        t = (P - base) @ d
        s0 = max(0, int(np.floor(t.min() / st)) - 1)
        s1 = min(nsteps, int(np.ceil(t.max() / st)) + 2)
        return s0, max(s0, s1)

    def solid_mask(self, lo_value: float) -> np.ndarray:
        """O que está aparecendo: acima do limiar, dentro da caixa, do lado certo do plano
        e fora do que a escultura apagou. É a máscara que vira modelo 3D."""
        m = self.data >= float(lo_value)
        if self.mask is not None:
            m &= self.mask
        cx0, cx1, cy0, cy1, cz0, cz1 = self._limits()
        caixa = np.zeros(m.shape, bool)
        caixa[cz0:cz1 + 1, cy0:cy1 + 1, cx0:cx1 + 1] = True
        m &= caixa
        if self.plane is not None:
            n, c = self.plane
            z = np.arange(m.shape[0], dtype=np.float32)[:, None, None]
            y = np.arange(m.shape[1], dtype=np.float32)[None, :, None]
            x = np.arange(m.shape[2], dtype=np.float32)[None, None, :]
            m &= (x * float(n[0]) + y * float(n[1]) + z * float(n[2])) <= float(c)
        return m

    # ---------------------------------------------------------------- clique
    def point_at(self, px: float, py: float):
        """Ponto em mm do paciente sob o pixel clicado da última imagem, ou None."""
        if self._last is None or self.last_depth is None:
            return None
        L = self._last
        hr, wr = self.last_depth.shape
        x = int(round(px * wr / max(L["w_out"], 1)))
        y = int(round(py * hr / max(L["h_out"], 1)))
        if not (0 <= x < wr and 0 <= y < hr):
            return None
        s = float(self.last_depth[y, x])
        if not np.isfinite(s):
            return None
        u, v, d, ps = L["u"], L["v"], L["d"], L["ps"]
        jj = (x - wr / 2 + 0.5) * ps + L["pan"][0]
        ii = (y - hr / 2 + 0.5) * ps + L["pan"][1]
        origem = self.center - self.radius * d + jj * u + ii * v
        return origem + d * (s * L["st"])

    def screen_of(self, point_mm):
        """Caminho inverso: onde um ponto do paciente cai na última imagem."""
        if self._last is None:
            return None
        L = self._last
        u, v, d = L["u"], L["v"], L["d"]
        rel = np.asarray(point_mm, dtype=float) - (self.center - self.radius * d)
        j = (float(rel @ u) - L["pan"][0]) / L["ps"] + L["w_out"] / 2 - 0.5
        i = (float(rel @ v) - L["pan"][1]) / L["ps"] + L["h_out"] / 2 - 0.5
        return j, i

    # ---------------------------------------------------------------- desenho
    def render(self, mode: str = "mip", az: float = 0.0, el: float = 0.0, size: tuple[int, int] = (384, 384),
               lo: float = 0.0, hi: float = 1.0, cmap: str = "", opacity: float = 0.2, zoom: float = 1.0,
               pan: tuple[float, float] = (0.0, 0.0), fast: bool = False) -> np.ndarray:
        """Imagem: MIP/MinIP/média -> float32 (H×W) em unidades do volume; VR -> RGB uint8 (H×W×3)."""
        w_out, h_out = int(size[0]), int(size[1])
        # ao arrastar, desenha menor e amplia: são 4× menos raios, e o olho não percebe no giro
        w = (w_out + 1) // 2 if fast else w_out
        h = (h_out + 1) // 2 if fast else h_out
        w, h = max(w, 2), max(h, 2)
        R = rotation(az, el)
        u, v, d = R
        ps = 2 * self.radius / (min(w, h) * zoom)
        st = self.step * (2.0 if fast else 1.0)
        if mode == "surf" and not fast:
            st = self.step * 0.5              # meia passada: a superfície fica lisa
        jj = (np.arange(w, dtype=np.float32) - w / 2 + 0.5) * ps + pan[0]
        ii = (np.arange(h, dtype=np.float32) - h / 2 + 0.5) * ps + pan[1]
        origin = (self.center - self.radius * d - self.lo) / self.step            # em índices da grade
        base = (origin[None, None, :] + jj[None, :, None] * (u / self.step)[None, None, :]
                + ii[:, None, None] * (v / self.step)[None, None, :]).reshape(-1, 3).astype(np.float32)
        dstep = (d * st / self.step).astype(np.float32)
        nsteps = int(2 * self.radius / st) + 1
        gz, gy, gx = self.shape
        flat = self.data.reshape(-1)
        mask_flat = None if self.mask is None else self.mask.reshape(-1)
        npx = base.shape[0]
        cx0, cx1, cy0, cy1, cz0, cz1 = self._limits()
        if mode in ("vr", "surf"):
            dentro = self.content_box(lo)
            if dentro is None:
                self.last_depth = np.full((h, w), np.nan, np.float32)
                self._last = {"u": u, "v": v, "d": d, "ps": ps, "pan": pan, "st": st,
                              "w_out": w_out, "h_out": h_out}
                vazio = np.zeros((h_out, w_out, 3), np.uint8)
                return vazio
            cx0, cx1 = max(cx0, dentro[0]), min(cx1, dentro[1])
            cy0, cy1 = max(cy0, dentro[2]), min(cy1, dentro[3])
            cz0, cz1 = max(cz0, dentro[4]), min(cz1, dentro[5])
        s_ini, s_fim = self._step_range((cx0, cx1, cy0, cy1, cz0, cz1), d, st, nsteps)
        plano = self.plane
        depth = np.full(npx, np.nan, np.float32)
        if mode == "vr":
            grad = self.gradient().reshape(-1, 3)
            lut = CM.lut(cmap).astype(np.float32) / 255.0 if cmap in CM.COLORMAPS else \
                np.repeat(np.linspace(0, 1, 256, dtype=np.float32)[:, None], 3, 1)
            col = np.zeros((npx, 3), np.float32)
            acc = np.zeros(npx, np.float32)
            a_step = 1.0 - (1.0 - min(opacity, 0.99)) ** st     # opacidade por passo (por mm)
            light = -d.astype(np.float32)
            alive = np.arange(npx)
        elif mode == "surf":
            light = -d.astype(np.float32)
            shade_out = np.zeros(npx, np.float32)
            hit = np.zeros(npx, bool)
            prev = np.full(npx, -np.inf, np.float32)
            alive = np.arange(npx)
        else:
            out = np.full(npx, -np.inf if mode == "mip" else np.inf, np.float32) if mode != "avg" else \
                np.zeros(npx, np.float32)
            cnt = np.zeros(npx, np.float32) if mode == "avg" else None
        for s in range(s_ini, s_fim):
            if mode in ("vr", "surf"):
                if alive.size == 0:
                    break
                p = base[alive] + dstep * s
            else:
                p = base + dstep * s
            xi = np.rint(p[:, 0]).astype(np.int32)
            yi = np.rint(p[:, 1]).astype(np.int32)
            zi = np.rint(p[:, 2]).astype(np.int32)
            ok = ((xi >= cx0) & (xi <= cx1) & (yi >= cy0) & (yi <= cy1)
                  & (zi >= cz0) & (zi <= cz1))
            if plano is not None:
                n, c = plano
                ok &= (p[:, 0] * n[0] + p[:, 1] * n[1] + p[:, 2] * n[2]) <= c
            if not ok.any():
                continue
            idx0 = np.nonzero(ok)[0]
            lin = (zi[idx0] * gy + yi[idx0]) * gx + xi[idx0]
            if mask_flat is not None:
                fica = mask_flat[lin]
                if not fica.any():
                    continue
                idx0, lin = idx0[fica], lin[fica]
            val = flat[lin]
            if mode == "mip":
                melhor = val > out[idx0]
                out[idx0] = np.where(melhor, val, out[idx0])
                depth[idx0[melhor]] = s
            elif mode == "minip":
                melhor = val < out[idx0]
                out[idx0] = np.where(melhor, val, out[idx0])
                depth[idx0[melhor]] = s
            elif mode == "avg":
                out[idx0] += val
                cnt[idx0] += 1
            elif mode == "surf":
                pix = alive[idx0]
                valor = sample_trilinear(self.data, p[idx0]).astype(np.float32)
                valor = np.where(np.isnan(valor), self.fill, valor)
                cruzou = (valor >= lo) & ~hit[pix]
                if cruzou.any():
                    alvo = pix[cruzou]
                    # onde exatamente a superfície foi cruzada, entre esta amostra e a anterior
                    antes = prev[alvo]
                    atual = valor[cruzou]
                    finito = np.isfinite(antes)
                    ant = np.where(finito, antes, 0.0)            # -inf no 1º passo do raio
                    den = np.where(finito, atual - ant, 1.0)
                    t = np.where(finito & (den > 0),
                                 np.clip((lo - ant) / np.where(den > 0, den, 1.0), 0, 1), 1.0)
                    phit = p[idx0][cruzou] - dstep[None, :] * (1.0 - t)[:, None]
                    n = self._normal_at(phit)
                    brilho = np.abs(np.einsum("ij,j->i", n, light))
                    profundidade = 1.0 - 0.45 * (s / max(nsteps - 1, 1))
                    # raio que já entrou dentro do sólido: está vendo a face de um corte,
                    # que não tem superfície de verdade — desenha lisa, como um corte mesmo
                    face = ~np.isfinite(antes)
                    brilho = np.where(face, 0.55, brilho)
                    shade_out[alvo] = (0.15 + 0.85 * brilho) * profundidade
                    hit[alvo] = True
                    depth[alvo] = s - (1.0 - t)
                prev[pix] = valor
                if s % 8 == 7:
                    alive = alive[~hit[alive]]
            else:
                t = np.clip((val - lo) / max(hi - lo, 1e-6), 0, 1)
                sel = t > 0
                if sel.any():
                    idx = alive[idx0[sel]]
                    tt = t[sel]
                    a = a_step * tt
                    g = grad[lin[sel]].astype(np.float32) / 127.0
                    shade = 0.3 + 0.7 * np.abs(g @ light)
                    c = lut[(tt * 255).astype(np.int32)] * shade[:, None]
                    wgt = (1.0 - acc[idx]) * a
                    col[idx] += c * wgt[:, None]
                    acc[idx] += wgt
                    novo = np.isnan(depth[idx]) & (acc[idx] >= 0.5)
                    depth[idx[novo]] = s
                if s % 8 == 7:
                    alive = alive[acc[alive] < 0.97]
        self.last_depth = depth.reshape(h, w)
        self._last = {"u": u, "v": v, "d": d, "ps": ps, "pan": pan, "st": st,
                      "w_out": w_out, "h_out": h_out}
        if mode == "vr":
            img = np.clip(col * 255, 0, 255).astype(np.uint8).reshape(h, w, 3)
            return _upscale(img, w_out, h_out)
        if mode == "surf":
            cinza = np.clip(shade_out * 255, 0, 255).astype(np.uint8)
            if cmap in CM.COLORMAPS:
                img = CM.lut(cmap)[cinza].reshape(h, w, 3)
            else:
                img = np.repeat(cinza[:, None], 3, 1).reshape(h, w, 3)
            return _upscale(img, w_out, h_out)
        if mode == "avg":
            out = np.where(cnt > 0, out / np.maximum(cnt, 1), self.fill)
        out = np.where(np.isfinite(out), out, self.fill)
        return _upscale(out.reshape(h, w).astype(np.float32), w_out, h_out)


def _upscale(img: np.ndarray, w: int, h: int) -> np.ndarray:
    """Amplia a imagem rápida de volta ao tamanho pedido (vizinho mais próximo)."""
    if img.shape[0] == h and img.shape[1] == w:
        return img
    grande = np.repeat(np.repeat(img, 2, axis=0), 2, axis=1)
    if grande.shape[0] < h or grande.shape[1] < w:
        pad = [(0, max(0, h - grande.shape[0])), (0, max(0, w - grande.shape[1]))]
        pad += [(0, 0)] * (grande.ndim - 2)
        grande = np.pad(grande, pad, mode="edge")
    return grande[:h, :w]


# ------------------------------------------------------------------ estruturas segmentadas (0.99.82)
def _suavizar3(a: np.ndarray) -> np.ndarray:
    """Média 3×3×3 (caixa) só com numpy: deixa a borda da máscara em degrau com normal que preste."""
    out = a.astype(np.float32)
    for eixo in range(3):
        p = np.pad(out, [(1, 1) if e == eixo else (0, 0) for e in range(3)], mode="edge")
        sl = [slice(None)] * 3
        sl0, sl1, sl2 = list(sl), list(sl), list(sl)
        sl0[eixo], sl1[eixo], sl2[eixo] = slice(0, -2), slice(1, -1), slice(2, None)
        out = (p[tuple(sl0)] + p[tuple(sl1)] + p[tuple(sl2)]) / 3.0
    return out


def rotulos_na_grade(r: "Renderer3D", volumes: list, progress=None) -> tuple[np.ndarray, list]:
    """As máscaras 3D (MaskVolume, em mm) na grade isotrópica do 3D: rótulo 1..n por voxel e as cores.

    Cada máscara só é amostrada dentro da própria caixa (em mm), por vizinho mais próximo; onde duas se
    sobrepõem, fica a que veio depois. Mais de 254 estruturas: as que sobram ficam de fora."""
    gz, gy, gx = r.shape
    lab = np.zeros(r.shape, np.uint8)
    cores = []
    for n, mv in enumerate(volumes[:254]):
        m = np.asarray(mv.mascara, bool)
        if not m.any():
            cores.append(tuple(mv.color))
            continue
        nz, ny, nx = m.shape
        cantos = np.array([mv.origem + mv.matriz @ np.array([i, j, k], float)
                           for i in (0, nx - 1) for j in (0, ny - 1) for k in (0, nz - 1)])
        lo_i = np.floor((cantos.min(0) - r.lo) / r.step).astype(int) - 1
        hi_i = np.ceil((cantos.max(0) - r.lo) / r.step).astype(int) + 1
        x0, y0, z0 = np.maximum(lo_i, 0)
        x1, y1, z1 = np.minimum(hi_i, [gx - 1, gy - 1, gz - 1])
        if x1 < x0 or y1 < y0 or z1 < z0:
            cores.append(tuple(mv.color))
            continue
        inv = np.linalg.inv(mv.matriz)
        ys, xs = np.mgrid[y0:y1 + 1, x0:x1 + 1].astype(np.float64)
        for z in range(z0, z1 + 1):
            P = np.stack([r.lo[0] + xs * r.step, r.lo[1] + ys * r.step,
                          np.full_like(xs, r.lo[2] + z * r.step)], axis=-1)
            ijk = np.rint((P - mv.origem) @ inv.T).astype(np.int64)
            i, j, k = ijk[..., 0], ijk[..., 1], ijk[..., 2]
            ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny) & (k >= 0) & (k < nz)
            if not ok.any():
                continue
            dentro = np.zeros(ok.shape, bool)
            dentro[ok] = m[k[ok], j[ok], i[ok]]
            if dentro.any():
                fatia = lab[z, y0:y1 + 1, x0:x1 + 1]
                fatia[dentro] = n + 1
        cores.append(tuple(mv.color))
        if progress and progress(n + 1, len(volumes)) is False:
            raise InterruptedError
    return lab, cores


def _definir_estruturas(self, volumes: list, progress=None) -> int:
    """Liga as estruturas segmentadas a este 3D. Devolve quantas têm algum voxel na grade."""
    if not volumes:
        self.labels, self.label_colors, self._label_occ = None, [], None
        return 0
    lab, cores = rotulos_na_grade(self, volumes, progress)
    self.labels, self.label_colors = lab, cores
    self._label_occ = _suavizar3(lab > 0)
    return int(len(np.unique(lab[lab > 0])))


def _render_estruturas(self, az: float, el: float, size: tuple[int, int], zoom: float = 1.0,
                       pan: tuple[float, float] = (0.0, 0.0), fast: bool = False):
    """Superfície sombreada das estruturas: (RGB uint8 h×w×3, cobertura h×w, profundidade em mm h×w).

    Respeita o recorte (caixa, plano e escultura) do volume, para cortar os órgãos junto com o osso."""
    w_out, h_out = int(size[0]), int(size[1])
    lab = getattr(self, "labels", None)
    vazio = (np.zeros((h_out, w_out, 3), np.uint8), np.zeros((h_out, w_out), np.float32),
             np.full((h_out, w_out), np.nan, np.float32))
    if lab is None or not lab.any():
        return vazio
    w = (w_out + 1) // 2 if fast else w_out
    h = (h_out + 1) // 2 if fast else h_out
    w, h = max(w, 2), max(h, 2)
    u, v, d = rotation(az, el)
    ps = 2 * self.radius / (min(w, h) * zoom)
    st = self.step * (1.5 if fast else 0.75)
    jj = (np.arange(w, dtype=np.float32) - w / 2 + 0.5) * ps + pan[0]
    ii = (np.arange(h, dtype=np.float32) - h / 2 + 0.5) * ps + pan[1]
    origin = (self.center - self.radius * d - self.lo) / self.step
    base = (origin[None, None, :] + jj[None, :, None] * (u / self.step)[None, None, :]
            + ii[:, None, None] * (v / self.step)[None, None, :]).reshape(-1, 3).astype(np.float32)
    dstep = (d * st / self.step).astype(np.float32)
    nsteps = int(2 * self.radius / st) + 1
    gz, gy, gx = self.shape
    zz, yy, xx = np.nonzero(lab)
    caixa = (max(int(xx.min()), self._limits()[0]), min(int(xx.max()), self._limits()[1]),
             max(int(yy.min()), self._limits()[2]), min(int(yy.max()), self._limits()[3]),
             max(int(zz.min()), self._limits()[4]), min(int(zz.max()), self._limits()[5]))
    s_ini, s_fim = self._step_range(caixa, d, st, nsteps)
    flat = lab.reshape(-1)
    mask_flat = None if self.mask is None else self.mask.reshape(-1)
    npx = base.shape[0]
    qual = np.zeros(npx, np.int32)
    prof = np.full(npx, np.nan, np.float32)
    brilho = np.zeros(npx, np.float32)
    alive = np.arange(npx)
    light = -d.astype(np.float32)
    plano = self.plane
    eixo = np.eye(3, dtype=np.float32)
    x0, x1, y0, y1, z0, z1 = caixa
    for s in range(s_ini, s_fim):
        if alive.size == 0:
            break
        p = base[alive] + dstep * s
        xi = np.rint(p[:, 0]).astype(np.int32)
        yi = np.rint(p[:, 1]).astype(np.int32)
        zi = np.rint(p[:, 2]).astype(np.int32)
        ok = (xi >= x0) & (xi <= x1) & (yi >= y0) & (yi <= y1) & (zi >= z0) & (zi <= z1)
        if plano is not None:
            n_, c_ = plano
            ok &= (p[:, 0] * n_[0] + p[:, 1] * n_[1] + p[:, 2] * n_[2]) <= c_
        if not ok.any():
            continue
        idx0 = np.nonzero(ok)[0]
        lin = (zi[idx0] * gy + yi[idx0]) * gx + xi[idx0]
        val = flat[lin]
        if mask_flat is not None:
            val = np.where(mask_flat[lin], val, 0)
        bate = val > 0
        if not bate.any():
            continue
        pix = alive[idx0[bate]]
        pts = p[idx0[bate]]
        g = np.empty((len(pts), 3), np.float32)
        for a in range(3):
            g[:, a] = np.nan_to_num(sample_trilinear(self._label_occ, pts - eixo[a])
                                    - sample_trilinear(self._label_occ, pts + eixo[a]), nan=0.0)
        nrm = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-6)
        b = np.abs(nrm @ light)
        sem_normal = np.linalg.norm(g, axis=1) < 1e-3           # face de um corte: lisa
        brilho[pix] = np.where(sem_normal, 0.6, 0.25 + 0.75 * b)
        qual[pix] = val[bate]
        prof[pix] = s * st
        vivo = np.ones(npx, bool)
        vivo[pix] = False
        alive = alive[vivo[alive]]
    cores = np.array([(0, 0, 0)] + [tuple(c)[:3] for c in self.label_colors], np.float32)
    cores = np.vstack([cores, np.zeros((max(0, 256 - len(cores)), 3), np.float32)])
    rgb = np.clip(cores[qual] * brilho[:, None], 0, 255).astype(np.uint8).reshape(h, w, 3)
    cob = (qual > 0).astype(np.float32).reshape(h, w)
    return (_upscale(rgb, w_out, h_out), _upscale(cob, w_out, h_out),
            _upscale(prof.reshape(h, w), w_out, h_out))


Renderer3D.labels = None
Renderer3D.label_colors = []
Renderer3D._label_occ = None
Renderer3D.set_labels = _definir_estruturas
Renderer3D.render_labels = _render_estruturas


def compor_estruturas(base: np.ndarray, lo: float, hi: float, estr, profundidade_base=None,
                      passo_base: float = 1.0, opacidade: float = 0.85, atras: float = 0.3) -> np.ndarray:
    """Junta a imagem do 3D (cinza do MIP ou RGB do VR) com as estruturas (o retorno de render_labels).

    Na frente do que o 3D mostra: `opacidade`; atrás (o raio do VR já tinha batido em osso antes): `atras`."""
    rgb, cob, prof = estr
    if base.ndim == 2:
        g = np.clip((base - lo) / max(hi - lo, 1e-6), 0, 1) * 255
        base = np.repeat(g[..., None], 3, axis=2)
    out = base.astype(np.float32)
    alfa = cob * opacidade
    if profundidade_base is not None:
        pb = np.asarray(profundidade_base, np.float32)
        if pb.shape != cob.shape:
            pb = _upscale(pb, cob.shape[1], cob.shape[0])
        pb = pb * passo_base
        escondido = np.isfinite(pb) & np.isfinite(prof) & (prof > pb + 2.0)
        alfa = np.where(escondido, cob * atras, alfa)
    out = out * (1 - alfa[..., None]) + rgb.astype(np.float32) * alfa[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)
