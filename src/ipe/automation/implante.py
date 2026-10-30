"""Implante corrigido na chegada (0.97): a mamografia com prótese já abre sem o silicone.

Pedido dele: *"quando uma mamografia chegar, verifique se existe implante de silicone. Se existir,
aplique o filtro de cortar o implante para agilizar. Salve a imagem sem silicone no banco de dados
local."*

O que acontece, por imagem 2D de mamografia que chega:

1. **Vale procurar?** A mesma regra do botão Implante (`mammo.implante_esperado`): não procura
   quando o aparelho diz que não há prótese (`BreastImplantPresent = NO`), nem na incidência com o
   implante deslocado (Eklund), nem em compressão localizada ou magnificação. Tomossíntese, imagem
   "para processamento" e recombinada da CEM ficam de fora.
2. **Achou a prótese?** `mammo.implant_mask` — a busca pela borda da 0.95. Sem prótese, nada é
   gravado.
3. **Corrige e grava uma cópia**, `mammo.corrige_implante` (o mesmo "corrigir" da 0.96: o silicone
   desce ao nível do tecido e o detalhe fica). A cópia é uma série nova **no mesmo exame**, com
   UIDs novos, a marca `MARCA_SEM_IMPLANTE` no DerivationDescription, a original referenciada em
   SourceImageSequence e " · sem implante" no nome da série.

**A original não é tocada** — a cópia é a mais, ao lado dela. No protocolo de mamografia a cópia
vira a imagem do quadro e a original fica um passo atrás, na mesma lista. **A cópia não sai do
computador**: o envio ao PACS (manual ou roteamento) pula as séries " · sem implante", a não ser que
o médico escolha a série de propósito.

Uma mesma imagem não é corrigida duas vezes: o exame que chega em partes passa por aqui a cada
parte, e a original que já tem cópia é pulada.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from ipe.imaging import mammo as M

log = logging.getLogger(__name__)

CHAVE = "mg.implante_na_chegada"
# Preferências ▸ CAD/IA (0.99)
CHAVE_ANTERIORES = "mg.implante_anteriores"      # também nos anteriores baixados para comparação
CHAVE_SO_COM_MARCA = "mg.implante_so_com_marca"  # só quando o aparelho diz que há (BreastImplantPresent = YES)
CHAVE_SALVAR_BOTAO = "mg.implante_salvar_botao"  # o botão Implante grava a cópia no banco
CHAVE_DESTINOS = "mg.implante_destinos"          # ids de nós DICOM para mandar a cópia depois
PADROES = {CHAVE: True, CHAVE_ANTERIORES: True, CHAVE_SO_COM_MARCA: False, CHAVE_SALVAR_BOTAO: True,
           CHAVE_DESTINOS: []}


def config(settings, chave):
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v
#: a cópia entra com o número da série original mais isto (fica no fim da tira, perto da original)
SERIE_MAIS = 1000


def ligado(settings) -> bool:
    if settings is None:
        return True
    try:
        return bool(settings.get(CHAVE, True))
    except Exception:  # noqa: BLE001
        return True


def candidatas(imagens: list) -> list:
    """As imagens que valem a busca: 2D de leitura, sem cópia ainda, fora as variantes."""
    ja = {im.fonte for im in imagens if im.sem_implante and im.fonte}
    out = []
    for im in imagens:
        if im.sem_implante or im.sop_uid in ja:
            continue
        if im.tomo or im.frames > 1 or im.for_processing or im.energy == "rec":
            continue
        if im.view in ("SPOT", "MAG"):
            continue
        out.append(im)
    return out


def _faixa(ds) -> tuple[int, int]:
    bits = int(ds.get("BitsStored", 16) or 16)
    if int(ds.get("PixelRepresentation", 0) or 0) == 1:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def corrigir(path: str, mascara: np.ndarray | None = None, so_com_marca: bool = False) -> tuple[object | None, str]:
    """(dataset da cópia sem implante, "") ou (None, motivo). Não grava nada.

    `mascara`: a prótese já achada (no visualizador, inclusive a do clique "a partir daqui"); sem
    ela, o programa procura sozinho, com a regra do botão. A cópia sai ainda com o
    SeriesInstanceUID da original — quem grava troca (`serie_da_copia`)."""
    import pydicom
    from pydicom.dataset import Dataset
    from pydicom.uid import generate_uid

    if mascara is None:
        tags = M.tags_do_implante(path)
        motivo = M.implante_esperado(tags)
        if motivo:
            return None, motivo
        if so_com_marca and str(tags.get("BreastImplantPresent", "")).strip().upper() != "YES":
            return None, "o aparelho não marca implante (BreastImplantPresent) e a regra pede a marca"
    ds = pydicom.dcmread(path, force=True)
    if M.eh_sem_implante(ds):
        return None, "já é a imagem sem implante"
    if int(ds.get("NumberOfFrames", 1) or 1) > 1 or int(ds.get("SamplesPerPixel", 1) or 1) != 1:
        return None, "não é imagem 2D em tons de cinza"
    arr = ds.pixel_array
    if arr.ndim != 2:
        return None, "não é imagem 2D"
    slope = float(ds.get("RescaleSlope", 1) or 1)
    intercept = float(ds.get("RescaleIntercept", 0) or 0)
    px = arr.astype(np.float32) * slope + intercept
    mono1 = str(ds.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1"
    if mascara is None:
        mascara = M.implant_mask(px, mono1)
    elif mascara.shape != px.shape:
        return None, "a máscara não é do tamanho da imagem"
    if mascara is None or not mascara.any():
        return None, "sem implante"
    out = M.corrige_implante(px, mascara, mono1)
    lo, hi = _faixa(ds)
    gravar = np.clip(np.rint((out - intercept) / (slope or 1.0)), lo, hi)
    gravar = gravar.astype(np.int16 if lo < 0 else np.uint16)
    if int(ds.get("BitsAllocated", 16) or 16) == 8:
        gravar = gravar.astype(np.int8 if lo < 0 else np.uint8)

    fonte_classe, fonte_sop = str(ds.SOPClassUID), str(ds.SOPInstanceUID)
    ds.set_pixel_data(gravar, str(ds.PhotometricInterpretation), int(ds.get("BitsStored", 16) or 16))
    sop = generate_uid()
    ds.SOPInstanceUID = sop
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    agora = datetime.now()
    ds.InstanceCreationDate, ds.InstanceCreationTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
    tipo = [str(x) for x in (ds.get("ImageType") or [])]
    ds.ImageType = ["DERIVED", "SECONDARY", *tipo[2:]]
    ds.DerivationDescription = M.MARCA_SEM_IMPLANTE
    ref = Dataset()
    ref.ReferencedSOPClassUID, ref.ReferencedSOPInstanceUID = fonte_classe, fonte_sop
    ds.SourceImageSequence = [ref]
    ds.BreastImplantPresent = "YES"
    return ds, ""


def serie_da_copia(serie_original: str) -> str:
    """UID da série das cópias: sempre o mesmo para a mesma série original. A cópia gravada na
    chegada, pela tela do banco e pelo botão do visualizador cai na mesma série, e não numa nova
    a cada imagem salva."""
    from pydicom.uid import generate_uid
    return generate_uid(entropy_srcs=[serie_original, M.MARCA_SEM_IMPLANTE])


def _nomear(ds, desc: str, numero: int) -> None:
    ds.SeriesInstanceUID = serie_da_copia(str(ds.SeriesInstanceUID))
    ds.SeriesNumber = int(numero or 0) + SERIE_MAIS
    base = (desc or str(ds.get("SeriesDescription", "")) or "MG")[: 64 - len(M.SUFIXO_SEM_IMPLANTE)]
    ds.SeriesDescription = base + M.SUFIXO_SEM_IMPLANTE


def _importar(db, storage_root, pasta: Path) -> list[str]:
    from ipe.importer.scanner import Importer
    r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([pasta])
    try:
        from ipe.imaging.derived import _miniaturas
        _miniaturas(db, r)
    except Exception:  # noqa: BLE001
        log.debug("miniatura da série sem implante", exc_info=True)
    return sorted(getattr(r, "new_series", None) or [])


def ja_salvas(repo, study_uid: str) -> set[str]:
    """SOP Instance UIDs das originais deste exame que já têm cópia sem implante no banco.
    Lê só os cabeçalhos das séries " · sem implante" (são poucas)."""
    import pydicom
    out = set()
    for s in repo.series_for_study(study_uid):
        if not M.serie_sem_implante(s.description):
            continue
        for inst in repo.instances_for_series(s.series_uid):
            try:
                ds = pydicom.dcmread(inst["path"], stop_before_pixels=True, force=True)
            except Exception:  # noqa: BLE001
                continue
            if M.eh_sem_implante(ds) and M.fonte_da_copia(ds):
                out.add(M.fonte_da_copia(ds))
    return out


def salvar_uma(repo, db, storage_root, study_uid: str, path: str, sop_uid: str,
               mascara: np.ndarray | None = None) -> str:
    """Grava a cópia sem implante de **uma** imagem, se ainda não houver. Devolve "salva", "já
    estava salva" ou o motivo de não ter salvo. É o que o botão Implante do visualizador usa."""
    if sop_uid in ja_salvas(repo, study_uid):
        return "já estava salva"
    ds, motivo = corrigir(path, mascara)
    if ds is None:
        return motivo
    desc, numero = next(((s.description or "", s.series_number or 0) for s in repo.series_for_study(study_uid)
                         if s.series_uid == str(ds.SeriesInstanceUID)), ("", 0))
    _nomear(ds, desc, numero)
    tmp = Path(tempfile.mkdtemp(prefix="dv_implante_"))
    try:
        ds.save_as(tmp / "copia.dcm", enforce_file_format=True)
        _importar(db, storage_root, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return "salva"


def processar(repo, db, storage_root, study_uid: str, parar=lambda: False, progresso=None,
              so_com_marca: bool = False) -> dict:
    """Corrige as mamografias com implante deste exame e grava as cópias no banco local.

    `progresso(feitas, total)` a cada imagem (a tela do banco mostra a barra com ele)."""
    imagens = M.read_images(repo, study_uid)
    lista = candidatas(imagens)
    out = {"vistas": len(lista), "corrigidas": 0, "sem_implante": 0, "puladas": 0, "erros": 0,
           "series": []}
    if not lista:
        return out
    descricoes = {s.series_uid: (s.description or "", s.series_number or 0)
                  for s in repo.series_for_study(study_uid)}
    tmp = Path(tempfile.mkdtemp(prefix="dv_implante_"))
    try:
        for n, im in enumerate(lista, 1):
            if progresso is not None:
                progresso(n - 1, len(lista))
            if parar():
                break
            try:
                ds, motivo = corrigir(im.path, so_com_marca=so_com_marca)
            except Exception:  # noqa: BLE001 - uma imagem que falha não para as outras
                log.exception("implante na chegada: %s", im.path)
                out["erros"] += 1
                continue
            if ds is None:
                out["sem_implante" if motivo == "sem implante" else "puladas"] += 1
                continue
            desc, numero = descricoes.get(im.series_uid, ("", 0))
            _nomear(ds, desc, numero)
            ds.save_as(tmp / f"{n:04d}.dcm", enforce_file_format=True)
            out["corrigidas"] += 1
        if progresso is not None:
            progresso(len(lista), len(lista))
        if out["corrigidas"]:
            out["series"] = _importar(db, storage_root, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def resumo(out: dict) -> str:
    k = out.get("corrigidas", 0)
    if k:
        return f"{k} imagem(ns) com implante corrigida(s) e guardada(s) neste computador"
    if out.get("vistas", 0):
        return "nenhuma imagem com implante"
    return "nenhuma mamografia 2D para conferir"


def series_locais(repo, study_uid: str) -> set[str]:
    """Séries deste exame que ficam só neste computador (as cópias sem implante)."""
    try:
        return {s.series_uid for s in repo.series_for_study(study_uid) if M.serie_sem_implante(s.description)}
    except Exception:  # noqa: BLE001
        return set()
