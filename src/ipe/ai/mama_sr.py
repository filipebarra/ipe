"""0.100.57: o resultado confirmado da mamografia gravado no exame — densidade e calcificações vasculares.

Pedido dele: "depois que confirmar, salve um SR, com tudo (densidade e todas as calcificações, incluindo as imagens
de onde estão as calcificações), como o da segmentação de órgãos abdominais".

Grava três séries no exame (e substitui as de uma confirmação anterior):
- **SR** (Comprehensive SR): a composição confirmada e as probabilidades da rede, o grau das calcificações
  confirmado e a sugestão, a área por mama e por imagem, as escalas (Margolies, CSBI, Loberant, BAC-SS), quem
  confirmou, os métodos, e as referências às imagens de origem e às imagens marcadas;
- **imagens marcadas** (Secondary Capture): cada imagem com calcificação, com o que a rede achou contornado em branco e cada vaso com setas e número (0.100.91; antes em vermelho, que sumia no monitor P&B);
- **resumo** (Secondary Capture): uma tabela com tudo, para quem não abre SR (o PACS mostra como imagem).

As imagens trazem o nome do paciente escrito: vão com BurnedInAnnotation = YES. Sem Qt (roda no servidor).
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

log = logging.getLogger(__name__)

COMPREHENSIVE_SR = "1.2.840.10008.5.1.4.1.1.88.33"
SECONDARY_CAPTURE = "1.2.840.10008.5.1.4.1.1.7"
DESC_SR = "Densidade e calcificações (Ipê) SR"
DESC_MARCADAS = "Calcificações vasculares (Ipê)"
DESC_RESUMO = "Densidade e calcificações (Ipê)"
SERIE_SR, SERIE_MARCADAS, SERIE_RESUMO = 7701, 7702, 7703
NOSSAS = (DESC_SR, DESC_MARCADAS, DESC_RESUMO)
ESQUEMA = "99IPE"
_COPIA = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "StudyInstanceUID",
          "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription", "ReferringPhysicianName",
          "InstitutionName"]
LADOS = {"R": "Direita", "L": "Esquerda"}
GRAUS = {"ausente": "Ausente", "leve": "Leve", "moderada": "Moderada", "acentuada": "Acentuada"}


# ------------------------------------------------------------------ quando gravar
def pronto_para_gravar(repo, study_uid: str) -> tuple[dict | None, dict | None]:
    """(densidade, calcificações) confirmadas — ou (None, None) se alguma medida ainda espera a confirmação."""
    from ipe.ai import calc_vascular as C
    from ipe.imaging import densidade_revisao as R
    d, c = R.guardada(repo, study_uid), C.guardada(repo, study_uid)
    d_ok = d is not None and d.get("estado") not in (None, "", "auto") and d.get("categoria")
    c_ok = c is not None and c.get("estado") not in (None, "", "auto") and c.get("grau")
    d_espera = d is not None and d.get("nyu") and not d_ok
    c_espera = c is not None and not c.get("aviso") and c.get("imagens") and not c_ok
    if d_espera or c_espera or not (d_ok or c_ok):
        return None, None
    return (d if d_ok else None), (c if c_ok else None)


def _auto(x: dict | None) -> bool:
    """Medida que ninguém conferiu (aceita automaticamente, 0.100.78)."""
    return (x or {}).get("estado") in (None, "", "auto")


def para_gravar_sem_conferir(repo, study_uid: str) -> tuple[dict | None, dict | None]:
    """0.100.78: o que vai ao SR quando a medida é aceita sem conferência — o que já foi confirmado fica como está;
    o resto entra como a rede sugeriu (densidade = categoria da NYU; calcificações = grau sugerido pela área)."""
    from ipe.ai import calc_vascular as C
    from ipe.imaging import densidade_revisao as R
    d, c = R.guardada(repo, study_uid), C.guardada(repo, study_uid)
    if d is not None and _auto(d):
        d = dict(d, categoria=d.get("nyu")) if d.get("nyu") else None
    elif d is not None and not d.get("categoria"):
        d = None
    if c is not None and _auto(c):
        c = dict(c, grau=c.get("sugestao")) if (c.get("sugestao") and not c.get("aviso")) else None
    elif c is not None and not c.get("grau"):
        c = None
    return d, c


def gravar_sem_conferir(repo, db, storage_root, study_uid: str) -> dict | None:
    """Grava o SR com a medida automática (sem esperar a confirmação). Quem abrir depois pode confirmar ou corrigir:
    `depois_de_confirmar` refaz o SR por cima."""
    d, c = para_gravar_sem_conferir(repo, study_uid)
    if d is None and c is None:
        return None
    out = gravar(repo, db, storage_root, study_uid, d, c, "")
    try:
        from ipe.central.client_repo import upload_if_client
        upload_if_client(repo, study_uid)
    except Exception:  # noqa: BLE001
        pass
    return out


def enviar(net, repo, settings, study_uid: str, out: dict | None) -> int:
    """Manda o SR, as imagens marcadas e o resumo para os nós de Preferências ▸ CAD/IA (0.100.78)."""
    if not out or not out.get("series"):
        return 0
    from ipe.automation import destinos as DEST
    from ipe.automation import mama_auto as MA
    info = {}
    try:
        info = repo.study_info(study_uid) or {}
    except Exception:  # noqa: BLE001
        pass
    nome = f"{info.get('patient_name', '')} {info.get('description', '')}".strip()
    return DEST.enviar(net, repo, study_uid, out["series"], MA.destinos(settings), f"Densidade e calcificações: {nome}", "mama")


def depois_de_confirmar(repo, db, storage_root, study_uid: str, quem: str = "",
                        sem_conferir: bool = False) -> dict | None:
    """Chamado depois de cada confirmação: com tudo confirmado, grava (ou regrava) o SR e as imagens. Com a medida
    aceita sem conferência (0.100.78), regrava já com o que foi confirmado e o resto como a rede sugeriu."""
    d, c = para_gravar_sem_conferir(repo, study_uid) if sem_conferir else pronto_para_gravar(repo, study_uid)
    if d is None and c is None:
        return None
    try:
        out = gravar(repo, db, storage_root, study_uid, d, c, quem)
    except Exception:  # noqa: BLE001
        log.exception("SR da mamografia")
        return None
    try:
        from ipe.central.client_repo import upload_if_client
        upload_if_client(repo, study_uid)
    except Exception:  # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------------ peças do SR
def _codigo(valor: str, esquema: str, sentido: str) -> Dataset:
    c = Dataset()
    c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = valor, esquema, sentido[:64]
    return c


def _ipe(valor: str, sentido: str) -> Dataset:
    return _codigo(valor, ESQUEMA, sentido)


def _item(tipo: str, nome: Dataset, rel: str = "CONTAINS") -> Dataset:
    it = Dataset()
    it.RelationshipType, it.ValueType = rel, tipo
    it.ConceptNameCodeSequence = Sequence([nome])
    return it


def _texto(nome: Dataset, texto: str, rel: str = "CONTAINS") -> Dataset:
    it = _item("TEXT", nome, rel)
    it.TextValue = str(texto)[:1024]
    return it


UNIDADES = {"mm2": ("mm2", "UCUM", "mm2"), "%": ("%", "UCUM", "%"), "1": ("1", "UCUM", "no units"),
            "mm": ("mm", "UCUM", "mm")}


def _num(nome: Dataset, valor: float, unidade: str) -> Dataset:
    it = _item("NUM", nome)
    mv = Dataset()
    mv.NumericValue = f"{float(valor):.4g}"[:16]
    mv.MeasurementUnitsCodeSequence = Sequence([_codigo(*UNIDADES[unidade])])
    it.MeasuredValueSequence = Sequence([mv])
    return it


def _imagem(nome: Dataset, classe: str, sop: str) -> Dataset:
    it = _item("IMAGE", nome)
    ref = Dataset()
    ref.ReferencedSOPClassUID, ref.ReferencedSOPInstanceUID = classe, sop
    it.ReferencedSOPSequence = Sequence([ref])
    return it


def _container(nome: Dataset, itens: list[Dataset], rel: str = "CONTAINS") -> Dataset:
    it = _item("CONTAINER", nome, rel)
    it.ContinuityOfContent = "SEPARATE"
    it.ContentSequence = Sequence(itens)
    return it


def _base(src, classe: str, modalidade: str, desc: str, numero: int, serie: str | None = None) -> Dataset:
    ds = Dataset()
    for kw in _COPIA:
        if kw in src:
            setattr(ds, kw, src.data_element(kw).value)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = classe
    sop = generate_uid()
    meta.MediaStorageSOPInstanceUID = sop
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = classe, sop
    ds.Modality = modalidade
    ds.SeriesInstanceUID = serie or generate_uid()
    ds.SeriesNumber = numero
    ds.SeriesDescription = desc[:64]
    ds.Manufacturer = "Ipe"
    agora = datetime.now()
    ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
    ds.SpecificCharacterSet = "ISO_IR 192"
    return ds


def _sc(src, rgb: np.ndarray, serie: str, numero: int, desc: str, n: int, comentario: str,
        origem: tuple[str, str] | None = None) -> Dataset:
    ds = _base(src, SECONDARY_CAPTURE, "OT", desc, numero, serie)
    ds.InstanceNumber = n
    ds.ConversionType = "WSD"
    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.BurnedInAnnotation = "YES"
    ds.ImageComments = comentario[:10240]
    if origem:
        r = Dataset()
        r.ReferencedSOPClassUID, r.ReferencedSOPInstanceUID = origem
        ds.SourceImageSequence = Sequence([r])
    rgb = np.ascontiguousarray(rgb[..., :3], dtype=np.uint8)
    ds.Rows, ds.Columns = rgb.shape[:2]
    ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = rgb.tobytes()
    return ds


# ------------------------------------------------------------------ desenhos (Pillow, sem Qt)
def _fonte(tam: int):
    from PIL import ImageFont
    for nome in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:
        return ImageFont.load_default()


def _fmt(v, casas=1) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def imagem_marcada(ds, img: dict, paciente: str) -> np.ndarray:
    """A mamografia com a calcificação marcada (contorno e setas numeradas) e uma faixa com lado, incidência, área e o nome."""
    from PIL import Image, ImageDraw

    from ipe.ai import calc_vascular as C
    largura = min(1400, int(getattr(ds, "Columns", 1400) or 1400))
    rgb = C.previa(ds, img, largura)
    im = Image.fromarray(rgb)
    faixa = 72                                   # duas linhas: o que é e de quem é
    out = Image.new("RGB", (im.width, im.height + faixa), (20, 22, 28))
    out.paste(im, (0, faixa))
    d = ImageDraw.Draw(out)
    lado, inc = (img.get("chave") or "?-?").split("-", 1)
    extra = " · fora da conta (compressão/ampliação)" if img.get("extra") else ""
    d.text((12, 8), f"{LADOS.get(lado, lado)} {inc} · {_fmt(img.get('area_mm2'))} mm²{extra}",
           font=_fonte(22), fill=(255, 210, 120))
    d.text((12, 42), paciente, font=_fonte(18), fill=(220, 220, 220))
    return np.asarray(out)


def tabela(d: dict | None, c: dict | None, cab: dict) -> np.ndarray:
    """O resumo de tudo, como imagem (para PACS que não mostram SR)."""
    from PIL import Image, ImageDraw

    from ipe.ai import calc_vascular_escalas as E
    from ipe.imaging import densidade_revisao as R
    linhas: list[tuple[str, str, str]] = []           # (tipo, esquerda, direita)
    if d:
        linhas.append(("faixa", "DENSIDADE MAMÁRIA (BI-RADS)", ""))
        linhas.append(("linha", "Composição (automática, não conferida)" if _auto(d) else "Composição confirmada",
                       R.NOMES.get(d.get("categoria", ""), d.get("categoria", ""))))
        if d.get("nyu"):
            linhas.append(("linha", "Sugestão da rede (NYU)", R.NOMES.get(d["nyu"], d["nyu"])))
        for cat, p in zip(R.CATEGORIAS, d.get("nyu_probs") or []):
            linhas.append(("linha", f"  probabilidade {cat.upper()}", f"{_fmt(100 * p)} %"))
        linhas.append(("linha", "Confirmado por", "não conferido pelo médico" if _auto(d) else
                       f"{d.get('revisor') or '—'} {d.get('confirmado_em') or ''}".strip()))
    if c:
        linhas.append(("faixa", "CALCIFICAÇÕES VASCULARES", ""))
        linhas.append(("linha", "Grau (automático, não conferido)" if _auto(c) else "Grau confirmado",
                       GRAUS.get(c.get("grau", ""), c.get("grau", ""))))
        if c.get("sugestao"):
            linhas.append(("linha", "Sugestão (área)", GRAUS.get(c["sugestao"], c["sugestao"])))
        for lado in ("R", "L"):
            pm = (c.get("por_mama") or {}).get(lado)
            if pm is not None:
                linhas.append(("linha", f"Mama {LADOS[lado].lower()}", f"{_fmt(pm)} mm²"))
        for nome, valor, _dica in E.resumo(c.get("escalas")):
            linhas.append(("linha", nome, valor))
        n = sum(1 for x in (c.get("imagens") or []) if (x.get("area_mm2") or 0) > 0)
        linhas.append(("linha", "Imagens com calcificação", str(n)))
        linhas.append(("linha", "Confirmado por", "não conferido pelo médico" if _auto(c) else
                       f"{c.get('revisor') or '—'} {c.get('confirmado_em') or ''}".strip()))
    larg, alt_l, topo = 1400, 40, 190
    alt = topo + alt_l * len(linhas) + 120
    im = Image.new("RGB", (larg, alt), (255, 255, 255))
    g = ImageDraw.Draw(im)
    g.rectangle([0, 0, larg, 120], fill=(38, 54, 89))
    g.text((40, 26), "Mamografia — densidade e calcificações vasculares", font=_fonte(36), fill=(255, 255, 255))
    g.text((40, 78), f"{cab.get('paciente', '')}  ·  {cab.get('id', '')}  ·  {cab.get('data', '')}",
           font=_fonte(22), fill=(219, 225, 242))
    sem = (d is not None and _auto(d)) or (c is not None and _auto(c))
    g.text((40, 140), f"Ipê · {'medida automática, sem conferência do médico' if sem else 'confirmado pelo médico'}"
                      f" · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
           font=_fonte(20), fill=(90, 90, 90))
    y = topo
    for tipo, a, b in linhas:
        if tipo == "faixa":
            g.rectangle([30, y + 4, larg - 30, y + alt_l - 2], fill=(219, 225, 242))
            g.text((44, y + 10), a, font=_fonte(22), fill=(38, 54, 89))
        else:
            g.text((60, y + 9), a, font=_fonte(22), fill=(30, 30, 30))
            g.text((larg - 60, y + 9), b, font=_fonte(22), fill=(30, 30, 30), anchor="ra")
            g.line([60, y + alt_l - 1, larg - 60, y + alt_l - 1], fill=(230, 230, 230))
        y += alt_l
    g.text((40, alt - 70), "Densidade: rede da NYU (Wu et al.). Calcificações: SCU-Net (Emory). As escalas são "
                           "estimadas pelo que a rede marcou.", font=_fonte(18), fill=(110, 110, 110))
    g.text((40, alt - 42), "Apoio à leitura — a decisão é do médico.", font=_fonte(18), fill=(110, 110, 110))
    return np.asarray(im)


# ------------------------------------------------------------------ gravar
def _apagar_anteriores(repo, study_uid: str, storage_root) -> int:
    n = 0
    for se in repo.series_for_study(study_uid):
        if (se.description or "") in NOSSAS:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
                n += 1
            except Exception:  # noqa: BLE001
                log.warning("não apaguei a série anterior %s", se.series_uid, exc_info=True)
    # 0.100.60: no modo cliente, o servidor apaga as dele (senão o SR regravado ficava duplicado lá)
    cliente = getattr(repo, "client", None)
    if cliente is not None and hasattr(cliente, "rpc"):
        try:
            cliente.rpc("apagar_series_da_mama", study_uid)
        except Exception:  # noqa: BLE001 - servidor de versão anterior: fica como antes
            log.info("o servidor não apagou o SR anterior da mamografia", exc_info=True)
    return n


def gravar(repo, db, storage_root, study_uid: str, d: dict | None, c: dict | None, quem: str = "") -> dict:
    """Monta e grava o SR, as imagens marcadas e o resumo; devolve {"series": [...], "marcadas": n}."""
    from ipe.ai import calc_vascular as C
    from ipe.importer.scanner import Importer
    lista = C.imagens_do_exame(repo, study_uid)
    if not lista:
        arqs = [f for f in repo.files_for_study(study_uid) if f]
        if not arqs:
            raise ValueError("o exame não tem imagens neste computador")
        src_path = arqs[0]
    else:
        src_path = lista[0]["caminho"]
    src = pydicom.dcmread(src_path, stop_before_pixels=True, force=True)
    paciente = str(src.get("PatientName", "") or "").replace("^", " ").strip()
    cab = {"paciente": paciente, "id": str(src.get("PatientID", "") or ""),
           "data": _data(str(src.get("StudyDate", "") or ""))}
    por_sop = {x["sop"]: x for x in lista}
    tmp = Path(tempfile.mkdtemp(prefix="ipe_mama_sr_"))
    datasets: list[Dataset] = []
    referencias: dict[str, tuple[str, str]] = {}       # sop -> (classe, série)
    try:
        # as imagens marcadas
        serie_m = generate_uid()
        marcadas: dict[str, Dataset] = {}
        if c:
            k = 0
            for img in C.imagens_guardadas(c):
                if (img.get("area_mm2") or 0) <= 0 or not img.get("mascara"):
                    continue
                x = por_sop.get(img.get("sop") or "")
                caminho = x["caminho"] if x else C.arquivo_da_imagem(repo, study_uid, img)
                if not caminho:
                    continue
                ds_o = pydicom.dcmread(caminho, force=True)
                k += 1
                comentario = f"{img.get('chave', '')}: {_fmt(img.get('area_mm2'))} mm2 de calcificação vascular (SCU-Net)"
                sc = _sc(src, imagem_marcada(ds_o, img, paciente), serie_m, SERIE_MARCADAS, DESC_MARCADAS, k,
                         comentario, (str(ds_o.SOPClassUID), str(ds_o.SOPInstanceUID)))
                marcadas[str(ds_o.SOPInstanceUID)] = sc
                referencias[str(ds_o.SOPInstanceUID)] = (str(ds_o.SOPClassUID), str(ds_o.SeriesInstanceUID))
                referencias[str(sc.SOPInstanceUID)] = (SECONDARY_CAPTURE, serie_m)
                datasets.append(sc)
        resumo = _sc(src, tabela(d, c, cab), generate_uid(), SERIE_RESUMO, DESC_RESUMO, 1,
                     "Resumo: densidade mamária e calcificações vasculares "
                     + ("(automático, não conferido)" if (d is not None and _auto(d)) or (c is not None and _auto(c))
                        else "(confirmado)"))
        datasets.append(resumo)
        referencias[str(resumo.SOPInstanceUID)] = (SECONDARY_CAPTURE, str(resumo.SeriesInstanceUID))
        sr = _sr(src, d, c, lista, marcadas, resumo, quem, referencias)
        datasets.append(sr)
        for i, ds in enumerate(datasets):
            ds.save_as(tmp / f"{i:03d}.dcm", enforce_file_format=True)
        _apagar_anteriores(repo, study_uid, storage_root)
        r = Importer(db, Path(storage_root)).import_paths([tmp])
        try:
            from ipe.db.repository import Repository
            from ipe.importer.thumbnails import generate_thumbnails
            generate_thumbnails(Repository(db), r.new_series)
        except Exception:  # noqa: BLE001
            log.debug("miniaturas do SR da mama", exc_info=True)
        return {"series": sorted(getattr(r, "new_series", None) or []), "marcadas": len(marcadas),
                "sr": str(sr.SOPInstanceUID)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _data(s: str) -> str:
    return f"{s[6:8]}/{s[4:6]}/{s[:4]}" if len(s) == 8 else s


def _sr(src, d, c, lista, marcadas, resumo, quem, referencias) -> Dataset:
    from ipe.ai import calc_vascular as C
    from ipe.imaging import densidade_revisao as R
    ds = _base(src, COMPREHENSIVE_SR, "SR", DESC_SR, SERIE_SR)
    ds.InstanceNumber = 1
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([_codigo("18748-4", "LN", "Diagnostic imaging report")])
    ds.ContinuityOfContent = "SEPARATE"
    ds.CompletionFlag = "COMPLETE"
    ds.VerificationFlag = "UNVERIFIED"
    itens: list[Dataset] = [_texto(_codigo("121050", "DCM", "Equivalent Meaning of Concept Name"),
                                   "Mamografia — densidade mamária e calcificações vasculares")]
    revisor = quem or (c or {}).get("revisor") or (d or {}).get("revisor") or ""
    if revisor:
        p = _item("PNAME", _codigo("121008", "DCM", "Person Observer Name"), "HAS OBS CONTEXT")
        p.PersonName = revisor[:64]
        itens.append(p)
    vistas_d = {}
    if d:
        sub = [_texto(_ipe("DENS-CAT", "Breast composition (BI-RADS)"),
                      R.NOMES.get(d.get("categoria", ""), d.get("categoria", ""))),
               _texto(_ipe("DENS-SUG", "Network suggestion"), R.NOMES.get(d.get("nyu") or "", d.get("nyu") or "—")),
               _texto(_ipe("DENS-EST", "Review"), "automática, não conferida pelo médico" if _auto(d)
                      else "aceita (igual à rede)" if d.get("estado") == "aceito" else "editada pelo médico"),
               _texto(_codigo("111001", "DCM", "Algorithm Name"), "NYU breast density network (Wu et al., 2020)")]
        for cat, p in zip(R.CATEGORIAS, d.get("nyu_probs") or []):
            sub.append(_num(_ipe(f"DENS-P{cat.upper()}", f"Probability of composition {cat.upper()}"),
                            100 * float(p), "%"))
        # as quatro incidências que a rede viu
        try:
            vistas, _ap, _av = R.escolher_vistas([R.cabecalho(x["caminho"]) for x in lista])
            for chave, caminho in vistas.items():
                h = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
                vistas_d[chave] = h
                sub.append(_imagem(_ipe("DENS-IMG", f"Image used ({chave})"), str(h.SOPClassUID),
                                   str(h.SOPInstanceUID)))
                referencias[str(h.SOPInstanceUID)] = (str(h.SOPClassUID), str(h.SeriesInstanceUID))
        except Exception:  # noqa: BLE001
            log.debug("vistas da densidade no SR", exc_info=True)
        for a in d.get("avisos") or []:
            sub.append(_texto(_ipe("AVISO", "Note"), a))
        itens.append(_container(_ipe("DENS", "Breast density"), sub))
    if c:
        sub = [_texto(_ipe("BAC-GRAU", "Vascular calcification grade"), GRAUS.get(c.get("grau", ""), c.get("grau", ""))),
               _texto(_ipe("BAC-SUG", "Suggested grade (area)"), GRAUS.get(c.get("sugestao") or "", "—")),
               _texto(_ipe("BAC-EST", "Review"), "automático, não conferido pelo médico" if _auto(c)
                      else "conferido pelo médico"),
               _texto(_codigo("111001", "DCM", "Algorithm Name"), str(c.get("modelo") or "SCU-Net"))]
        if c.get("area_mm2") is not None:
            sub.append(_num(_ipe("BAC-AREA", "Calcified area (largest breast)"), c["area_mm2"], "mm2"))
        for lado in ("R", "L"):
            pm = (c.get("por_mama") or {}).get(lado)
            if pm is not None:
                sub.append(_num(_ipe(f"BAC-AREA-{lado}", f"Calcified area — {'right' if lado == 'R' else 'left'} breast"),
                                pm, "mm2"))
        e = c.get("escalas")
        if e:
            sub.append(_num(_ipe("BAC-MARG", "Margolies score (0-12, estimated)"), e["margolies"]["total"], "1"))
            sub.append(_num(_ipe("BAC-CSBI", "CSBI grade (0-3, estimated)"), e["csbi"]["grau"], "1"))
            sub.append(_num(_ipe("BAC-LOB", "Loberant grade (0-3, estimated)"), e["loberant"]["grau"], "1"))
            sub.append(_num(_ipe("BAC-SS", "BAC-SS (estimated)"), e["bacss"]["maior"], "1"))
        for img in C.imagens_guardadas(c):
            if (img.get("area_mm2") or 0) <= 0:
                continue
            itens_img = [_texto(_ipe("BAC-VISTA", "View"), img.get("chave", "")),
                         _num(_ipe("BAC-AREA-IMG", "Calcified area in image"), img["area_mm2"], "mm2")]
            if img.get("extra"):
                itens_img.append(_texto(_ipe("AVISO", "Note"), "compressão localizada/ampliação — fora da conta"))
            sop = img.get("sop") or ""
            if sop in referencias and sop in marcadas:
                itens_img.append(_imagem(_ipe("BAC-ORIG", "Source image"), referencias[sop][0], sop))
                m = marcadas[sop]
                itens_img.append(_imagem(_ipe("BAC-MARCADA", "Image with calcifications marked"),
                                         SECONDARY_CAPTURE, str(m.SOPInstanceUID)))
            sub.append(_container(_ipe("BAC-IMG", "Image with vascular calcification"), itens_img))
        for a in (c.get("avisos") or []):
            sub.append(_texto(_ipe("AVISO", "Note"), a))
        itens.append(_container(_ipe("BAC", "Breast arterial calcification"), sub))
    itens.append(_imagem(_ipe("RESUMO", "Summary table"), SECONDARY_CAPTURE, str(resumo.SOPInstanceUID)))
    ds.ContentSequence = Sequence(itens)
    # as imagens citadas (obrigatório no SR): por série
    por_serie: dict[str, list[tuple[str, str]]] = {}
    for sop, (classe, serie) in referencias.items():
        por_serie.setdefault(serie, []).append((classe, sop))
    estudo = Dataset()
    estudo.StudyInstanceUID = src.StudyInstanceUID
    series = []
    for serie, sops in por_serie.items():
        s = Dataset()
        s.SeriesInstanceUID = serie
        refs = []
        for classe, sop in sops:
            r = Dataset()
            r.ReferencedSOPClassUID, r.ReferencedSOPInstanceUID = classe, sop
            refs.append(r)
        s.ReferencedSOPSequence = Sequence(refs)
        series.append(s)
    estudo.ReferencedSeriesSequence = Sequence(series)
    ds.CurrentRequestedProcedureEvidenceSequence = Sequence([estudo])
    return ds


def resumo_texto(out: dict | None) -> str:
    if not out:
        return ""
    n = out.get("marcadas", 0)
    return f"SR gravado no exame ({n} imagem(ns) com calcificação marcada e o resumo)."
