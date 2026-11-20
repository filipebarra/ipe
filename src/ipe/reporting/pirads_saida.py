"""0.100.79: o PI-RADS para fora — o SR (Enhanced SR) com o volume, o PSA e a densidade, cada lesão com a localização,
as pontuações, o ADC e a categoria, a imagem ligada e a impressão; e o "Gravar no exame", que grava também o mapa de
setores (série dos esquemas). O que veio de um modelo de pesquisa leva o aviso em cada item.

Sem Qt: usado igual pela janela do Ipê de mesa e pelo Ipê Web.
"""
from __future__ import annotations

import logging

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from ipe.reporting import pirads as P

log = logging.getLogger(__name__)

SERIE, DESCRICAO = 994, "PI-RADS (SR)"
_UCUM = {"ml": ("ml", "mL"), "ng/ml": ("ng/mL", "ng/mL"), "psad": ("ng/mL/cm3", "ng/mL/cm3"), "mm": ("mm", "mm"),
         "adc": ("um2/s", "um2/s"), "1": ("1", "no units")}


def _c(valor: str, esquema: str, sentido: str) -> Dataset:
    from ipe.reporting.dicom_out import _code
    return _code(valor, esquema, sentido[:64])


def _ipe(sentido: str) -> Dataset:
    import unicodedata
    valor = "".join(c for c in unicodedata.normalize("NFD", sentido) if ord(c) < 128)
    return _c(valor.upper().replace(" ", "_").replace("-", "")[:16], "99IPE", sentido)


def _item(tipo: str, nome: Dataset, rel: str = "CONTAINS") -> Dataset:
    it = Dataset()
    it.RelationshipType, it.ValueType = rel, tipo
    it.ConceptNameCodeSequence = Sequence([nome])
    return it


def _texto(nome: Dataset, texto: str) -> Dataset:
    it = _item("TEXT", nome)
    it.TextValue = str(texto)[:1024] or "-"
    return it


def _num(nome: Dataset, valor: float, unidade: str) -> Dataset:
    it = _item("NUM", nome)
    mv = Dataset()
    mv.NumericValue = f"{float(valor):.6g}"[:16]
    u, sentido = _UCUM[unidade]
    mv.MeasurementUnitsCodeSequence = Sequence([_c(u, "UCUM", sentido)])
    it.MeasuredValueSequence = Sequence([mv])
    return it


def _aviso() -> Dataset:
    return _texto(_c("121106", "DCM", "Comment"), "Aviso: " + P.MARCA_PESQUISA)


def montar_sr(repo, study_uid: str, src_path: str, d: dict, autor: str = "") -> Dataset:
    """O SR do PI-RADS (não é o laudo: fica como não verificado)."""
    from ipe.reporting.dicom_out import ENHANCED_SR, _base, _declarar, _imagem
    from ipe.reporting.esquemas_saida import _classe_da_imagem
    c = P.calcular(d)
    ds = _base(src_path, ENHANCED_SR, "SR", DESCRICAO, SERIE)
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([_c("121070", "DCM", "Findings")])
    ds.ContinuityOfContent = "SEPARATE"
    ds.CompletionFlag = "PARTIAL"
    ds.VerificationFlag = "UNVERIFIED"
    itens: list[Dataset] = []
    if autor:
        a = _item("PNAME", _c("121008", "DCM", "Person Observer Name"), "HAS OBS CONTEXT")
        a.PersonName = autor[:64]
        itens.append(a)
    itens.append(_texto(_c("121050", "DCM", "Equivalent Meaning of Concept Name"),
                        "RM de próstata — PI-RADS v2.1" + (" (biparamétrica)" if c["biparametrico"] else "")))
    if c["pesquisa"]:
        itens.append(_aviso())
    if c["volume_ml"]:
        v = _num(_c("118565006", "SCT", "Volume"), c["volume_ml"], "ml")
        v.ContentSequence = Sequence([_texto(_c("370129005", "SCT", "Measurement Method"),
                                             "elipsoide (0,52 × AP × T × CC)" if c["volume_fonte"] == "elipsoide"
                                             else f"segmentação automática ({c['volume_fonte']})")])
        itens.append(v)
    if c.get("psa") is not None:
        itens.append(_num(_c("2857-1", "LN", "Prostate specific Ag [Mass/volume] in Serum or Plasma"),
                          c["psa"], "ng/ml"))
    if c.get("psad") is not None:
        itens.append(_num(_ipe("Densidade do PSA"), c["psad"], "psad"))
    evidencia: dict[str, list[tuple[str, str]]] = {}
    for l in c["lesoes"]:
        filhos = [_texto(_c("363698007", "SCT", "Finding Site"), P.onde(l))]
        if l.get("zona"):
            filhos.append(_texto(_ipe("Zona"), P.ZONAS[l["zona"]]))
        if l.get("tamanho_mm"):
            filhos.append(_num(_c("G-D7FE", "SRT", "Diameter"), l["tamanho_mm"], "mm"))
        for k, nome in (("t2", "Pontuação T2"), ("dwi", "Pontuação difusão")):
            if l.get(k):
                filhos.append(_num(_ipe(nome), l[k], "1"))
        if not c["biparametrico"] and l.get("dce"):
            filhos.append(_texto(_ipe("DCE"), P.DCE[l["dce"]]))
        if l.get("adc"):
            filhos.append(_num(_c("113041", "DCM", "Apparent Diffusion Coefficient"), l["adc"], "adc"))
        if l.get("epe"):
            filhos.append(_texto(_ipe("Extensão extraprostática"), P.EPE[l["epe"]]))
        if l.get("descricao"):
            filhos.append(_texto(_c("121071", "DCM", "Finding"), l["descricao"]))
        if l.get("categoria"):
            filhos.append(_texto(_ipe("PI-RADS"), f"PI-RADS {l['categoria']}: {P.CATEGORIAS[l['categoria']]}"))
        if l.get("pesquisa"):
            filhos.append(_aviso())
            if l.get("probabilidade") is not None:
                filhos.append(_num(_ipe("Probabilidade do modelo"), l["probabilidade"], "1"))
            filhos.append(_texto(_ipe("Conferida"), "sim" if l.get("conferida") else "não"))
        im = l.get("imagem") or {}
        if im.get("sop_uid"):
            classe = _classe_da_imagem(repo, im["sop_uid"], im.get("series_uid", ""))
            if classe:
                filhos.append(_imagem("CONTAINS", classe, im["sop_uid"], int(im.get("frame") or 0),
                                      ("121080", "DCM", "Best illustration of finding")))
                evidencia.setdefault(im.get("series_uid") or "", []).append((classe, im["sop_uid"]))
        cont = _item("CONTAINER", _ipe(f"Lesão {l['n']}"))
        cont.ContinuityOfContent = "SEPARATE"
        cont.ContentSequence = Sequence(filhos)
        itens.append(cont)
    if c.get("outros"):
        itens.append(_texto(_c("121071", "DCM", "Finding"), c["outros"]))
    itens.append(_texto(_c("121073", "DCM", "Impression"), P.texto_impressao(c)))
    _declarar(ds, evidencia)
    ds.ContentSequence = Sequence(itens)
    return ds


def apagar_anteriores(repo, study_uid: str, storage_root) -> int:
    from pathlib import Path
    n = 0
    for se in repo.series_for_study(study_uid, True):
        if (se.description or "") == DESCRICAO:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
                n += 1
            except Exception:  # noqa: BLE001
                log.warning("pirads: não apaguei o SR anterior %s", se.series_uid, exc_info=True)
    return n


def gravar_no_exame(repo, storage_root, study_uid: str, quem: str = "") -> dict:
    """Grava agora, sem laudo assinado: o SR do PI-RADS e o mapa de setores (pela série dos esquemas). Gravar de
    novo troca o que havia. Devolve {"sr": uid da série, "esquemas": n de figuras}."""
    import shutil
    import tempfile
    from pathlib import Path
    from ipe.importer.scanner import Importer
    d = P.ler(repo, study_uid)
    if P.vazio(d):
        raise ValueError("O formulário PI-RADS deste exame está vazio.")
    arqs = [f for f in repo.files_for_study(study_uid) if f]
    if not arqs:
        raise ValueError("o exame não tem imagens neste computador")
    P.gravar_esquema(repo, study_uid, d, quem)
    figuras = 0
    try:
        from ipe.reporting import esquemas_saida as ES
        figuras = int(ES.gravar_no_exame(repo, storage_root, study_uid, quem).get("imagens") or 0)
    except ValueError:
        pass                                              # nenhum esquema com desenho (sem lesão com setor)
    sr = montar_sr(repo, study_uid, arqs[0], d, quem)
    tmp = Path(tempfile.mkdtemp(prefix="ipe_pirads_"))
    try:
        sr.save_as(tmp / "sr.dcm", enforce_file_format=True)
        apagar_anteriores(repo, study_uid, storage_root)
        Importer(repo.db, Path(storage_root)).import_paths([tmp])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        from ipe.central.client_repo import upload_if_client
        upload_if_client(repo, study_uid)
    except Exception:  # noqa: BLE001
        log.exception("pirads: enviar ao servidor")
    return {"sr": str(sr.SeriesInstanceUID), "esquemas": figuras}
