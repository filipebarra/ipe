"""0.100.8: contorno da lesão no PET pela borda (gradiente), como o "PET Edge" da MIM.

O limiar em % do SUVmáx (41%) depende do tamanho: numa lesão pequena o efeito de volume parcial derruba o máximo e o
contorno "incha" ou "murcha" conforme o fundo. A borda de verdade está onde o sinal **cai mais depressa** — o máximo do
gradiente —, e isso independe do valor do pico.

Como faz:
1. acha o máximo local perto do clique (o centro da lesão);
2. lança raios do centro em ~260 direções (em mm, então cortes grossos não distorcem) e amostra o PET ao longo de cada
   um (interpolação trilinear);
3. em cada raio, a borda é o ponto de queda mais íngreme **antes** de o perfil voltar a subir (outra lesão, o
   coração, a bexiga) ou chegar ao fundo;
4. o raio de cada direção é filtrado pela mediana das direções vizinhas (um raio que escapou por uma fresta não puxa
   o contorno);
5. **correção do volume parcial**: numa esfera borrada pela resolução do aparelho, a queda mais íngreme fica um
   pouco para dentro da borda verdadeira (2–3% numa lesão de 4 cm, ~17% numa de 1,3 cm). Com o perfil exato de uma
   esfera uniforme borrada por uma gaussiana, cada raio medido volta ao raio verdadeiro. A resolução (FWHM) vem da
   própria lesão quando ela é grande o bastante para mostrá-la (a largura da queda); senão, do valor ajustado
   (padrão 6 mm, o de um PET/TC atual);
6. a lesão é o que fica dentro dessa superfície (forma "estrelada" a partir do centro) e acima de um piso baixo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

N_DIRECOES = 258
PASSO_MM = 0.5
PISO = 0.10          # abaixo de 10% do máximo é fundo, o raio para
SUBIDA = 0.15        # se o perfil volta a subir 15% do máximo acima do mínimo já visto, é outra estrutura
VIZINHOS = 10        # direções vizinhas na mediana do raio
FWHM_PADRAO_MM = 6.0
SUAVE_MM = 2.0        # gaussiana leve no PET antes dos raios (o ruído vence a borda nas lesões pequenas); entra
                      # na correção do volume parcial, então não muda o tamanho medido
_FATOR_TRUNC = 0.691  # variância de uma gaussiana cortada a 20% do pico, em σ²


@dataclass
class Borda:
    centro: tuple                    # (k, j, i) do máximo
    vmax: float
    raios_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))
    direcoes: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    valor_borda: float = 0.0         # mediana do valor do PET na borda
    fracao_borda: float = 0.0        # o mesmo, em fração do máximo
    escapou: float = 0.0             # fração dos raios que chegou ao raio máximo sem achar borda
    raios_gradiente_mm: np.ndarray = field(default_factory=lambda: np.zeros(0))   # antes da correção
    fwhm_mm: float = 0.0             # a resolução usada na correção
    fwhm_da_lesao: bool = False      # True: medida na própria lesão; False: o valor ajustado
    centro_fino: tuple = ()          # o centro dos raios: o centroide do miolo quente (fracionário)


def direcoes(n: int = N_DIRECOES) -> np.ndarray:
    """Pontos quase uniformes na esfera (espiral de Fibonacci), em (z, y, x)."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(phi), np.sin(phi) * np.sin(theta), np.sin(phi) * np.cos(theta)], axis=1)


def trilinear(data: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Valor em pontos (…, 3) em índice (k, j, i) fracionário; fora do volume vale 0."""
    nz, ny, nx = data.shape
    p = pts.reshape(-1, 3)
    fora = (p[:, 0] < 0) | (p[:, 0] > nz - 1) | (p[:, 1] < 0) | (p[:, 1] > ny - 1) | (p[:, 2] < 0) | (p[:, 2] > nx - 1)
    q = np.clip(p, 0, [nz - 1, ny - 1, nx - 1])
    b = np.floor(q).astype(np.int64)
    b = np.minimum(b, [max(nz - 2, 0), max(ny - 2, 0), max(nx - 2, 0)])
    f = q - b
    out = np.zeros(len(p), np.float64)
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                kk = np.minimum(b[:, 0] + dz, nz - 1)
                jj = np.minimum(b[:, 1] + dy, ny - 1)
                ii = np.minimum(b[:, 2] + dx, nx - 1)
                w = (f[:, 0] if dz else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dx else 1 - f[:, 2])
                out += w * data[kk, jj, ii]
    out[fora] = 0.0
    return out.reshape(pts.shape[:-1])


def maximo_local(data: np.ndarray, semente: tuple, voxel_mm: tuple, raio_mm: float = 15.0) -> tuple:
    """O voxel mais quente ligado à semente (subindo pelos vizinhos), até `raio_mm` dela."""
    k, j, i = (int(v) for v in semente)
    dz, dy, dx = voxel_mm
    nz, ny, nx = data.shape
    for _ in range(200):
        a0, a1 = max(0, k - 1), min(nz, k + 2)
        b0, b1 = max(0, j - 1), min(ny, j + 2)
        c0, c1 = max(0, i - 1), min(nx, i + 2)
        cubo = data[a0:a1, b0:b1, c0:c1]
        kk, jj, ii = np.unravel_index(int(np.argmax(cubo)), cubo.shape)
        nk, nj, ni = a0 + int(kk), b0 + int(jj), c0 + int(ii)
        if data[nk, nj, ni] <= data[k, j, i]:
            break
        if np.hypot(np.hypot((nk - semente[0]) * dz, (nj - semente[1]) * dy), (ni - semente[2]) * dx) > raio_mm:
            break
        k, j, i = nk, nj, ni
    return k, j, i


def suavizar_mm(data: np.ndarray, sigma_mm: float, voxel_mm: tuple) -> np.ndarray:
    """Gaussiana exata, separável, de `sigma_mm` em cada eixo (no voxel de cada um)."""
    out = np.asarray(data, np.float32)
    for eixo, v in enumerate(voxel_mm):
        s = sigma_mm / float(v)
        if s < 0.2:
            continue
        n = max(1, int(np.ceil(3 * s)))
        x = np.arange(-n, n + 1)
        k = np.exp(-0.5 * (x / s) ** 2)
        k /= k.sum()
        a = np.moveaxis(out, eixo, -1)
        q = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(n, n)], mode="edge")
        acc = np.zeros_like(a)
        for m, w in enumerate(k):
            acc += w * q[..., m:m + a.shape[-1]]
        out = np.moveaxis(acc, -1, eixo)
    return out


def centroide(data: np.ndarray, c: tuple, voxel_mm: tuple, raio_mm: float = 20.0) -> np.ndarray:
    """O centro de onde saem os raios: o centroide (pesado) do miolo acima de 70% do máximo, ligado a ele. O voxel do
    máximo é, por definição, o mais puxado para cima pelo ruído: raios saindo dele começam com um "tombo" falso."""
    from ipe.imaging.segment import _grow
    dz, dy, dx = voxel_mm
    k, j, i = c
    r = (max(1, int(raio_mm / dz)), max(1, int(raio_mm / dy)), max(1, int(raio_mm / dx)))
    k0, j0, i0 = max(0, k - r[0]), max(0, j - r[1]), max(0, i - r[2])
    caixa = data[k0:k + r[0] + 1, j0:j + r[1] + 1, i0:i + r[2] + 1].astype(np.float64)
    v = float(data[c])
    miolo = _grow(caixa >= 0.7 * v, (k - k0, j - j0, i - i0))
    w = np.where(miolo, caixa - 0.7 * v, 0.0)
    if w.sum() <= 0:
        return np.asarray(c, float)
    kk, jj, ii = np.nonzero(w)
    p = w[kk, jj, ii]
    return np.array([k0 + np.average(kk, weights=p), j0 + np.average(jj, weights=p), i0 + np.average(ii, weights=p)])


def _erf(x: np.ndarray) -> np.ndarray:
    """erf vetorizado (Abramowitz–Stegun 7.1.26, erro < 1,5e-7)."""
    x = np.asarray(x, np.float64)
    sgn = np.sign(x)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * \
        np.exp(-a * a)
    return sgn * y


def perfil_esfera(r: np.ndarray, raio: float, sigma: float) -> np.ndarray:
    """Perfil radial de uma esfera uniforme (valor 1, fundo 0) de `raio` borrada por uma gaussiana 3D de `sigma`."""
    r = np.maximum(np.asarray(r, np.float64), 1e-6)
    s2 = np.sqrt(2.0) * sigma
    return 0.5 * (_erf((raio + r) / s2) + _erf((raio - r) / s2)) - sigma / (r * np.sqrt(2 * np.pi)) * (
        np.exp(-(raio - r) ** 2 / (2 * sigma ** 2)) - np.exp(-(raio + r) ** 2 / (2 * sigma ** 2)))


def tabela_raio(sigma: float, raio_max_mm: float = 80.0) -> tuple[np.ndarray, np.ndarray]:
    """(raio da queda mais íngreme, raio verdadeiro) para esferas de 0,3σ a `raio_max_mm`."""
    reais = np.linspace(0.3 * sigma, raio_max_mm, 400)
    r = np.linspace(0, raio_max_mm + 4 * sigma, 4000)
    medidos = np.empty_like(reais)
    for n, R in enumerate(reais):
        medidos[n] = r[int(np.argmin(np.gradient(perfil_esfera(r, R, sigma), r)))]
    return np.maximum.accumulate(medidos), reais


def corrigir_raios(raios: np.ndarray, sigma: float) -> np.ndarray:
    medidos, reais = tabela_raio(sigma, max(80.0, float(np.max(raios)) + 10))
    return np.interp(raios, medidos, reais)


def _suave(p: np.ndarray, sigma_mm: float) -> np.ndarray:
    """Gaussiana ao longo do raio. A interpolação trilinear deixa o perfil em retas entre os voxels (a derivada vira
    degraus e o "ponto de queda" cairia em qualquer lugar do degrau), e o ruído do PET derruba a derivada num pixel ao
    acaso; uma gaussiana da ordem de meio voxel resolve os dois."""
    n = max(1, int(np.ceil(3 * sigma_mm / PASSO_MM)))
    x = np.arange(-n, n + 1) * PASSO_MM
    k = np.exp(-0.5 * (x / sigma_mm) ** 2)
    k /= k.sum()
    # borda: repete o primeiro valor (o centro) e o último
    q = np.pad(p, ((0, 0), (n, n)), mode="edge")
    out = np.zeros_like(p)
    for a, w in enumerate(k):
        out += w * q[:, a:a + p.shape[1]]
    return out


def achar_borda(data: np.ndarray, semente: tuple, voxel_mm: tuple, raio_max_mm: float = 60.0,
                n: int = N_DIRECOES, fwhm_mm: float = FWHM_PADRAO_MM, corrigir: bool = True) -> Borda:
    dz, dy, dx = (float(v) for v in voxel_mm)
    c = maximo_local(data, semente, (dz, dy, dx))
    vmax = float(data[c])
    # a conta corre num recorte suavizado (o tamanho volta pela correção, que sabe da suavização)
    nz, ny, nx = data.shape
    folga = raio_max_mm + 4 * SUAVE_MM
    rk, rj, ri = int(folga / dz) + 2, int(folga / dy) + 2, int(folga / dx) + 2
    k0, j0, i0 = max(0, c[0] - rk), max(0, c[1] - rj), max(0, c[2] - ri)
    rec = suavizar_mm(data[k0:c[0] + rk + 1, j0:c[1] + rj + 1, i0:c[2] + ri + 1], SUAVE_MM, (dz, dy, dx))
    canto = np.array([k0, j0, i0], float)
    c_rec = (c[0] - k0, c[1] - j0, c[2] - i0)
    dirs = direcoes(n)
    t = np.arange(0.0, raio_max_mm + PASSO_MM, PASSO_MM)
    escala = np.array([dz, dy, dx])
    cf = centroide(rec, c_rec, (dz, dy, dx))
    pts = cf[None, None, :] + (dirs[:, None, :] * t[None, :, None]) / escala
    sigma_k = 0.5 * max(dz, dy, dx)
    perfil = _suave(trilinear(rec, pts), sigma_k)
    # média com as direções vizinhas antes da derivada: o ruído cai, e numa lesão "estrelada" vizinhos têm a mesma
    # borda (o ruído puxava o ponto de queda para dentro: um degrau de ruído antes da borda vencia a borda)
    viz = np.argsort(-(dirs @ dirs.T), axis=1)[:, :VIZINHOS + 1]
    perfil = perfil[viz].mean(axis=1)
    raios = np.full(n, raio_max_mm)
    largura = np.full(n, np.nan)
    escapou = np.zeros(n, bool)
    if vmax <= 0:
        return Borda(c, vmax, raios * 0, dirs)
    deriv = np.gradient(perfil, PASSO_MM, axis=1)
    for d in range(n):
        p = perfil[d]
        minimo = np.minimum.accumulate(p)
        fim = len(p)
        abaixo = np.flatnonzero(p < PISO * vmax)
        if abaixo.size:
            fim = min(fim, int(abaixo[0]) + 1)
        sobe = np.flatnonzero(p - minimo > SUBIDA * vmax)
        if sobe.size:
            fim = min(fim, int(sobe[0]))
        if fim < 3:
            raios[d] = t[min(1, len(t) - 1)]
            continue
        # a queda mais íngreme no trecho que desce; o ponto de borda é o meio dela
        g = deriv[d, :fim]
        pico = int(np.argmin(g))
        # a posição fina pela parábola nos 3 pontos em volta do pico
        fino = 0.0
        if 0 < pico < fim - 1:
            y0, y1, y2 = g[pico - 1], g[pico], g[pico + 1]
            den = y0 - 2 * y1 + y2
            if den > 0:
                fino = float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5))
        raios[d] = t[pico] + fino * PASSO_MM
        # a largura da queda (σ), no trecho acima de 20% do pico, de um lado e do outro
        q = -g
        if q[pico] > 0:
            a = pico
            while a > 0 and q[a - 1] > 0.2 * q[pico]:
                a -= 1
            z = pico
            while z < fim - 1 and q[z + 1] > 0.2 * q[pico]:
                z += 1
            if a > 0 and z < fim - 1:
                w = q[a:z + 1]
                largura[d] = float(np.sqrt(np.sum(w * (t[a:z + 1] - t[pico]) ** 2) / np.sum(w) / _FATOR_TRUNC))
        escapou[d] = not abaixo.size and not sobe.size and fim == len(p)
    # mediana entre as direções vizinhas
    raios = np.median(raios[viz], axis=1)
    brutos = raios.copy()
    sigma = float(np.hypot(float(fwhm_mm) / 2.3548, SUAVE_MM))
    da_lesao = False
    if np.isfinite(largura).sum() > n // 3:
        # a largura da queda tem também o borrão do que se fez aqui (a gaussiana do raio e a interpolação), que
        # alarga a queda mas não a desloca: sai da conta
        s_med = float(np.nanmedian(largura))
        s_psf = float(np.sqrt(max(s_med ** 2 - sigma_k ** 2 - np.mean([dz, dy, dx]) ** 2 / 12.0,
                                  (0.5 * min(dz, dy, dx)) ** 2)))
        # a largura só mostra a resolução quando a lesão é bem maior que ela
        if np.median(raios) > 3.0 * s_med:
            sigma, da_lesao = s_psf, True
    if corrigir and sigma > 0:
        raios = corrigir_raios(raios, sigma)
    bordas = cf[None, :] + dirs * raios[:, None] / escala
    vb = trilinear(rec, bordas[:, None, :])[:, 0]
    cf = cf + canto
    return Borda(c, vmax, raios, dirs, float(np.median(vb)), float(np.median(vb) / vmax), float(escapou.mean()),
                 brutos, float(np.sqrt(max(sigma ** 2 - SUAVE_MM ** 2, 0.0))) * 2.3548, da_lesao,
                 tuple(float(x) for x in cf))


def mascara(data: np.ndarray, b: Borda, voxel_mm: tuple) -> tuple[np.ndarray, tuple]:
    """A máscara (recortada) dos voxels dentro da superfície da borda, e o canto (k, j, i) do recorte."""
    dz, dy, dx = (float(v) for v in voxel_mm)
    rmax = float(b.raios_mm.max()) if b.raios_mm.size else 0.0
    nz, ny, nx = data.shape
    k, j, i = b.centro
    rk, rj, ri = int(np.ceil(rmax / dz)) + 1, int(np.ceil(rmax / dy)) + 1, int(np.ceil(rmax / dx)) + 1
    k0, k1 = max(0, k - rk), min(nz, k + rk + 1)
    j0, j1 = max(0, j - rj), min(ny, j + rj + 1)
    i0, i1 = max(0, i - ri), min(nx, i + ri + 1)
    kk, jj, ii = np.meshgrid(np.arange(k0, k1), np.arange(j0, j1), np.arange(i0, i1), indexing="ij")
    fk, fj, fi = b.centro_fino or b.centro
    v = np.stack([(kk - fk) * dz, (jj - fj) * dy, (ii - fi) * dx], axis=-1).reshape(-1, 3)
    dist = np.linalg.norm(v, axis=1)
    dentro = np.zeros(len(v), bool)
    perto = dist <= rmax + 1e-6
    idx = np.flatnonzero(perto)
    if idx.size:
        u = v[idx] / np.maximum(dist[idx], 1e-9)[:, None]
        # direção mais próxima em blocos (memória)
        r = np.empty(idx.size)
        for a in range(0, idx.size, 20000):
            r[a:a + 20000] = b.raios_mm[np.argmax(u[a:a + 20000] @ b.direcoes.T, axis=1)]
        dentro[idx] = dist[idx] <= r
    m = dentro.reshape(kk.shape)
    m &= data[k0:k1, j0:j1, i0:i1] >= PISO * b.vmax
    m[k - k0, j - j0, i - i0] = True
    return m, (k0, j0, i0)
