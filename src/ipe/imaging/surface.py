"""Superfície 3D (malha) a partir de uma máscara ou de um limiar, e arquivo STL.

Usa "surface nets": cada cubo de 2×2×2 voxels que fica na fronteira ganha um vértice no meio
das travessias, e os vértices vizinhos são ligados em quadriláteros. É simples, fecha a
superfície e dá uma malha bem mais lisa que a de cubinhos — sem precisar de scipy.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def _downsample(mask: np.ndarray, passo: int) -> np.ndarray:
    if passo <= 1:
        return mask
    return mask[::passo, ::passo, ::passo]


def mesh_from_mask(mask: np.ndarray, spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
                   origin: tuple[float, float, float] = (0.0, 0.0, 0.0), step: int = 1,
                   smooth: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Vértices (n, 3) em mm e triângulos (m, 3) de uma máscara booleana (nz, ny, nx).

    `spacing` é (dz, dy, dx). `step` reduz a máscara antes (malha mais leve).
    """
    m = np.ascontiguousarray(_downsample(np.asarray(mask, dtype=bool), max(1, int(step))))
    if m.ndim != 3 or m.size == 0 or not m.any():
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)
    dz, dy, dx = (float(s) * max(1, int(step)) for s in spacing)
    dentro = np.pad(m, 1)                       # moldura de fora, para fechar a superfície
    nz, ny, nx = dentro.shape
    # soma dos 8 cantos de cada célula: 0 = fora, 8 = dentro, entre isso = fronteira
    c = dentro.astype(np.uint8)
    soma = (c[:-1, :-1, :-1] + c[:-1, :-1, 1:] + c[:-1, 1:, :-1] + c[:-1, 1:, 1:] +
            c[1:, :-1, :-1] + c[1:, :-1, 1:] + c[1:, 1:, :-1] + c[1:, 1:, 1:])
    fronteira = (soma > 0) & (soma < 8)
    if not fronteira.any():
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)
    idx = -np.ones(soma.shape, dtype=np.int64)
    kk, jj, ii = np.nonzero(fronteira)
    idx[kk, jj, ii] = np.arange(kk.size)
    # vértice no centro da célula, puxado para o lado que tem massa (média dos cantos dentro)
    pesos = np.stack([c[:-1, :-1, :-1], c[:-1, :-1, 1:], c[:-1, 1:, :-1], c[:-1, 1:, 1:],
                      c[1:, :-1, :-1], c[1:, :-1, 1:], c[1:, 1:, :-1], c[1:, 1:, 1:]], axis=-1)
    cantos = np.array([(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1),
                       (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)], dtype=np.float32)
    p = pesos[kk, jj, ii].astype(np.float32)            # (n, 8)
    total = np.maximum(p.sum(axis=1, keepdims=True), 1.0)
    desloc = (p @ cantos) / total                        # (n, 3) em (dk, dj, di)
    base = np.stack([kk, jj, ii], axis=1).astype(np.float32) + desloc
    verts = np.empty((kk.size, 3), np.float32)
    verts[:, 0] = (base[:, 2] - 1.0) * dx + origin[2]     # x
    verts[:, 1] = (base[:, 1] - 1.0) * dy + origin[1]     # y
    verts[:, 2] = (base[:, 0] - 1.0) * dz + origin[0]     # z

    tris: list[np.ndarray] = []
    # para cada aresta do grid onde o dentro/fora muda, um quadrilátero com as 4 células vizinhas
    for eixo in (0, 1, 2):
        a = dentro
        if eixo == 0:
            muda = a[:-1, :, :] != a[1:, :, :]
            kz, jy, ix = np.nonzero(muda)
            ok = (jy > 0) & (ix > 0) & (jy < ny - 1) & (ix < nx - 1)
            kz, jy, ix = kz[ok], jy[ok], ix[ok]
            q = [idx[kz, jy - 1, ix - 1], idx[kz, jy - 1, ix], idx[kz, jy, ix], idx[kz, jy, ix - 1]]
            frente = a[kz + 1, jy, ix]
        elif eixo == 1:
            muda = a[:, :-1, :] != a[:, 1:, :]
            kz, jy, ix = np.nonzero(muda)
            ok = (kz > 0) & (ix > 0) & (kz < nz - 1) & (ix < nx - 1)
            kz, jy, ix = kz[ok], jy[ok], ix[ok]
            q = [idx[kz - 1, jy, ix - 1], idx[kz - 1, jy, ix], idx[kz, jy, ix], idx[kz, jy, ix - 1]]
            frente = a[kz, jy + 1, ix]
        else:
            muda = a[:, :, :-1] != a[:, :, 1:]
            kz, jy, ix = np.nonzero(muda)
            ok = (kz > 0) & (jy > 0) & (kz < nz - 1) & (jy < ny - 1)
            kz, jy, ix = kz[ok], jy[ok], ix[ok]
            q = [idx[kz - 1, jy - 1, ix], idx[kz - 1, jy, ix], idx[kz, jy, ix], idx[kz, jy - 1, ix]]
            frente = a[kz, jy, ix + 1]
        if not len(kz):
            continue
        quad = np.stack(q, axis=1)
        bom = (quad >= 0).all(axis=1)
        quad, frente = quad[bom], frente[bom]
        if not quad.size:
            continue
        # Orienta as faces para fora (normal saindo do que está dentro).
        # A ordem base do quadrilátero dá normal +z no eixo 0, −y no eixo 1 e +x no eixo 2.
        # `frente` diz se o voxel do lado de lá (no sentido do eixo) está dentro; se estiver,
        # o fora é para trás, e a normal tem que apontar no sentido contrário ao do eixo.
        # Sem distinguir por eixo, dois dos três saíam invertidos: a malha fechava, mas o
        # volume com sinal dava 1/3 do certo e o fatiador via a peça do avesso.
        inverte = frente.astype(bool) if eixo in (0, 2) else ~frente.astype(bool)
        quad[inverte] = quad[inverte][:, ::-1]
        tris.append(np.stack([quad[:, 0], quad[:, 1], quad[:, 2]], axis=1))
        tris.append(np.stack([quad[:, 0], quad[:, 2], quad[:, 3]], axis=1))
    if not tris:
        return verts, np.zeros((0, 3), np.int32)
    faces = np.concatenate(tris, axis=0).astype(np.int32)
    if smooth > 0:
        verts = smooth_mesh(verts, faces, int(smooth))
    return verts, faces


def mesh_in_patient(vol, mask: np.ndarray, offset: tuple[int, int, int] = (0, 0, 0),
                   step: int = 1, smooth: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Malha em milímetros do paciente, a partir de uma máscara (inteira ou de um recorte)."""
    verts, faces = mesh_from_mask(mask, (1.0, 1.0, 1.0), (0.0, 0.0, 0.0), step, smooth)
    if not len(verts):
        return verts, faces
    k0, j0, i0 = offset
    ijk = np.stack([verts[:, 0] + i0, verts[:, 1] + j0, verts[:, 2] + k0], axis=1)
    m = vol.matrix().astype(np.float32)
    return (np.asarray(vol.origin, dtype=np.float32) + ijk @ m.T).astype(np.float32), faces


def smooth_mesh(verts: np.ndarray, faces: np.ndarray, passes: int = 2) -> np.ndarray:
    """Suavização de Laplace: cada vértice caminha um pouco para a média dos vizinhos."""
    if not len(faces) or passes <= 0:
        return verts
    a = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2]])
    b = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0]])
    arestas = np.concatenate([np.stack([a, b], 1), np.stack([b, a], 1)], axis=0)
    out = verts.astype(np.float32).copy()
    for _ in range(passes):
        soma = np.zeros_like(out)
        np.add.at(soma, arestas[:, 0], out[arestas[:, 1]])
        grau = np.bincount(arestas[:, 0], minlength=len(out)).astype(np.float32)[:, None]
        media = np.where(grau > 0, soma / np.maximum(grau, 1), out)
        out = out * 0.4 + media * 0.6
    return out


def mask_from_threshold(data: np.ndarray, lo: float, hi: float | None = None) -> np.ndarray:
    """Máscara por faixa de valores (ex.: osso na TC a partir de 200 HU)."""
    m = data >= float(lo)
    if hi is not None:
        m &= data <= float(hi)
    return m


def keep_largest(mask: np.ndarray) -> np.ndarray:
    """Só a maior peça conectada — tira as ilhas soltas (mesa, ruído)."""
    from ipe.imaging.segment import _grow
    if not mask.any():
        return mask
    idx = np.argwhere(mask)
    # semente no centro de massa, puxada para o voxel marcado mais próximo
    centro = idx.mean(axis=0)
    seed = tuple(int(v) for v in idx[np.argmin(((idx - centro) ** 2).sum(axis=1))])
    try:
        return _grow(mask, seed)
    except Exception:  # noqa: BLE001
        log.exception("maior componente")
        return mask


def volume_ml(mask: np.ndarray, spacing: tuple[float, float, float]) -> float:
    dz, dy, dx = spacing
    return float(mask.sum()) * dz * dy * dx / 1000.0


def write_stl(path: Path | str, verts: np.ndarray, faces: np.ndarray, name: str = "Ipê") -> Path:
    """Grava STL binário (o formato que as impressoras 3D e os programas de planejamento leem)."""
    path = Path(path)
    v = np.asarray(verts, dtype=np.float32)
    f = np.asarray(faces, dtype=np.int64)
    if not len(f):
        raise ValueError("A superfície ficou vazia.")
    p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(p1 - p0, p2 - p0)
    comp = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.where(comp > 0, n / np.maximum(comp, 1e-12), 0.0).astype(np.float32)
    with open(path, "wb") as fh:
        fh.write(name.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(f)))
        bloco = np.zeros((len(f), 12), dtype=np.float32)
        bloco[:, 0:3] = n
        bloco[:, 3:6] = p0
        bloco[:, 6:9] = p1
        bloco[:, 9:12] = p2
        dados = np.zeros((len(f), 50), dtype=np.uint8)
        dados[:, :48] = bloco.view(np.uint8).reshape(len(f), 48)
        fh.write(dados.tobytes())
    return path


def read_stl_header(path: Path | str) -> int:
    """Quantos triângulos tem um STL binário (para conferir o que foi gravado)."""
    with open(path, "rb") as fh:
        fh.read(80)
        return struct.unpack("<I", fh.read(4))[0]
