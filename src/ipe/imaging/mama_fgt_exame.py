"""0.100.7: fibroglandular (FGT) e realce de fundo (BPE) de um exame de RM de mama — a parte que conversa com o
banco: escolhe a série, monta o volume, chama `mama_fgt` e grava a máscara como SEG.

Ordem das séries (a que foi conferida no acervo primeiro):
1. **T1 sem saturação** (no protocolo do serviço, o "A T1"/"Axi T1"/"Ax T1 FSE" de quase todo exame);
2. **Dixon** (o par FAT:/WATER:, ou _F/_W), pela fração de gordura;
3. a **pré-contraste da dinâmica** (com saturação de gordura), com aviso de número menos confiável.

O realce de fundo sai da dinâmica aberta (pré e primeira fase pós), com a máscara do FGT levada para a grade dela
pela posição no paciente.
"""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ipe.imaging import mama_fgt as F

log = logging.getLogger(__name__)

DESC_SEG = "Mama e fibroglandular · Ipê"
SERIE_SEG = 972

#: o que denuncia saturação de gordura, contraste ou subtração na descrição
_RE_NAO_T1 = re.compile(r"(\bfs\b|fat ?sat|f/s|spair|spir|stir|vibrant|ph\d|dyn|din[aâ]m|sub|\+ ?c\b|\bc\+|"
                        r"\bpos\b|p[oó]s|post|gd|gado|realce|water|fat:|\bfat\b|\bw\b|\bf\b|dixon|flex|ideal|"
                        r"mip|mpr|dwi|adc|difus|t2|stir|\(ipe\)|· ip[eê])", re.I)
_RE_T1 = re.compile(r"\bt1", re.I)
_RE_GORDURA = re.compile(r"(^fat[:\s_]|[_\s]f$|\bfat\b|gordura|fat fraction)", re.I)
_RE_AGUA = re.compile(r"(^water[:\s_]|[_\s]w$|\bwater\b|[aá]gua)", re.I)


@dataclass
class Escolha:
    fonte: str = ""
    series: list = field(default_factory=list)      # uids: [t1] ou [gordura, água] ou [] (a pré da dinâmica)
    descricao: str = ""


def _nucleo_dixon(desc: str) -> str:
    d = re.sub(r"^(fat|water)[:\s_]+", "", desc.strip(), flags=re.I)
    return re.sub(r"[_\s](f|w)$", "", d, flags=re.I).strip().lower()


def escolher_series(series) -> Escolha:
    """`series`: objetos com `.series_uid`, `.description`, `.modality` e (opcional) `.num_images`."""
    mr = [s for s in series if (getattr(s, "modality", "") or "MR") == "MR" and (getattr(s, "num_images", 0) or 99) >= 10]
    t1 = [s for s in mr if _RE_T1.search(s.description or "") and not _RE_NAO_T1.search(s.description or "")]
    if t1:
        # axial primeiro (o nome costuma dizer), e a de mais imagens
        t1.sort(key=lambda s: (not re.search(r"\bax|axi", s.description or "", re.I), -(getattr(s, "num_images", 0) or 0)))
        return Escolha(F.FONTE_T1, [t1[0].series_uid], t1[0].description or "")
    gord = [s for s in mr if _RE_GORDURA.search(s.description or "")]
    agua = [s for s in mr if _RE_AGUA.search(s.description or "")]
    for g in gord:
        par = [a for a in agua if _nucleo_dixon(a.description or "") == _nucleo_dixon(g.description or "")
               and (getattr(a, "num_images", 0) or 0) == (getattr(g, "num_images", 0) or 0)]
        if par:
            return Escolha(F.FONTE_DIXON, [g.series_uid, par[0].series_uid],
                           f"{g.description} + {par[0].description}")
    return Escolha(F.FONTE_FS, [], "")


def afim(origem, row_dir, col_dir, slice_vec, dx, dy) -> np.ndarray:
    """4×4: índice (corte, linha, coluna) → mm."""
    a = np.eye(4)
    a[:3, 0] = np.asarray(slice_vec, float)
    a[:3, 1] = np.asarray(col_dir, float) * float(dy)
    a[:3, 2] = np.asarray(row_dir, float) * float(dx)
    a[:3, 3] = np.asarray(origem, float)
    return a


def _volume(repo, cache, uid: str, progresso=None):
    from ipe.imaging.series import build_frames
    from ipe.imaging.volume import build_volume
    frames = build_frames(repo.instances_for_series(uid), uid)
    return build_volume(frames, cache, progresso), frames


def _geometria(v) -> tuple:
    ori = list(v.row_dir) + list(v.col_dir)
    return ori, (v.dz, v.dy, v.dx)


def volumes_da_dinamica(maps, progresso=None):
    """(pré, primeira pós, afim, orientação, slice_vec) da dinâmica aberta, ou None."""
    ref = maps.dset.phases[maps.pre]
    if len(ref) < 3 or ref[0].position is None or ref[0].orientation is None:
        return None
    pre = np.empty((maps.n, *maps.shape), np.float32)
    pos = np.empty_like(pre)
    for k in range(maps.n):
        st = maps.stack(k)
        pre[k], pos[k] = st[maps.pre], st[maps.early]
        if progresso is not None and not progresso(k + 1, maps.n):
            return None
    p = np.asarray([f.position for f in ref], float)
    slice_vec = (p[-1] - p[0]) / (len(ref) - 1)
    o = np.asarray(ref[0].orientation, float)
    rs, cs = maps.pixel_spacing or (1.0, 1.0)
    return pre, pos, afim(p[0], o[:3], o[3:], slice_vec, cs, rs), list(o), slice_vec


def medir(repo, cache, study_uid: str, maps=None, progresso=None):
    """Mede o FGT (e o BPE, se `maps` — a dinâmica aberta — vier). Devolve (ResultadoFGT, Escolha, volume, frames);
    o volume e os quadros são os da série medida, para gravar a SEG."""
    esc = escolher_series(repo.series_for_study(study_uid))
    dyn = volumes_da_dinamica(maps) if maps is not None else None
    vol = frames = None
    if esc.fonte == F.FONTE_T1:
        vol, frames = _volume(repo, cache, esc.series[0], progresso)
        ori, vox = _geometria(vol)
        r = F.segmentar(np.asarray(vol.data, np.float32), ori, vox, F.FONTE_T1, slice_vec=vol.slice_vec)
    elif esc.fonte == F.FONTE_DIXON:
        vol, frames = _volume(repo, cache, esc.series[0], progresso)
        agua, _ = _volume(repo, cache, esc.series[1])
        if agua.shape != vol.shape:
            raise ValueError("As séries de gordura e de água do Dixon não têm o mesmo tamanho.")
        ori, vox = _geometria(vol)
        r = F.segmentar(None, ori, vox, F.FONTE_DIXON, gordura=np.asarray(vol.data, np.float32),
                        agua=np.asarray(agua.data, np.float32), slice_vec=vol.slice_vec)
    else:
        if dyn is None:
            raise ValueError("Sem T1 sem saturação, sem Dixon e sem a dinâmica aberta: não há onde separar gordura "
                             "de glândula. Abra a dinâmica da mama e tente de novo.")
        pre, _pos, a, ori, sv = dyn
        n = np.linalg.norm(sv)
        r = F.segmentar(pre, ori, (n, a[:3, 1].dot(a[:3, 1]) ** 0.5, a[:3, 2].dot(a[:3, 2]) ** 0.5), F.FONTE_FS,
                        slice_vec=sv)
        esc.descricao = "pré-contraste da dinâmica"
        frames = maps.dset.phases[maps.pre]
    r.serie = esc.descricao
    if dyn is not None:
        pre, pos, a_dyn, ori_dyn, sv_dyn = dyn
        if vol is not None:
            a_src = afim(vol.origin, vol.row_dir, vol.col_dir, vol.slice_vec, vol.dx, vol.dy)
            fgt_dyn = F.reamostrar(r.fgt, a_src, pre.shape, a_dyn)
            mama_dyn = F.reamostrar(r.mama, a_src, pre.shape, a_dyn)
        else:
            fgt_dyn, mama_dyn = r.fgt, r.mama
        eixo, sentido = F.eixo_esquerda(ori_dyn, sv_dyn)
        F.medir_bpe(r, fgt_dyn, list(F.lados(mama_dyn, eixo, sentido)), pre, pos)
    return r, esc, vol, frames


def gravar_seg(r, vol, frames, db, storage_root, repo, study_uid: str) -> list[str]:
    """A mama medida e o FGT como uma SEG na série medida (troca a anterior). Devolve as séries novas."""
    from types import SimpleNamespace

    from ipe.ai import cefalometria as CF
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    if vol is None or r.mama is None or not r.mama.any():
        return []
    for se in repo.series_for_study(study_uid):
        if (se.description or "") == DESC_SEG:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar a SEG do fibroglandular")
    segs = []
    for mk, nome, cor in ((r.mama & ~r.fgt, "Mama (gordura)", (240, 200, 90)), (r.fgt, "Fibroglandular", (220, 50, 80))):
        if mk is not None and mk.any():
            fat, off = CF._recorte(mk)
            segs.append((SimpleNamespace(mask=mk[fat], offset=off), nome, cor))
    ds = build_seg(vol, segs, vol.source_path, frames=frames, series_number=SERIE_SEG, description=DESC_SEG,
                   algoritmo=("AUTOMATIC", "Ipe fibroglandular (Otsu)"), anatomia=True)
    tmp = Path(tempfile.mkdtemp(prefix="dv_fgt_"))
    try:
        ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
        res = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        return sorted(getattr(res, "new_series", None) or [])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def linhas(r) -> list[tuple[str, str]]:
    """Tabela para a tela."""
    out = [("Série medida", r.serie or "—")]
    for lado in r.lados + [r.total]:
        nome = {"direita": "Mama direita", "esquerda": "Mama esquerda", "total": "As duas"}[lado.nome]
        if lado.mama_ml:
            out.append((nome, f"FGT {lado.fgt_pct:.0f}% · {lado.fgt_ml:.0f} de {lado.mama_ml:.0f} mL"))
    if r.implante_ml:
        out.append(("Implante (fora da conta)", f"{r.implante_ml:.0f} mL"))
    for lado in r.lados + [r.total]:
        if lado.bpe_realce_mediana is not None:
            nome = {"direita": "Realce · direita", "esquerda": "Realce · esquerda", "total": "Realce · as duas"}[lado.nome]
            out.append((nome, f"mediana {lado.bpe_realce_mediana:.0f}% · {lado.bpe_pct:.0f}% do FGT > "
                              f"{F.REALCE_LIMIAR:.0f}%"))
    return out
