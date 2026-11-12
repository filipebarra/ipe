"""T1 sintético de 1 mm a partir de qualquer série do crânio (SynthSR) — 0.100.23.

Para que serve: os protocolos sem T1 3D (os de Parkinson só têm 2D de 4–5 mm) não dão MPR decente — o
sagital mediano e o coronal oblíquo do MRPI saem em degraus. O SynthSR (Iglesias et al., NeuroImage 2021;
Science Advances 2023) recebe uma série de qualquer contraste, orientação e espessura e devolve um volume
isotrópico de 1 mm com contraste de MP-RAGE. A série nova entra no exame, com o **mesmo Frame of Reference**
da original: abre no MPR, sincroniza e aceita as medidas guiadas e os índices automáticos.

Como roda: a U-Net do SynthSR 1.0 foi reescrita em PyTorch no trabalhador (`totalseg_worker._rede_synthsr`),
lendo os pesos originais do Keras (Apache-2.0, 53 MB, baixados uma vez) — o ambiente da segmentação não
precisa do TensorFlow.

**É imagem sintética.** A rede foi treinada só com anatomia normal: lesões podem sumir ou mudar de aspecto
("inpainting"), e o contraste é inventado. Serve para medir anatomia (distâncias, áreas, volumes); nunca
para procurar ou caracterizar lesão. Isso vai na descrição da série, no cabeçalho DICOM e na mensagem.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FERRAMENTA = "synthsr"
TITULO = "T1 sintético de 1 mm (IA, SynthSR)"
MARCA = "· SynthSR"
DESC_SERIE = f"T1 sintético 1 mm {MARCA}"
DESC_SEG = DESC_SERIE                 # o nome que as telas genéricas usam para "a série desta ferramenta"
SERIE = 977
MIN_CORTES = 12
MODALIDADES = ("MR", "CT")
MOTIVO_MODALIDADE = "O T1 sintético é feito a partir de uma RM ou TC do crânio."
MODELO = "SynthSR 1.0"
CHAVE_SAIDA = "synthsr"
ESCALA = 100.0                        # o trabalhador devolve cinza (0–128) × 100
AVISO = ("imagem sintética: serve para medir a anatomia; lesões podem não aparecer ou mudar de aspecto — "
         "não use para procurar nem caracterizar lesão")

CHAVE_AUTO = "synthsr.auto"
CHAVE_EXAME_CONTEM = "synthsr.exame_contem"
CHAVE_MODALIDADES = "synthsr.modalidades"
CHAVE_PRIOR_CT = "synthsr.prioridade"
CHAVE_ESPESSURA = "synthsr.espessura_max"
CHAVE_MIN_CORTES = "synthsr.min_cortes"
CHAVE_DESTINOS = "synthsr.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "CRANIO|CRÂNIO|ENCEFALO|ENCÉFALO|BRAIN|HEAD|HIPOCAMPO|PARKINSON|NEURO",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "T1|FLAIR|T2",
    CHAVE_ESPESSURA: 7.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("SYNTHSR", "ADC", "DWI", "DIF", "SWI", "SWAN", "PHA", "PERF", "DSC", "ASL", "TOF", "MIP",
                      "SCOUT", "LOCALIZER", "CALIBRA", "T2*", "GRE", "POS", "PÓS", "GD")}
NOME_CADIA = "T1 sintético (SynthSR)"
TITULO_CADIA = "T1 sintético de 1 mm a partir de uma série 2D do crânio (SynthSR)"
EXPLICACAO_CADIA = ("Cria no exame uma série T1 de 1 mm, isotrópica, a partir de uma série de qualquer contraste e "
                    "espessura (por exemplo o sagital T1 de 5 mm), para abrir no MPR e medir os índices do crânio "
                    "quando o protocolo não tem T1 3D. É imagem sintética: serve para medir a anatomia, não para "
                    "procurar lesão. Na chegada, só roda nos exames que não têm uma série fina (até 1,5 mm).")
#: na chegada: exame com uma série assim já tem MPR bom — o sintético não acrescenta
FINO_MM = 1.5


def config(settings, chave):
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def tem_serie_fina(repo, study_uid: str) -> bool:
    """O exame já tem uma série de RM/TC fina (≤ 1,5 mm) com cortes bastantes para um MPR."""
    from ipe.ai import totalseg as TS
    try:
        for s in repo.series_for_study(study_uid):
            if (s.modality or "").upper() not in MODALIDADES or MARCA in (s.description or ""):
                continue
            if (s.num_images or 0) < 60:
                continue
            esp = TS._espessura(repo, s.series_uid)
            if esp is not None and esp <= FINO_MM + 1e-6:
                return True
    except Exception:  # noqa: BLE001
        log.exception("procurar série fina")
    return False


def exame_serve(info: dict, settings=None) -> bool:
    from ipe.ai import totalseg as TS
    return TS.exame_serve(info, settings, PERFIL, config)


def escolher_serie(repo, study_uid: str, settings=None):
    from ipe.ai import totalseg as TS
    try:
        info = repo.study_info(study_uid) or {}
    except Exception:  # noqa: BLE001
        info = {}
    if info and not exame_serve(info, settings):
        return None, "o T1 sintético é para a RM do crânio"
    if tem_serie_fina(repo, study_uid):
        return None, "o exame já tem uma série fina (até 1,5 mm): o T1 sintético não é necessário"
    return TS.escolher_serie(repo, study_uid, settings, PERFIL, config, min_absoluto=MIN_CORTES)


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SERIE)


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    return [{"nome": "synthsr", "rotulo": "T1 sintético (SynthSR)", "ct": (modalidade or "").upper() == "CT"}]


# ------------------------------------------------------------------ a "conta": só recolhe a imagem
@dataclass
class Resultado:
    imagem: np.ndarray | None = None          # (i, j, k) int16, cinza × ESCALA, eixos perto de RAS
    afim: np.ndarray | None = None            # RAS, 1 mm
    origem: str = ""                          # descrição da série de origem
    espessura: float | None = None
    n_origem: int = 0
    avisos: list = field(default_factory=list)
    versao: str = ""
    series_uid: str = ""                      # a série de origem
    nova_serie: str = ""
    calculado: bool = False


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", "") or MODELO, series_uid=t.series_uid, calculado=True,
                    origem=t.descricao_serie or t.series_uid[-8:], espessura=float(abs(vol.dz)),
                    n_origem=int(vol.data.shape[0]))
    extra = (getattr(t, "extras", None) or {}).get("synthsr")
    if extra is None:
        res.avisos.append("o SynthSR não devolveu a imagem")
        return res
    img, afim = extra
    img = np.asarray(img)
    if img.ndim != 3 or min(img.shape) < 8 or not (img > 0).any():
        res.avisos.append("o SynthSR devolveu uma imagem vazia")
        return res
    res.imagem, res.afim = img, np.asarray(afim, float)
    if (t.modalidade or "").upper() == "CT":
        res.avisos.append("feito a partir de TC: o resultado costuma ser pior que o da RM")
    if res.n_origem < 20:
        res.avisos.append(f"série de origem com só {res.n_origem} cortes: confira a anatomia entre os cortes")
    res.avisos.append(AVISO)
    return res


def geometria(afim: np.ndarray, forma: tuple) -> dict:
    """Cortes axiais (eixo 2 do volume) em DICOM (LPS). O pixel (linha r, coluna c) do corte k é o voxel
    [nx−1−c, ny−1−r, k]: colunas para a esquerda do paciente, linhas para trás, como um axial de aparelho."""
    A = np.asarray(afim, float)
    lps = np.diag([-1.0, -1.0, 1.0])
    a0, a1, a2 = (lps @ A[:3, k] for k in range(3))
    nx, ny, _nz = forma
    canto = lps @ (A[:3, :3] @ np.array([nx - 1, ny - 1, 0.0]) + A[:3, 3])
    return {"linha": -a0 / np.linalg.norm(a0), "coluna": -a1 / np.linalg.norm(a1), "passo": a2, "canto": canto,
            "dx": float(np.linalg.norm(a0)), "dy": float(np.linalg.norm(a1)), "dz": float(np.linalg.norm(a2))}


_DO_PACIENTE = ["PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "PatientWeight",
                "StudyInstanceUID", "StudyDate", "StudyTime", "StudyID", "AccessionNumber", "StudyDescription",
                "ReferringPhysicianName", "InstitutionName", "BodyPartExamined", "FrameOfReferenceUID"]


def datasets(res: Resultado, origem_dcm: str, serie_uid: str | None = None):
    """Um Dataset por corte axial da imagem sintética (gerador)."""
    import pydicom
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    src = pydicom.dcmread(origem_dcm, stop_before_pixels=True, force=True)
    g = geometria(res.afim, res.imagem.shape)
    serie = serie_uid or generate_uid()
    agora = datetime.now()
    sop_class = "1.2.840.10008.5.1.4.1.1.4"           # MR Image Storage: é um "T1" para as ferramentas
    nz = res.imagem.shape[2]
    fontes = None
    try:
        from ipe.imaging.derived import sequencia_de_origem
        fontes = sequencia_de_origem([str(src.get("SOPInstanceUID", ""))], str(src.get("SOPClassUID", "")))
    except Exception:  # noqa: BLE001
        fontes = None
    for k in range(nz):
        ds = pydicom.Dataset()
        for kw in _DO_PACIENTE:
            if kw in src:
                setattr(ds, kw, src.data_element(kw).value)
        meta = FileMetaDataset()
        sop = generate_uid()
        meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID = sop_class, sop
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = sop_class, sop
        ds.Modality = "MR"
        ds.SeriesInstanceUID, ds.SeriesNumber, ds.SeriesDescription = serie, SERIE, DESC_SERIE
        ds.InstanceNumber = k + 1
        ds.ImageType = ["DERIVED", "SECONDARY", "SYNTHETIC"]
        ds.Manufacturer = "Ipe"
        ds.DerivationDescription = (f"Ipe: imagem SINTETICA por IA ({MODELO}) a partir da serie "
                                    f"'{res.origem}' ({res.n_origem} cortes de {res.espessura:.1f} mm). "
                                    f"Nao e aquisicao; lesoes podem nao aparecer.")[:1024]
        ds.ImageComments = "SINTETICA (SynthSR): medir anatomia; nao usar para lesao"
        if fontes:
            ds.SourceImageSequence = fontes
        ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
        ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
        pos = g["canto"] + k * g["passo"]
        ds.ImagePositionPatient = [f"{x:.4f}" for x in pos]
        ds.ImageOrientationPatient = [f"{x:.6f}" for x in (*g["linha"], *g["coluna"])]
        ds.PixelSpacing = [f"{g['dy']:.6f}", f"{g['dx']:.6f}"]
        ds.SliceThickness = f"{g['dz']:.4f}"
        ds.SpacingBetweenSlices = f"{g['dz']:.4f}"
        raw = np.ascontiguousarray(res.imagem[::-1, ::-1, k].T).astype(np.int16)
        ds.Rows, ds.Columns = raw.shape
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
        ds.RescaleSlope, ds.RescaleIntercept = "1", "0"
        ds.WindowCenter, ds.WindowWidth = f"{64 * ESCALA:.0f}", f"{128 * ESCALA:.0f}"
        ds.PixelData = raw.tobytes()
        yield ds


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    from ipe.db.repository import Repository
    from ipe.imaging.derived import _miniaturas
    from ipe.importer.scanner import Importer
    repo = repo or Repository(db)
    out = {"series": [], "ferramenta": FERRAMENTA, "achados": []}
    if res.imagem is None:
        return out
    for se in repo.series_for_study(t.study_uid):          # refeito: troca a série anterior
        if (se.description or "") == DESC_SERIE:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar o T1 sintético anterior")
    tmp = Path(tempfile.mkdtemp(prefix="ipe_synthsr_"))
    try:
        serie = None
        for k, ds in enumerate(datasets(res, t.vol.source_path)):
            serie = str(ds.SeriesInstanceUID)
            ds.save_as(tmp / f"{k + 1:05d}.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        try:
            _miniaturas(db, r)
        except Exception:  # noqa: BLE001
            log.exception("miniatura do T1 sintético")
        res.nova_serie = serie or ""
        out["series"] = sorted(getattr(r, "new_series", None) or ([serie] if serie else []))
        out["nova_serie"] = res.nova_serie
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def resumo(res: Resultado) -> str:
    if res.imagem is None:
        return res.avisos[0] if res.avisos else "sem imagem"
    nx, ny, nz = res.imagem.shape
    return f"{nz} cortes de 1 mm ({nx} × {ny}) a partir de “{res.origem}”"


def n_itens(res: Resultado) -> int:
    return int(res.imagem is not None)


def mensagem(res: Resultado, minutos: float) -> str:
    if res.imagem is None:
        return "O T1 sintético não saiu: " + ("; ".join(res.avisos) or "sem imagem") + "."
    msg = (f"T1 sintético pronto em {minutos:.1f} min — {resumo(res)}. Está no exame como a série "
           f"“{DESC_SERIE}”: arraste para um quadro e abra o MPR.")
    msg += "\n\nAtenção: " + "; ".join(res.avisos) + "."
    return msg


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    return []
