"""0.100.72: os esquemas do laudo para fora — a imagem DICOM (captura secundária) no exame, o que o SR leva (a
referência à imagem, as marcas com a posição e a imagem ligada a cada uma) e as figuras do PDF.

Sem Qt (o PDF recebe os PNG prontos). Usado igual pela janela do laudo do Ipê e pelo laudo no navegador.
"""
from __future__ import annotations

import logging

import numpy as np
import pydicom
from pydicom.uid import generate_uid

from ipe.reporting import esquemas as E

log = logging.getLogger(__name__)

SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
SERIE, DESCRICAO = 992, "Esquemas do laudo"
DESCRICAO_SR = "Esquemas do laudo (SR)"
NOSSAS = (DESCRICAO, DESCRICAO_SR)                     # as séries que o Ipê grava com os esquemas (e pode regravar)
LARGURA = 1100


def com_conteudo(repo, study_uid: str) -> list[dict]:
    """Os esquemas do exame que têm alguma coisa desenhada (os vazios não vão para lugar nenhum)."""
    return [e for e in E.ler(repo, study_uid) if not E.vazio(e) and E.modelo(e.get("modelo", ""), repo)]


def figuras(repo, study_uid: str, largura: int = 900, so_do_laudo: bool = False) -> list[dict]:
    """Para o PDF: [{"titulo", "png", "linhas"}]. `so_do_laudo`: só se o médico pôs os esquemas no laudo."""
    out = []
    if so_do_laudo and not E.no_laudo(repo, study_uid):
        return out
    for e in com_conteudo(repo, study_uid):
        try:
            out.append({"titulo": E.titulo(e, repo), "png": E.png(e, largura, repo), "linhas": E.legenda(e, repo)})
        except Exception:  # noqa: BLE001
            log.exception("esquema no PDF")
    return out


def _imagem_sc(rgb: np.ndarray, fonte_path: str, serie_uid: str, instancia: int, nome: str):
    from ipe.reporting.dicom_out import _base
    ds = _base(fonte_path, SECONDARY_CAPTURE, "OT", DESCRICAO, SERIE)
    ds.SeriesInstanceUID = serie_uid
    ds.InstanceNumber = instancia
    ds.ConversionType = "SYN"                            # imagem sintética (desenho)
    ds.BurnedInAnnotation = "YES"
    ds.ImageComments = nome[:200]
    ds.DerivationDescription = ("Esquema do laudo: " + nome)[:1024]
    ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
    ds.Rows, ds.Columns = int(rgb.shape[0]), int(rgb.shape[1])
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()
    return ds


def _grafico(m: dict, W: int, H: int) -> tuple[str, list[float]] | None:
    """A marca como SCOORD (colunas e linhas da imagem gravada)."""
    pts = [(p[0] * (W - 1), p[1] * (H - 1)) for p in m.get("p") or []]
    if not pts:
        return None
    t = m.get("tipo")
    if t in ("ponto", "texto"):
        return "POINT", [round(v, 2) for v in pts[0]]
    if t == "elipse" and len(pts) >= 2:
        (x0, y0), (x1, y1) = pts[0], pts[1]
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        eixos = [(cx - rx, cy), (cx + rx, cy), (cx, cy - ry), (cx, cy + ry)]
        if ry > rx:                                      # o DICOM quer o eixo maior primeiro
            eixos = eixos[2:] + eixos[:2]
        return "ELLIPSE", [round(v, 2) for p in eixos for v in p]
    if len(pts) >= 2:
        return "POLYLINE", [round(v, 2) for p in pts for v in p]
    return None


def _classe_da_imagem(repo, sop_uid: str, series_uid: str = "") -> str:
    """A SOP Class da imagem ligada à marca (o SR precisa dela na referência)."""
    caminho = ""
    try:
        caminho = (repo.paths_for_sops([sop_uid]) or {}).get(sop_uid) or ""
    except Exception:  # noqa: BLE001 - o Ipê cliente não tem esta consulta
        log.debug("esquema: caminho da imagem ligada", exc_info=True)
    try:
        if not caminho and series_uid:
            caminho = next((i["path"] for i in repo.instances_for_series(series_uid) if i["sop_uid"] == sop_uid), "")
        if caminho:
            return str(pydicom.dcmread(caminho, stop_before_pixels=True, force=True, specific_tags=["SOPClassUID"]).SOPClassUID)
    except Exception:  # noqa: BLE001
        log.debug("esquema: classe da imagem ligada", exc_info=True)
    return ""


def para_o_exame(repo, study_uid: str, fonte_path: str, so_do_laudo: bool = False) -> tuple[list, list[dict]]:
    """(as imagens DICOM dos esquemas, o que o SR leva). Cada item do SR: `titulo`, `sop_uid`, `series_uid` e
    `sop_class` da imagem do esquema, `linhas` (a legenda) e `marcas` [{texto, grafico, dados, imagem}]."""
    datasets, para_sr = [], []
    if so_do_laudo and not E.no_laudo(repo, study_uid):   # 0.100.74: fora do laudo, quem grava é o "Gravar no exame"
        return datasets, para_sr
    serie = generate_uid()
    for i, e in enumerate(com_conteudo(repo, study_uid), 1):
        try:
            im = E.desenhar(e, LARGURA, repo, com_titulo=False)
        except Exception:  # noqa: BLE001
            log.exception("esquema para o exame")
            continue
        rgb = np.asarray(im, dtype=np.uint8)
        nome = E.titulo(e, repo)
        ds = _imagem_sc(rgb, fonte_path, serie, i, nome)
        datasets.append(ds)
        H, W = rgb.shape[:2]
        marcas = []
        for m in e.get("marcas") or []:
            n, texto = int(m.get("n") or 0), (m.get("texto") or "").strip()
            if not (n or texto):
                continue
            g = _grafico(m, W, H)
            item = {"texto": (f"{n}. " if n else "") + (texto or "(sem descrição)"),
                    "grafico": g[0] if g else "", "dados": g[1] if g else []}
            im_ = m.get("imagem") or {}
            if im_.get("sop_uid"):
                classe = _classe_da_imagem(repo, im_["sop_uid"], im_.get("series_uid", ""))
                if classe:
                    item["imagem"] = {"sop_uid": im_["sop_uid"], "series_uid": im_.get("series_uid", ""),
                                      "sop_class": classe, "frame": int(im_.get("frame") or 0)}
            marcas.append(item)
        mod = E.modelo(e["modelo"], repo) or {}
        nomes = {s["id"]: s["nome"] for s in mod.get("setores") or []}
        cats = {c["k"]: c["nome"] for c in mod.get("categorias") or []}
        setores = [f"{cats[v]}: {nomes[k]}" for k, v in (e.get("setores") or {}).items() if k in nomes and v in cats]
        para_sr.append({"titulo": nome, "sop_uid": ds.SOPInstanceUID, "series_uid": serie,
                        "sop_class": SECONDARY_CAPTURE, "linhas": E.legenda(e, repo), "marcas": marcas,
                        "setores": setores})
    return datasets, para_sr


# ---------------------------------------------------------------------- gravar no exame, sem depender do laudo
def apagar_anteriores(repo, study_uid: str, storage_root) -> int:
    """Tira do exame as séries dos esquemas que o próprio Ipê gravou antes (regravar não duplica)."""
    from pathlib import Path
    n = 0
    nossas = [se for se in repo.series_for_study(study_uid, True) if (se.description or "") in NOSSAS]
    destravado = False
    try:
        for se in nossas:
            try:
                try:
                    repo.delete_series(se.series_uid, Path(storage_root))
                except PermissionError as e:
                    # exame com cadeado (ligar uma marca a uma imagem-chave põe o cadeado) não deixa apagar série:
                    # estas são as que o próprio Ipê gerou dos esquemas, então o cadeado sai só enquanto são trocadas
                    if destravado or "cadeado" not in str(e):
                        raise
                    repo.set_locked(study_uid, False)
                    destravado = True
                    repo.delete_series(se.series_uid, Path(storage_root))
                n += 1
            except Exception:  # noqa: BLE001
                log.warning("não apaguei a série anterior %s", se.series_uid, exc_info=True)
    finally:
        if destravado:
            repo.set_locked(study_uid, True)
    cliente = getattr(repo, "client", None)              # no modo cliente, o servidor apaga as dele
    if cliente is not None and hasattr(cliente, "rpc"):
        try:
            cliente.rpc("apagar_series_dos_esquemas", study_uid)
        except Exception:  # noqa: BLE001 - servidor de versão anterior: fica como antes
            log.info("o servidor não apagou os esquemas anteriores", exc_info=True)
    return n


def gravar_no_exame(repo, storage_root, study_uid: str, quem: str = "") -> dict:
    """0.100.73: grava os esquemas no exame **agora**, sem laudo assinado — as figuras (série "Esquemas do laudo")
    e um SR só deles —, como a tabela da segmentação e o resumo da densidade. Gravar de novo troca o que havia.
    Devolve {"imagens": n, "series": [...]}."""
    import shutil
    import tempfile
    from pathlib import Path
    from ipe.importer.scanner import Importer
    from ipe.reporting.dicom_out import esquemas_sr
    arqs = [f for f in repo.files_for_study(study_uid) if f]
    if not arqs:
        raise ValueError("o exame não tem imagens neste computador")
    imagens, para_sr = para_o_exame(repo, study_uid, arqs[0])
    if not imagens:
        raise ValueError("Nenhum esquema com desenho para gravar.")
    sr = esquemas_sr(arqs[0], para_sr, quem, description=DESCRICAO_SR)
    tmp = Path(tempfile.mkdtemp(prefix="ipe_esquemas_"))
    try:
        for i, ds in enumerate([*imagens, sr]):
            ds.save_as(tmp / f"{i:03d}.dcm", enforce_file_format=True)
        apagar_anteriores(repo, study_uid, storage_root)
        r = Importer(repo.db, Path(storage_root)).import_paths([tmp])
        try:
            from ipe.importer.thumbnails import generate_thumbnails
            generate_thumbnails(repo, getattr(r, "new_series", None) or [])
        except Exception:  # noqa: BLE001
            log.debug("miniaturas dos esquemas", exc_info=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        from ipe.central.client_repo import upload_if_client
        upload_if_client(repo, study_uid)
    except Exception:  # noqa: BLE001
        log.exception("esquemas: enviar ao servidor")
    return {"imagens": len(imagens), "series": [str(imagens[0].SeriesInstanceUID), str(sr.SeriesInstanceUID)]}
