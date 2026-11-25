"""0.100.119: **Dinâmica da mama: alinhar as fases** — a correção de movimento como uma IA que grava séries novas.

Pedido dele (25/11/2026): *"quero colocar a correção de movimento do dinâmico da mama como uma "ia", para poder rodar
sempre que o exame entre no Ipê. Pra isso tem que gerar novas imagens"* — com o método do projeto antigo dele
(dce-align): registro **conjunto e deformável em 3D** do elastix, e não só a translação/rotação que o visualizador
corrige na hora.

O que acontece:

1. acha a dinâmica do exame (as mesmas fases que o visualizador usa: `automation.dinamica.series_da_dinamica`);
2. grava as fases em arquivos temporários e chama o **trabalhador** (`dce_trabalhador.py`) no ambiente próprio
   `venv_dce` (itk-elastix, instalado à parte, ~1,5 GB em disco): registro conjunto no plano reduzido e a
   transformação aplicada na resolução cheia;
3. a **porta do movimento**: se o registro não tirou pelo menos `min_pct` % do resíduo |pós − pré| (o realce fica,
   o desalinhamento sai), o exame não tem movimento que valha corrigir e **nada é gravado**;
4. senão grava no próprio exame, **cada fase alinhada** ("Dinâmica alinhada N · Ipê") e as **subtrações** pós − pré
   ("Subtração alinhada N · Ipê"), com a mesma geometria das originais. As originais não são tocadas.

As séries gravadas levam `ImageType` DERIVED\\SECONDARY (as subtrações também SUBTRACT): a detecção da dinâmica do
visualizador as ignora (não viram "mais fases"), e o selo "IA" aparece nas miniaturas pelo " · Ipê" no nome.

Só dinâmicas em arquivos de um corte por imagem (a RM de mama clássica). Sem Qt.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FERRAMENTA = "dce_alinhar"
TITULO = "Dinâmica da mama: alinhar as fases"
CHAVE_AUTO = "mama.dce_alinhar_na_chegada"
CHAVE_MIN_PCT = "mama.dce_alinhar_min_pct"
CHAVE_SUBTRACOES = "mama.dce_alinhar_subtracoes"
CHAVE_GRADE = "mama.dce_alinhar_grade_mm"
CHAVE_DESTINOS = "mama.dce_alinhar_destinos"
PADROES = {CHAVE_AUTO: False, CHAVE_MIN_PCT: 12.0, CHAVE_SUBTRACOES: True, CHAVE_GRADE: 32.0, CHAVE_DESTINOS: []}

MARCA = "· Ipê"
DESC_FASE = "Dinâmica alinhada {} " + MARCA
DESC_SUB = "Subtração alinhada {} " + MARCA
PREFIXOS = ("Dinâmica alinhada ", "Subtração alinhada ")
SERIE_FASE, SERIE_SUB = 8000, 8100
MIN_FASES = 3
#: uma por vez no processo: o registro usa a CPU inteira e vários GB de memória
TRAVA = threading.Lock()


class Cancelado(Exception):
    pass


def config(settings, chave):
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def ligado(settings) -> bool:
    return bool(config(settings, CHAVE_AUTO))


# ------------------------------------------------------------------ o ambiente do elastix
def pasta_ambiente() -> Path:
    from ipe.ai import totalseg as TS
    return TS.pasta_base() / "venv_dce"


def python_do_ambiente() -> Path | None:
    base = pasta_ambiente()
    return next((c for c in (base / "Scripts" / "python.exe", base / "bin" / "python") if c.is_file()), None)


def disponivel(settings=None) -> tuple[bool, str]:
    if os.environ.get("IPE_DCE_PYTHON") and Path(os.environ["IPE_DCE_PYTHON"]).is_file():
        return True, ""
    if python_do_ambiente() is None:
        return False, ("falta o ambiente do alinhamento da dinâmica (elastix): Configurações ▸ CAD/IA ▸ Instalar o "
                       "alinhamento da dinâmica da mama…")
    return True, ""


def _python() -> Path:
    env = os.environ.get("IPE_DCE_PYTHON")
    if env and Path(env).is_file():
        return Path(env)
    py = python_do_ambiente()
    if py is None:
        raise RuntimeError(disponivel()[1])
    return py


def caminho_do_trabalhador() -> Path:
    perto = Path(__file__).with_name("dce_trabalhador.py")
    if perto.is_file():
        return perto
    from ipe.core.runtime import resource_dir
    return resource_dir() / "ai" / "dce_trabalhador.py"


# ------------------------------------------------------------------ o que serve
def exame_serve(info: dict, settings=None) -> bool:
    return "MR" in str((info or {}).get("modalities") or "").upper()


def e_nossa(descricao: str) -> bool:
    d = descricao or ""
    return d.startswith(PREFIXOS) and MARCA in d


def ja_feita(repo, study_uid: str) -> bool:
    return any(e_nossa(s.description) for s in repo.series_for_study(study_uid, ocultas=True))


def fases_do_exame(repo, study_uid: str) -> list[tuple[str, list]]:
    """[(series_uid, quadros)] das fases da dinâmica, em ordem — as mesmas do visualizador."""
    from ipe.automation import dinamica as D
    return D.series_da_dinamica(repo, study_uid)


def escolher_serie(repo, study_uid: str, settings=None) -> tuple[str | None, str]:
    """(série da pré-contraste, motivo): para a lista de IAs do exame."""
    ok, motivo = disponivel(settings)
    if not ok:
        return None, motivo
    fases = fases_do_exame(repo, study_uid)
    if len(fases) < MIN_FASES:
        return None, "o exame não tem uma dinâmica de mama (pré + pelo menos 2 fases pós)"
    return fases[0][0], ""


# ------------------------------------------------------------------ ler e gravar
def _espaco(quadros: list, img) -> tuple[float, float, float]:
    """(dx, dy, dz) em mm: coluna, linha e corte."""
    rs, cs = img.pixel_spacing or (1.0, 1.0)
    dz = 1.0
    try:
        if len(quadros) > 1 and quadros[0].position is not None and quadros[1].position is not None:
            dz = float(np.linalg.norm(np.asarray(quadros[1].position, float)
                                      - np.asarray(quadros[0].position, float))) or 1.0
    except (TypeError, ValueError):
        pass
    return float(cs), float(rs), dz


def ler_fase(quadros: list) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Volume (corte, linha, coluna) float32 de uma fase, em unidades reais."""
    from ipe.imaging.series import read_frame
    cortes, esp = [], None
    for q in quadros:
        if q.frame_index > 0 or q.n_frames > 1:
            raise ValueError("dinâmica em arquivo multiframe (Enhanced MR): ainda não é suportada")
        im = read_frame(q)
        if im.is_color or im.pixels.ndim != 2:
            raise ValueError("a dinâmica tem imagens coloridas")
        if esp is None:
            esp = _espaco(quadros, im)
        cortes.append(np.asarray(im.pixels, np.float32))
    return np.stack(cortes), esp


def _para_inteiros(vol: np.ndarray) -> tuple[np.ndarray, float]:
    """(uint16, RescaleSlope): os valores reais cabem direto em uint16 (inclinação 1) quando dá."""
    v = np.nan_to_num(vol, nan=0.0, posinf=0.0, neginf=0.0)
    v = np.clip(v, 0, None)
    pico = float(v.max()) if v.size else 0.0
    if pico <= 65535:
        return np.rint(v).astype(np.uint16), 1.0
    slope = pico / 65535.0
    return np.rint(v / slope).astype(np.uint16), slope


def datasets_da_serie(quadros: list, vol: np.ndarray, descricao: str, numero: int, serie_uid: str,
                      versao: str, subtracao: bool = False, nota: str = ""):
    """Um Dataset por corte, com o cabeçalho do corte original (mesma geometria) e a imagem nova."""
    import pydicom
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    from datetime import datetime
    inteiros, slope = _para_inteiros(vol)
    agora = datetime.now()
    janela = None
    if subtracao:
        alvo = vol[vol > 0]
        pico = float(np.percentile(alvo, 99.5)) if alvo.size else 1.0
        janela = (max(pico, 1.0), max(pico, 1.0) / 2)
    for k, q in enumerate(quadros):
        ds = pydicom.dcmread(q.path, force=True)
        sop_origem, classe = str(ds.get("SOPInstanceUID", "")), str(ds.get("SOPClassUID", ""))
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        sop = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID = sop
        ds.SeriesInstanceUID = serie_uid
        ds.SeriesDescription = descricao
        ds.SeriesNumber = numero
        ds.InstanceNumber = k + 1
        tipo = ["DERIVED", "SECONDARY", "ALIGNED"] + (["SUBTRACT"] if subtracao else [])
        ds.ImageType = tipo
        ds.Manufacturer = "Ipe"
        ds.SoftwareVersions = f"Ipe {versao}"
        ds.DerivationDescription = (f"Ipe: {nota}" if nota else "Ipe: dinâmica alinhada")[:1024]
        ds.ImageComments = "ALINHADA por IA (elastix): conferir com a original; nao e aquisicao"
        try:
            from ipe.imaging.derived import sequencia_de_origem
            ds.SourceImageSequence = sequencia_de_origem([sop_origem], classe)
        except Exception:  # noqa: BLE001
            pass
        ds.ContentDate, ds.ContentTime = agora.strftime("%Y%m%d"), agora.strftime("%H%M%S")
        ds.SeriesDate, ds.SeriesTime = ds.ContentDate, ds.ContentTime
        for kw in ("SmallestImagePixelValue", "LargestImagePixelValue", "ModalityLUTSequence", "VOILUTSequence",
                   "PixelPaddingValue", "PixelPaddingRangeLimit", "LossyImageCompression",
                   "LossyImageCompressionRatio", "LossyImageCompressionMethod"):
            if kw in ds:
                del ds[kw]
        raw = np.ascontiguousarray(inteiros[k])
        ds.Rows, ds.Columns = raw.shape
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
        ds.RescaleSlope, ds.RescaleIntercept = f"{slope:.8g}", "0"
        if janela:
            ds.WindowWidth, ds.WindowCenter = f"{janela[0]:.0f}", f"{janela[1]:.0f}"
        ds.PixelData = raw.tobytes()
        ds["PixelData"].VR = "OW"
        yield ds


def _apagar_anteriores(repo, study_uid: str, storage) -> int:
    n = 0
    for se in repo.series_for_study(study_uid, ocultas=True):
        if e_nossa(se.description):
            try:
                repo.delete_series(se.series_uid, Path(storage))
                n += 1
            except Exception:  # noqa: BLE001
                log.exception("trocar a dinâmica alinhada anterior")
    return n


# ------------------------------------------------------------------ o trabalho
def _chamar_trabalhador(pasta: Path, progresso=None, cancelar: threading.Event | None = None) -> dict:
    py = _python()
    env = dict(os.environ)
    for k in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(k, None)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [str(py), "-I", str(caminho_do_trabalhador()), str(pasta)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", env=env, creationflags=flags)
    ultimas: list[str] = []

    def ler():
        for linha in proc.stdout:
            linha = linha.rstrip()
            if not linha:
                continue
            ultimas.append(linha)
            del ultimas[:-30]
            if linha.startswith("ETAPA ") and progresso:
                progresso(linha[6:])
    t = threading.Thread(target=ler, daemon=True)
    t.start()
    while proc.poll() is None:
        if cancelar is not None and cancelar.is_set():
            proc.kill()
            proc.wait()
            raise Cancelado()
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
    t.join(timeout=5)
    arq = pasta / "saida.json"
    saida = json.loads(arq.read_text("utf-8")) if arq.is_file() else {}
    if proc.returncode != 0 or saida.get("erro"):
        raise RuntimeError(saida.get("erro") or ("o elastix falhou: " + " | ".join(ultimas[-3:])))
    return saida


def processar(repo, db, storage_root, study_uid: str, settings=None, progresso=None, forcar: bool = False,
              cancelar: threading.Event | None = None, travar: bool = True) -> dict:
    """Devolve {"fases", "movimento_pct", "sem_movimento", "series", "geradas", "aviso"}."""
    from ipe import __version__
    from ipe.db.repository import Repository
    from ipe.imaging.derived import _miniaturas
    from ipe.importer.scanner import Importer
    from pydicom.uid import generate_uid
    ok, motivo = disponivel(settings)
    if not ok:
        raise RuntimeError(motivo)
    repo = repo or Repository(db)
    fases = fases_do_exame(repo, study_uid)
    if len(fases) < MIN_FASES:
        return {"fases": len(fases), "geradas": 0, "series": [], "sem_movimento": False,
                "aviso": "o exame não tem uma dinâmica de mama (pré + pelo menos 2 fases pós)"}
    if not forcar and ja_feita(repo, study_uid):
        return {"fases": len(fases), "geradas": 0, "series": [], "sem_movimento": False,
                "aviso": "o exame já tem a dinâmica alinhada"}
    def etapa(t: str) -> None:
        if progresso:
            progresso(t)
        if cancelar is not None and cancelar.is_set():
            raise Cancelado()
    with (TRAVA if travar else contextlib.nullcontext()):
        tmp = Path(tempfile.mkdtemp(prefix="ipe_dce_"))
        try:
            etapa("lendo as imagens das fases")
            nomes, esp, vols = [], None, []
            for k, (_uid, quadros) in enumerate(fases):
                vol, e = ler_fase(quadros)
                if vols and vol.shape != vols[0].shape:
                    raise ValueError(f"a fase {k + 1} tem {vol.shape[0]} cortes de {vol.shape[1]}×{vol.shape[2]}; "
                                     f"a primeira tem {vols[0].shape[0]} de {vols[0].shape[1]}×{vols[0].shape[2]}")
                vols.append(vol)
                esp = esp or e
                np.save(tmp / f"fase{k}.npy", vol)
                nomes.append(f"fase{k}.npy")
            (tmp / "entrada.json").write_text(json.dumps({
                "fases": nomes, "espaco": list(esp), "reduzir": max(1, int(np.ceil(max(vols[0].shape[1:]) / 256))),
                "grade_mm": float(config(settings, CHAVE_GRADE)), "min_pct": float(config(settings, CHAVE_MIN_PCT)),
                "forcar": bool(forcar), "iteracoes": 256, "amostras": 2048}), encoding="utf-8")
            del vols
            saida = _chamar_trabalhador(tmp, progresso, cancelar)
            res = {"fases": len(fases), "movimento_pct": saida.get("movimento_pct"), "series": [], "geradas": 0,
                   "sem_movimento": bool(saida.get("sem_movimento")), "segundos": saida.get("segundos")}
            if res["sem_movimento"]:
                return res
            etapa("gravando as fases alinhadas no exame")
            alinhadas = [np.load(tmp / f"alinhada{k}.npy") for k in range(len(fases))]
            _apagar_anteriores(repo, study_uid, storage_root)
            saida_dcm = tmp / "dcm"
            saida_dcm.mkdir()
            nota = (f"{len(fases)} fases alinhadas por registro conjunto (elastix, grade {saida['grade_mm']:g} mm); "
                    f"o movimento tirou {saida['movimento_pct']:.1f}% do residuo pos-pre")
            n = 0
            for k, (_uid, quadros) in enumerate(fases):
                uid = generate_uid()
                for i, ds in enumerate(datasets_da_serie(quadros, alinhadas[k], DESC_FASE.format(k + 1),
                                                         SERIE_FASE + k + 1, uid, __version__, nota=nota)):
                    ds.save_as(saida_dcm / f"f{k:02d}_{i:05d}.dcm", enforce_file_format=True)
                    n += 1
            if config(settings, CHAVE_SUBTRACOES):
                pre = alinhadas[0]
                for k in range(1, len(fases)):
                    sub = np.clip(alinhadas[k] - pre, 0, None)
                    uid = generate_uid()
                    for i, ds in enumerate(datasets_da_serie(fases[k][1], sub, DESC_SUB.format(k), SERIE_SUB + k, uid,
                                                             __version__, subtracao=True,
                                                             nota=f"fase {k + 1} menos a pre-contraste, alinhadas")):
                        ds.save_as(saida_dcm / f"s{k:02d}_{i:05d}.dcm", enforce_file_format=True)
                        n += 1
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([saida_dcm])
            try:
                _miniaturas(db, r)
            except Exception:  # noqa: BLE001
                log.exception("miniaturas da dinâmica alinhada")
            res["series"] = sorted(getattr(r, "new_series", None) or [])
            res["geradas"] = len(res["series"])
            res["imagens"] = n
            return res
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def resumo(res: dict) -> str:
    if res.get("aviso"):
        return res["aviso"]
    if res.get("sem_movimento"):
        return f"sem movimento que valha corrigir ({(res.get('movimento_pct') or 0):.1f}% do resíduo)"
    return (f"{res.get('fases', 0)} fases alinhadas ({(res.get('movimento_pct') or 0):.1f}% do resíduo tirado), "
            f"{res.get('geradas', 0)} série(s) gravada(s)")
