"""Escrita dos formatos de modelo 3D: OBJ+MTL, PLY, glTF/GLB e 3MF.

Só formato de arquivo — nenhum texto de tela mora aqui, por isso o extrator de idiomas
pula este arquivo. O que o usuário lê (nome dos formatos, laudo da malha) fica em
`mesh_io.py`.

Coordenadas: milímetros do paciente (LPS) em todos, menos no GLB, que é girado para Y
para cima — senão o modelo abre deitado no visualizador do Windows e no PowerPoint.
"""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import numpy as np


def limpa_nome(nome: str) -> str:
    seguro = "".join(c if c.isalnum() or c in " -_." else "_" for c in str(nome or "peca"))
    return seguro.strip() or "peca"


def _write_obj(path: Path, parts: list, name: str) -> list:
    mtl = path.with_suffix(".mtl")
    linhas = [f"# {name} — Ipê (milímetros do paciente, LPS)", f"mtllib {mtl.name}"]
    mats = [f"# {name}"]
    base = 1
    for i, p in enumerate(parts):
        v = np.asarray(p.verts, dtype=np.float64)
        f = np.asarray(p.faces, dtype=np.int64) + base
        chave = f"{limpa_nome(p.name)}_{i}"
        r, g, b = (c / 255.0 for c in p.color)
        mats += [f"newmtl {chave}", f"Kd {r:.4f} {g:.4f} {b:.4f}", "Ka 0 0 0", "Ks 0.1 0.1 0.1",
                 f"d {float(p.opacity):.3f}", ""]
        linhas.append(f"o {chave}")
        linhas.append(f"usemtl {chave}")
        linhas += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in v]
        linhas += [f"f {a} {bb} {c}" for a, bb, c in f]
        base += len(v)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    mtl.write_text("\n".join(mats) + "\n", encoding="utf-8")
    return [path, mtl]


def _write_ply(path: Path, parts: list) -> Path:
    vs, fs, cs, base = [], [], [], 0
    for p in parts:
        v = np.asarray(p.verts, dtype=np.float32)
        vs.append(v)
        fs.append(np.asarray(p.faces, dtype=np.int32) + base)
        cs.append(np.tile(np.array(p.color, np.uint8), (len(v), 1)))
        base += len(v)
    v = np.concatenate(vs)
    f = np.concatenate(fs)
    c = np.concatenate(cs)
    cabecalho = ("ply\nformat binary_little_endian 1.0\n"
                 "comment Ipê — milímetros do paciente (LPS)\n"
                 f"element vertex {len(v)}\n"
                 "property float x\nproperty float y\nproperty float z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                 f"element face {len(f)}\n"
                 "property list uchar int vertex_indices\nend_header\n")
    linha = np.zeros(len(v), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                    ("r", "u1"), ("g", "u1"), ("b", "u1")])
    linha["x"], linha["y"], linha["z"] = v[:, 0], v[:, 1], v[:, 2]
    linha["r"], linha["g"], linha["b"] = c[:, 0], c[:, 1], c[:, 2]
    tri = np.zeros(len(f), dtype=[("n", "u1"), ("a", "<i4"), ("b", "<i4"), ("c", "<i4")])
    tri["n"] = 3
    tri["a"], tri["b"], tri["c"] = f[:, 0], f[:, 1], f[:, 2]
    with open(path, "wb") as fh:
        fh.write(cabecalho.encode("utf-8"))
        fh.write(linha.tobytes())
        fh.write(tri.tobytes())
    return path


def para_gltf(v: np.ndarray) -> np.ndarray:
    """LPS (x esquerda, y posterior, z superior) -> glTF (Y para cima, olhando de frente)."""
    saida = np.empty_like(v)
    saida[:, 0] = v[:, 0]
    saida[:, 1] = v[:, 2]
    saida[:, 2] = -v[:, 1]
    return saida


def _write_glb(path: Path, parts: list, name: str) -> Path:
    buf = bytearray()
    views, acessores, malhas, materiais, nos = [], [], [], [], []

    def pedaco(dados: bytes) -> int:
        while len(buf) % 4:
            buf.append(0)
        ini = len(buf)
        buf.extend(dados)
        views.append({"buffer": 0, "byteOffset": ini, "byteLength": len(dados)})
        return len(views) - 1

    for i, p in enumerate(parts):
        v = para_gltf(np.asarray(p.verts, dtype=np.float32))
        f = np.asarray(p.faces, dtype=np.uint32)
        iv = pedaco(np.ascontiguousarray(v).tobytes())
        acessores.append({"bufferView": iv, "componentType": 5126, "count": int(len(v)),
                          "type": "VEC3",
                          "min": [float(x) for x in v.min(axis=0)],
                          "max": [float(x) for x in v.max(axis=0)]})
        a_pos = len(acessores) - 1
        ii = pedaco(np.ascontiguousarray(f.reshape(-1)).tobytes())
        acessores.append({"bufferView": ii, "componentType": 5125, "count": int(f.size),
                          "type": "SCALAR"})
        a_idx = len(acessores) - 1
        r, g, b = (c / 255.0 for c in p.color)
        materiais.append({"name": p.name or f"peça {i + 1}",
                          "pbrMetallicRoughness": {
                              "baseColorFactor": [r, g, b, float(p.opacity)],
                              "metallicFactor": 0.0, "roughnessFactor": 0.75},
                          "doubleSided": True,
                          "alphaMode": "BLEND" if p.opacity < 0.999 else "OPAQUE"})
        malhas.append({"name": p.name or f"peça {i + 1}",
                       "primitives": [{"attributes": {"POSITION": a_pos}, "indices": a_idx,
                                       "material": len(materiais) - 1}]})
        nos.append({"mesh": len(malhas) - 1, "name": p.name or f"peça {i + 1}"})
    while len(buf) % 4:
        buf.append(0)
    gltf = {"asset": {"version": "2.0", "generator": f"Ipê — {name}"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nos)))}],
            "nodes": nos, "meshes": malhas, "materials": materiais,
            "accessors": acessores, "bufferViews": views,
            "buffers": [{"byteLength": len(buf)}]}
    texto = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    texto += b" " * ((4 - len(texto) % 4) % 4)
    total = 12 + 8 + len(texto) + 8 + len(buf)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(texto), 0x4E4F534A))
        fh.write(texto)
        fh.write(struct.pack("<II", len(buf), 0x004E4942))
        fh.write(bytes(buf))
    return path


TIPOS_3MF = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

RELS_3MF = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" \
Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""


def _write_3mf(path: Path, parts: list, name: str) -> Path:
    cores = "".join(f'<base name="{limpa_nome(p.name)}" '
                    f'displaycolor="#{p.color[0]:02X}{p.color[1]:02X}{p.color[2]:02X}FF"/>'
                    for p in parts)
    objetos, itens = [], []
    for i, p in enumerate(parts):
        v = np.asarray(p.verts, dtype=np.float64)
        f = np.asarray(p.faces, dtype=np.int64)
        vs = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in v)
        ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
        oid = i + 2
        objetos.append(f'<object id="{oid}" type="model" pid="1" pindex="{i}" '
                       f'name="{limpa_nome(p.name)}"><mesh><vertices>{vs}</vertices>'
                       f'<triangles>{ts}</triangles></mesh></object>')
        itens.append(f'<item objectid="{oid}"/>')
    modelo = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<model unit="millimeter" xml:lang="en-US" '
              'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
              f'<metadata name="Application">Ipê</metadata>'
              f'<metadata name="Title">{limpa_nome(name)}</metadata>'
              f'<resources><basematerials id="1">{cores}</basematerials>'
              + "".join(objetos) + "</resources>"
              f'<build>{"".join(itens)}</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", TIPOS_3MF)
        z.writestr("_rels/.rels", RELS_3MF)
        z.writestr("3D/3dmodel.model", modelo)
    return path
