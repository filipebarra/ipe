"""Exportar modelos 3D: OBJ, PLY, glTF/GLB, 3MF e STL — com um laudo da malha.

O STL continua em `surface.py` (é o formato mais antigo e o mais usado em impressão).
Aqui entram os outros quatro, o relatório de qualidade da malha e a redução de triângulos.

Cada peça (`Part`) tem nome e cor, então um arquivo só pode levar osso, vaso e lesão
separados — coisa que o STL não sabe fazer.

Sistema de coordenadas: tudo sai em **milímetros do paciente (LPS)**, que é o que os
programas de planejamento e os fatiadores esperam. A exceção é o GLB, formato de
apresentação: ele é girado para Y para cima, senão o modelo abre deitado no visualizador
do Windows e no PowerPoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FORMATOS = [("stl", "STL binário (impressão 3D, universal)"),
            ("obj", "OBJ + MTL (Blender, MeshLab, Slicer)"),
            ("ply", "PLY com cor por vértice"),
            ("glb", "glTF/GLB (abre no navegador, no Windows e no PowerPoint)"),
            ("3mf", "3MF (impressão 3D moderna, com escala e cor)")]
EXTENSAO = {"stl": ".stl", "obj": ".obj", "ply": ".ply", "glb": ".glb", "3mf": ".3mf"}
COM_COR = {"obj", "ply", "glb", "3mf"}
PALETA = [(222, 220, 210), (200, 70, 60), (70, 130, 200), (230, 180, 70),
          (120, 190, 120), (180, 120, 200)]


@dataclass
class Part:
    """Uma estrutura do modelo: malha em mm do paciente, com nome e cor."""
    name: str
    verts: np.ndarray
    faces: np.ndarray
    color: tuple = (222, 220, 210)
    opacity: float = 1.0

    @property
    def n_faces(self) -> int:
        return int(len(self.faces))

    @property
    def n_verts(self) -> int:
        return int(len(self.verts))


def cor_da_vez(i: int) -> tuple:
    return PALETA[i % len(PALETA)]


# ---------------------------------------------------------------- relatório da malha
@dataclass
class MeshReport:
    """O que a malha é — e o que falta para ela poder ser impressa."""
    faces: int = 0
    verts: int = 0
    size_mm: tuple = (0.0, 0.0, 0.0)
    volume_ml: float = 0.0
    closed: bool | None = None          # None = não dava para conferir
    outward: bool | None = None
    pieces: int | None = None
    open_edges: int = 0

    @property
    def printable(self) -> bool:
        return bool(self.faces and self.closed and self.outward is not False)

    def lines(self) -> list:
        """Frases curtas para a tela, na ordem em que interessam."""
        d = self.size_mm
        saida = [f"{self.faces} triângulos e {self.verts} vértices",
                 f"Tamanho: {d[0]:.0f} × {d[1]:.0f} × {d[2]:.0f} mm",
                 f"Volume fechado: {self.volume_ml:.1f} mL"]
        if self.closed is None:
            saida.append("Malha grande demais para conferir se está fechada")
        elif self.closed:
            saida.append("Malha fechada — pode imprimir")
        else:
            saida.append(f"Malha aberta: {self.open_edges} aresta(s) sem par — o fatiador pode recusar")
        if self.outward is False:
            saida.append("As faces estão viradas para dentro")
        if self.pieces and self.pieces > 1:
            saida.append(f"{self.pieces} peças soltas — considere manter só a maior")
        return saida


def report(verts: np.ndarray, faces: np.ndarray, limite: int = 400_000) -> MeshReport:
    """Confere a malha: tamanho, volume, se está fechada, para que lado olham as faces."""
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    r = MeshReport(faces=len(f), verts=len(v))
    if not len(f) or not len(v):
        return r
    r.size_mm = tuple(float(x) for x in (v.max(axis=0) - v.min(axis=0)))
    p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    seis = float(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum())
    r.volume_ml = abs(seis) / 6.0 / 1000.0
    r.outward = seis > 0
    if len(f) > limite:
        return r
    arestas = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]], axis=0)
    arestas = np.sort(arestas, axis=1)
    _u, contagem = np.unique(arestas, axis=0, return_counts=True)
    r.open_edges = int((contagem != 2).sum())
    r.closed = r.open_edges == 0
    r.pieces = _pecas(len(v), f)
    return r


def _pecas(n: int, faces: np.ndarray) -> int:
    """Quantas peças soltas a malha tem (união e busca sobre as arestas)."""
    pai = list(range(n))

    def achar(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    for a, b, c in faces:
        for u, w in ((int(a), int(b)), (int(b), int(c))):
            ru, rw = achar(u), achar(w)
            if ru != rw:
                pai[ru] = rw
    usados = np.unique(faces)
    return len({achar(int(i)) for i in usados})


def masks_from_seg(vol, obj) -> dict:
    """Máscara 3D por segmento, a partir de um DICOM SEG guardado no exame.

    Cada quadro do SEG traz a posição em mm; a fatia é achada pelo `patient_to_voxel` do
    volume. Quadro cujo tamanho não bate com a série é de outra série — fica de fora, em
    vez de entrar torto.
    """
    nz, ny, nx = vol.data.shape
    saida: dict = {}
    for mf in getattr(obj, "masks", []) or []:
        if mf.position is None or mf.mask is None:
            continue
        m = np.asarray(mf.mask, dtype=bool)
        try:
            i, j, k = vol.patient_to_voxel(np.asarray(mf.position, dtype=float))
        except Exception:  # noqa: BLE001
            continue
        k, i0, j0 = int(round(float(k))), int(round(float(i))), int(round(float(j)))
        if not 0 <= k < nz:
            continue
        h, w = m.shape
        # o quadro pode ser o recorte do segmento (0.98): o canto dele diz onde ele começa.
        # Quadro que não cabe na grade da série é de outra série — fica de fora, em vez de entrar torto.
        if i0 < 0 or j0 < 0 or j0 + h > ny or i0 + w > nx:
            continue
        rotulo = mf.label or "Segmento"
        alvo = saida.get(rotulo)
        if alvo is None:
            alvo = saida[rotulo] = np.zeros((nz, ny, nx), bool)
        alvo[k, j0:j0 + h, i0:i0 + w] |= m
    return {k: v for k, v in saida.items() if v.any()}


# ---------------------------------------------------------------- redução
def decimate(verts: np.ndarray, faces: np.ndarray, fator: float) -> tuple:
    """Menos triângulos, juntando vértices que caem na mesma casinha de uma grade.

    `fator` é a fração de triângulos que se quer manter (0,3 = 30%). É o método mais
    simples que funciona bem em superfície médica: rápido, previsível e sem dependência
    nova. Não preserva quina viva — para peça anatômica não faz falta.
    """
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    if not len(f) or fator >= 0.999:
        return verts, faces
    fator = float(np.clip(fator, 0.01, 1.0))
    tamanho = v.max(axis=0) - v.min(axis=0)
    maior = float(max(tamanho.max(), 1e-6))
    # o número de células cai com o quadrado do passo (a malha é uma superfície)
    lado = maior / max(2.0, (len(v) * fator) ** 0.5)
    chave = np.floor((v - v.min(axis=0)) / lado).astype(np.int64)
    _u, inverso, _c = np.unique(chave, axis=0, return_inverse=True, return_counts=True)
    n = int(inverso.max()) + 1
    soma = np.zeros((n, 3), np.float64)
    np.add.at(soma, inverso, v)
    quantos = np.bincount(inverso, minlength=n).astype(np.float64)[:, None]
    novos = (soma / np.maximum(quantos, 1)).astype(np.float32)
    nf = inverso[f]
    bom = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
    nf = nf[bom]
    if not len(nf):
        return verts, faces
    ordenado = np.sort(nf, axis=1)
    _uu, primeiro = np.unique(ordenado, axis=0, return_index=True)
    nf = nf[np.sort(primeiro)]
    usados, remap = np.unique(nf, return_inverse=True)
    return novos[usados], remap.reshape(-1, 3).astype(np.int32)


# ---------------------------------------------------------------- escrita
def save(path: Path | str, parts: list, fmt: str = "", name: str = "Ipê") -> list:
    """Grava o modelo. Devolve os arquivos criados (o STL pode virar mais de um)."""
    path = Path(path)
    fmt = (fmt or path.suffix.lstrip(".") or "stl").lower()
    uteis = [p for p in parts if p is not None and len(getattr(p, "faces", []))]
    if not uteis:
        raise ValueError("Não há malha para gravar: a superfície ficou vazia.")
    from ipe.imaging import mesh_fmt as F
    if fmt == "stl":
        return _write_stl(path, uteis, name)
    if fmt == "obj":
        return F._write_obj(path, uteis, name)
    if fmt == "ply":
        return [F._write_ply(path, uteis)]
    if fmt == "glb":
        return [F._write_glb(path, uteis, name)]
    if fmt == "3mf":
        return [F._write_3mf(path, uteis, name)]
    raise ValueError(f"Formato desconhecido: {fmt}")


def para_gltf(v):
    """Reexportado para quem só usa `mesh_io` (a conversão mora em `mesh_fmt`)."""
    from ipe.imaging.mesh_fmt import para_gltf as conv
    return conv(v)


def _write_stl(path: Path, parts: list, name: str) -> list:
    """STL não guarda nome nem cor: com mais de uma peça, sai um arquivo por peça."""
    from ipe.imaging.mesh_fmt import limpa_nome as _limpa
    from ipe.imaging.surface import write_stl
    if len(parts) == 1:
        return [write_stl(path, parts[0].verts, parts[0].faces, name)]
    saida = []
    for p in parts:
        alvo = path.with_name(f"{path.stem}_{_limpa(p.name)}{path.suffix or '.stl'}")
        saida.append(write_stl(alvo, p.verts, p.faces, p.name))
    return saida


