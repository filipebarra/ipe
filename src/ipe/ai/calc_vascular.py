"""Calcificações vasculares da mama (calcificação arterial) na mamografia — 0.100.51.

Pedido dele (15/11/2026): *"quero tentar identificar calcificações vasculares na mamografia … não quero nada somente
para pesquisa"*; graduação combinada: **ausente, leve, moderada ou acentuada** (a escala de pontos vem depois da
validação).

A rede é a **SCU-Net** de Guo, O'Neill, Vey, Yang, Kim, Ghassemi, Pan, Gichoya, Trivedi e Banerjee, *SCU-Net: A deep
learning method for segmentation and quantification of breast arterial calcifications on mammograms*, Med Phys
2021;48:5851–61 (https://github.com/Emory-HITI/BAC_segmentation), licença **MIT**, treinada pelos autores em
mamografias digitais da Emory. Usamos o peso `SCU_Net_512_512_best_BCE_pos_all.pt` ("o que funciona melhor em
imagens com e sem calcificação"), convertido para ONNX sem alteração (diferença para o PyTorch ≤ 1,1 × 10⁻⁵).

O preparo segue o código dos autores (`utils.py`/`dataset.py`): a imagem em 8 bits (aqui: com a janela/LUT do
próprio arquivo, tecido claro), filtro de mediana 5 × 5, pedaços de 512 × 512 a cada 480 pixels (pula os de fundo:
média ≤ 20 ou desvio ≤ 10), normalização (x/255 − 0,2813)/0,1256 em três canais iguais; o mapa da imagem inteira é o
máximo dos pedaços. Pixel de calcificação: saída > 0,65 (o limiar do `AutoSeg.py`; aqui depois da sigmoide).

Quantidade: área segmentada em mm² (pelo espaçamento do detector) por incidência; por mama, a maior entre CC e MLO.
Conta para a sugestão só o que é **alongado** (pedaço com ≥ `COMPRIMENTO_MIN` mm no maior lado), o jeito do vaso; os
pontinhos isolados ficam na área total, à parte. A **sugestão** de grau pela área é provisória (cortes em `CORTES`):
o que vale é a confirmação do médico, guardada com as áreas para calibrar depois.

**Prótese**: no primeiro teste nos exames dele (6 exames, 15/11/2026), a borda da prótese virou "calcificação" (até
180 mm² numa incidência; num deles o aparelho nem declarava a prótese). A região da prótese é achada na imagem
(grande, lisa e clara na média em blocos de 16 pixels) e o que cai nela e numa faixa de `FAIXA_PROTESE_MM` mm em volta
é descartado, com aviso.
"""
from __future__ import annotations

import base64
import logging
import zlib
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

ARQUIVO = "calc_vascular_scunet.onnx"
MODULO = "calc_vascular"
VERSAO = 4                 # 0.100.52: todas as imagens 2D; 0.100.55: escalas; 0.100.60: refaz as automáticas que falharam
GRAUS = ("ausente", "leve", "moderada", "acentuada")
NOMES = {"ausente": "Ausente", "leve": "Leve", "moderada": "Moderada", "acentuada": "Acentuada"}
#: área (mm², na mama com mais) a partir da qual a sugestão sobe de grau — PROVISÓRIO, até as confirmações dele
CORTES = (5.0, 30.0, 100.0)
LIMIAR = 0.65
COMPRIMENTO_MIN = 3.0
FAIXA_PROTESE_MM = 5.0
PEDACO, PASSO = 512, 480
MEDIA, DESVIO = 0.2813, 0.1256
#: a máscara guardada fica em 1/ESCALA da imagem (só para mostrar)
ESCALA = 4

_sessao = None
_de_onde = ""


def pastas(dados: Path | None = None) -> list:
    from ipe.ai import densidade_nyu as N
    return N.pastas(dados)


def caminho(dados: Path | None = None) -> Path | None:
    for p in pastas(dados):
        f = Path(p) / ARQUIVO
        if f.is_file():
            return f
    return None


def disponivel(dados: Path | None = None) -> tuple[bool, str]:
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False, "falta o onnxruntime"
    if caminho(dados) is None:
        return False, "sem o modelo"
    return True, ""


def sessao(dados: Path | None = None):
    global _sessao, _de_onde
    f = caminho(dados)
    if f is None:
        raise FileNotFoundError("modelo da calcificação vascular não encontrado")
    if _sessao is None or _de_onde != str(f):
        import onnxruntime as ort
        op = ort.SessionOptions()
        op.intra_op_num_threads = 2
        _sessao = ort.InferenceSession(str(f), op, providers=["CPUExecutionProvider"])
        _de_onde = str(f)
    return _sessao


# ------------------------------------------------------------------ preparo
def oito_bits(ds) -> np.ndarray:
    """A imagem como a tela mostra (janela/LUT do arquivo, tecido claro), em 0–255."""
    from ipe.imaging import density as D
    from ipe.imaging.mammo import display_values
    bruto = ds.pixel_array
    if getattr(bruto, "ndim", 0) != 2:
        raise ValueError("só imagem 2D")
    a = display_values(D._na_janela(ds, bruto),
                       str(getattr(ds, "PhotometricInterpretation", "")) == "MONOCHROME1").astype(np.float32)
    lo, hi = float(np.min(a)), float(np.max(a))
    if hi <= lo:
        return np.zeros(a.shape, np.uint8)
    return np.clip((a - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def mediana5(img: np.ndarray, faixa: int = 256) -> np.ndarray:
    """Mediana 5 × 5 (o cv2.medianBlur dos autores; sem o OpenCV, em numpy, por faixas de linhas)."""
    try:
        import cv2
        return cv2.medianBlur(np.ascontiguousarray(img, dtype=np.uint8), 5)
    except ImportError:
        pass
    from numpy.lib.stride_tricks import sliding_window_view
    p = np.pad(img, 2, mode="edge")
    out = np.empty_like(img)
    for y in range(0, img.shape[0], faixa):
        bloco = p[y:y + faixa + 4]
        jan = sliding_window_view(bloco, (5, 5)).reshape(bloco.shape[0] - 4, img.shape[1], 25)
        out[y:y + faixa] = np.partition(jan, 12, axis=-1)[..., 12]
    return out


def inicios(n: int) -> list[int]:
    """Onde começam os pedaços (get_slices dos autores)."""
    if n <= PEDACO:
        return [0]
    s = []
    for i in range(0, n, PASSO):
        if i + PEDACO >= n:
            s.append(n - PEDACO)
            break
        s.append(i)
    return s


def mapa(img8: np.ndarray, dados=None, stop=None) -> np.ndarray:
    """Probabilidade de calcificação vascular por pixel (0–1), da imagem inteira."""
    s = sessao(dados)
    h, w = img8.shape
    alto, largo = max(h, PEDACO), max(w, PEDACO)
    if (alto, largo) != (h, w):                      # imagem menor que o pedaço: completa com fundo
        g = np.zeros((alto, largo), np.uint8)
        g[:h, :w] = img8
        img8 = g
    prob = np.zeros(img8.shape, np.float32)
    lote, onde = [], []

    def roda():
        x = np.stack(lote).astype(np.float32)
        x = ((x / 255.0 - MEDIA) / DESVIO)[:, None]
        x = np.repeat(x, 3, axis=1)
        y = s.run(None, {"imagem": x})[0][:, 0]
        y = 1.0 / (1.0 + np.exp(-y))
        for (i, j), p in zip(onde, y):
            np.maximum(prob[i:i + PEDACO, j:j + PEDACO], p, out=prob[i:i + PEDACO, j:j + PEDACO])
        lote.clear()
        onde.clear()
    # 0.100.60: `stop` pode ser uma função ou um threading.Event (a fila automática passava o Event e a conta falhava)
    if stop is not None and hasattr(stop, "is_set"):
        stop = stop.is_set
    for i in inicios(img8.shape[0]):
        for j in inicios(img8.shape[1]):
            if stop is not None and stop():
                raise InterruptedError("cancelado")
            p = img8[i:i + PEDACO, j:j + PEDACO]
            if p.mean() <= 20 or p.std() <= 10:
                continue
            lote.append(p)
            onde.append((i, j))
            if len(lote) == 4:
                roda()
    if lote:
        roda()
    return prob[:h, :w]



def compactar(m: np.ndarray) -> str:
    return base64.b64encode(zlib.compress(np.packbits(m.astype(bool)).tobytes(), 9)).decode("ascii")


def descompactar(txt: str, forma) -> np.ndarray:
    bits = np.unpackbits(np.frombuffer(zlib.decompress(base64.b64decode(txt)), np.uint8))
    return bits[:forma[0] * forma[1]].reshape(forma).astype(bool)


def reduzir(m: np.ndarray, k: int = ESCALA) -> np.ndarray:
    """Máscara em 1/k (um pixel reduzido acende se qualquer um do bloco acende)."""
    h, w = (m.shape[0] // k) * k, (m.shape[1] // k) * k
    r = m[:h, :w].reshape(h // k, k, w // k, k).any(axis=(1, 3))
    return r


def tem_protese(ds) -> bool:
    return str(getattr(ds, "BreastImplantPresent", "") or "").upper() == "YES"


def regiao_da_protese(img8: np.ndarray, passo_mm: float) -> np.ndarray | None:
    """A prótese e a faixa em volta (bool, tamanho da imagem): a maior região lisa e clara dentro da mama, se for
    grande (≥ 8% da mama). None: não achou."""
    try:
        import cv2
    except ImportError:
        return None
    k = 16                                         # média em blocos de 16: o ruído da prótese some, a borda fica
    h, w = img8.shape
    p = cv2.resize(img8.astype(np.float32), (max(1, w // k), max(1, h // k)), interpolation=cv2.INTER_AREA)
    mu = cv2.blur(p, (5, 5))
    sd = np.sqrt(np.maximum(cv2.blur(p * p, (5, 5)) - mu * mu, 0))
    mama = p > 20
    if mama.sum() < 100:
        return None
    cand = (mama & (sd < 6) & (p > np.median(p[mama]))).astype(np.uint8)
    n, lab, st, _c = cv2.connectedComponentsWithStats(cand, connectivity=8)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[i, cv2.CC_STAT_AREA] < 0.08 * mama.sum():
        return None
    reg = (lab == i).astype(np.uint8)
    reg = cv2.morphologyEx(reg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    # preenche os buracos: o que o fundo (pela borda) não alcança é dentro
    fundo = np.zeros((reg.shape[0] + 2, reg.shape[1] + 2), np.uint8)
    cheio = reg.copy()
    cv2.floodFill(cheio, fundo, (0, 0), 1)
    reg = reg | (1 - cheio)
    # + 2 blocos: o desvio é medido numa janela de 5 blocos, então a região achada fica ~2 blocos para dentro da borda
    raio = max(1, round(FAIXA_PROTESE_MM / (passo_mm * k))) + 2
    reg = cv2.dilate(reg, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * raio + 1, 2 * raio + 1)))
    return cv2.resize(reg, (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)


def pedacos(m: np.ndarray, passo_mm: float) -> tuple[np.ndarray, list[dict]]:
    """Os pedaços segmentados com o tamanho de cada um; devolve também a máscara só dos alongados."""
    try:
        import cv2
    except ImportError:
        return m, []
    n, lab, st, _c = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    lista, longos = [], np.zeros(n, bool)
    for i in range(1, n):
        comp = max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) * passo_mm
        longos[i] = comp >= COMPRIMENTO_MIN
        lista.append({"comprimento_mm": round(float(comp), 1),
                      "area_mm2": round(float(st[i, cv2.CC_STAT_AREA]) * passo_mm * passo_mm, 2),
                      "alongado": bool(longos[i])})
    lista.sort(key=lambda x: -x["area_mm2"])
    return longos[lab], lista[:40]


def medir_imagem(ds, dados=None, stop=None) -> dict:
    from ipe.imaging import density as D
    img8 = oito_bits(ds)
    m = mapa(mediana5(img8), dados, stop) > LIMIAR
    passo = float(D.espacamento(ds) or 0.1)
    # a prótese: pelo arquivo ou pela imagem (num dos exames dele o aparelho não declarava)
    reg = regiao_da_protese(img8, passo)
    out = {"protese": tem_protese(ds) or reg is not None, "protese_achada": reg is not None,
           "descartado_protese_mm2": 0.0}
    if reg is not None:
        out["descartado_protese_mm2"] = round(float((m & reg).sum()) * passo * passo, 2)
        m &= ~reg
    longos, lista = pedacos(m, passo)
    from ipe.ai import calc_vascular_escalas as E
    try:
        out["tracado"] = E.caracteristicas(m, img8, passo)
    except Exception:
        log.warning("calcificação vascular: escalas", exc_info=True)
    total = float(m.sum()) * passo * passo
    area = float(longos.sum()) * passo * passo if lista else total
    red = reduzir(m)
    out.update({"area_mm2": round(area, 2), "area_total_mm2": round(total, 2), "pixels": int(m.sum()),
                "pedacos": lista, "passo_mm": passo, "forma": list(red.shape), "mascara": compactar(red)})
    return out


def grau_pela_area(area_mm2: float, cortes=CORTES) -> str:
    g = 0
    for c in cortes:
        if area_mm2 >= c:
            g += 1
    return GRAUS[g]


ORDEM = ("R-CC", "L-CC", "R-MLO", "L-MLO")
#: incidências que não são as quatro de rotina, pelo ViewPosition
OUTRAS = ("ML", "LM", "XCCL", "XCCM", "FB", "SIO", "LMO", "AT", "CV")


def _incidencia_livre(ds) -> str:
    from ipe.imaging import densidade_revisao as R
    v = R._incidencia(ds)
    if v:
        return v
    vp = str(getattr(ds, "ViewPosition", "") or "").upper().strip()
    return vp if vp in OUTRAS else (vp[:8] or "?")


def _modificadores(ds) -> list[str]:
    out = []
    for it in getattr(ds, "ViewModifierCodeSequence", None) or []:
        t = str(getattr(it, "CodeMeaning", "") or "").lower()
        if "spot" in t or "compress" in t:
            out.append("compressão localizada")
        elif "magnif" in t:
            out.append("ampliação")
        elif t:
            out.append(t)
    try:
        if float(getattr(ds, "EstimatedRadiographicMagnificationFactor", 1) or 1) > 1.3 and "ampliação" not in out:
            out.append("ampliação")
    except (TypeError, ValueError):
        pass
    return out


def imagens_do_exame(repo, study_uid: str) -> list[dict]:
    """0.100.52: **todas** as imagens 2D de mamografia do exame com lado — as de rotina, as repetidas, as outras
    incidências, a compressão localizada e a ampliação (a densidade usa só as quatro). Fora: a tomossíntese (cortes), a
    imagem "para processamento" e a sem lado. Em ordem: R-CC, L-CC, R-MLO, L-MLO, as outras; dentro, pela série e
    pelo número da imagem. `extra`: compressão localizada ou ampliação (aparece, mas não entra na conta da mama, porque
    a área sai maior)."""
    import pydicom

    from ipe.imaging import densidade_revisao as R
    lista = []
    for f in repo.files_for_study(study_uid):
        if not f:
            continue
        try:
            ds = pydicom.dcmread(str(f), stop_before_pixels=True, force=True)
        except Exception:
            log.debug("calcificação vascular: não li %s", f, exc_info=True)
            continue
        if str(getattr(ds, "Modality", "") or "").upper() != "MG":
            continue
        try:
            quadros = int(getattr(ds, "NumberOfFrames", 1) or 1)
        except (TypeError, ValueError):
            quadros = 1
        tipo = [str(x).upper() for x in (getattr(ds, "ImageType", None) or [])]
        if quadros > 1 or any(t in ("TOMO", "TOMOSYNTHESIS", "VOLUME") for t in tipo):
            continue
        if str(getattr(ds, "PresentationIntentType", "") or "").upper() == "FOR PROCESSING":
            continue
        lado = R._lado(ds)
        if not lado:
            continue
        inc = _incidencia_livre(ds)
        mods = _modificadores(ds)
        desc = str(getattr(ds, "SeriesDescription", "") or "").strip()
        lista.append({
            "caminho": str(f), "sop": str(getattr(ds, "SOPInstanceUID", "") or ""), "chave": f"{lado}-{inc}",
            "lado": lado, "incidencia": inc, "extra": bool(mods), "modificadores": mods, "serie": desc,
            "aparelho": " ".join(x for x in (str(getattr(ds, "Manufacturer", "") or "").strip(),
                                             str(getattr(ds, "ManufacturerModelName", "") or "").strip()) if x),
            "_ordem": (ORDEM.index(f"{lado}-{inc}") if f"{lado}-{inc}" in ORDEM else 9, inc, lado,
                       int(getattr(ds, "SeriesNumber", 0) or 0), int(getattr(ds, "InstanceNumber", 0) or 0),
                       str(getattr(ds, "AcquisitionTime", "") or "")),
        })
    lista.sort(key=lambda x: x["_ordem"])
    for x in lista:
        x.pop("_ordem")
    return lista


def medir_exame(repo, study_uid: str, dados=None, stop=None, cortes=CORTES) -> dict:
    """Todas as imagens 2D do exame (`imagens_do_exame`). Por mama, a maior área entre as imagens de campo inteiro."""
    import time
    from collections import Counter

    import pydicom
    if hasattr(repo, "is_cached") and not repo.is_cached(study_uid):
        repo.download(study_uid)
    lista = imagens_do_exame(repo, study_uid)
    chaves = {x["chave"] for x in lista}
    faltam = [k for k in ORDEM if k not in chaves]
    avisos = [f"Faltam incidências: {', '.join(faltam)}."] if lista and faltam else []
    aparelho = Counter(x["aparelho"] or "?" for x in lista).most_common(1)[0][0] if lista else ""
    out = {"versao": VERSAO, "modelo": "SCU-Net (Emory, MIT)", "limiar": LIMIAR, "cortes": list(cortes),
           "imagens": [], "vistas": {}, "por_mama": {}, "area_mm2": None, "sugestao": None, "aviso": "",
           "avisos": avisos, "aparelho": aparelho, "quando": time.strftime("%Y-%m-%d %H:%M")}
    ok, motivo = disponivel(dados)
    if not ok:
        out["aviso"] = motivo
        return out
    if not lista:
        out["aviso"] = "Nenhuma imagem de mamografia 2D com lado no exame."
        return out
    for x in lista:
        try:
            v = medir_imagem(pydicom.dcmread(x["caminho"], force=True), dados, stop)
        except InterruptedError:
            raise
        except Exception as e:
            log.warning("calcificação vascular: %s falhou", x["chave"], exc_info=True)
            out["avisos"].append(f"{x['chave']}: {e}")
            continue
        v.update({k: x[k] for k in ("sop", "chave", "lado", "incidencia", "extra", "modificadores", "serie")})
        out["imagens"].append(v)
    # a de cada incidência que entra na tela de resumo: a de maior área (campo inteiro antes)
    for v in out["imagens"]:
        atual = out["vistas"].get(v["chave"])
        if atual is None or (atual["extra"], -atual["area_mm2"]) > (v["extra"], -v["area_mm2"]):
            out["vistas"][v["chave"]] = v
    protese = any(v.get("protese") for v in out["imagens"])
    if protese:
        out["avisos"].append("Prótese: a borda da prótese engana a rede; o que cai nela e em volta fica fora da conta, "
                             "mas confira nas imagens. Sem sugestão de grau.")
    if any(v["extra"] for v in out["imagens"]):
        out["avisos"].append("Compressão localizada e ampliação aparecem, mas não entram na área da mama.")
    for lado in ("R", "L"):
        areas = [v["area_mm2"] for v in out["imagens"] if v["lado"] == lado and not v["extra"]]
        if not areas:
            areas = [v["area_mm2"] for v in out["imagens"] if v["lado"] == lado]
        if areas:
            out["por_mama"][lado] = max(areas)
    if out["por_mama"]:
        out["area_mm2"] = max(out["por_mama"].values())
        out["sugestao"] = None if protese else grau_pela_area(out["area_mm2"], cortes)
    out["escalas"] = escalas(out)
    return out


def escalas(m: dict) -> dict | None:
    """Margolies, CSBI, Loberant e BAC-SS estimadas (`calc_vascular_escalas`); None numa medida de antes da 0.100.55."""
    from ipe.ai import calc_vascular_escalas as E
    try:
        return E.calcular(imagens_guardadas(m))
    except Exception:
        log.warning("calcificação vascular: escalas", exc_info=True)
        return None


def imagens_guardadas(m: dict) -> list[dict]:
    """As imagens medidas, também numa medida da 0.100.51 (só as quatro, em "vistas")."""
    if m.get("imagens"):
        return list(m["imagens"])
    out = []
    for k in ORDEM:
        v = (m.get("vistas") or {}).get(k)
        if v:
            out.append(dict(v, chave=k, lado=k[0], incidencia=k[2:], extra=False, modificadores=[], sop="", serie=""))
    return out


def arquivo_da_imagem(repo, study_uid: str, img: dict) -> str | None:
    """O arquivo desta imagem neste computador (o caminho não vai guardado: no servidor e no cliente é outro)."""
    lista = imagens_do_exame(repo, study_uid)
    if img.get("sop"):
        x = next((x for x in lista if x["sop"] == img["sop"]), None)
        return x["caminho"] if x else None
    from ipe.imaging import (
        densidade_revisao as R,  # medida da 0.100.51: a última da incidência
    )
    arquivos = [f for f in repo.files_for_study(study_uid) if f]
    return R.escolher_vistas([R.cabecalho(f) for f in arquivos])[0].get(img.get("chave", ""))


def arquivos_das_vistas(repo, study_uid: str) -> dict:
    """{"R-CC": caminho, ...}: as quatro de rotina (a última de cada), como a densidade escolhe."""
    from ipe.imaging import densidade_revisao as R
    arquivos = [f for f in repo.files_for_study(study_uid) if f]
    return R.escolher_vistas([R.cabecalho(f) for f in arquivos])[0]


# ------------------------------------------------------------------ guardar e confirmar
def guardada(repo, study_uid: str) -> dict | None:
    import json
    try:
        r = repo.revisao_ia(study_uid, MODULO)
    except Exception:
        log.debug("calcificação vascular guardada", exc_info=True)
        return None
    if not r or not r.get("dados"):
        return None
    try:
        d = json.loads(r["dados"])
    except ValueError:
        return None
    d["estado"] = r.get("estado") or "auto"
    if r.get("usuario"):
        d["revisor"] = r["usuario"]
    q = r.get("quando")
    if q is not None and not isinstance(q, str):
        q = q.strftime("%Y-%m-%d %H:%M")
    d["confirmado_em"] = q if d["estado"] != "auto" else ""
    return d


def guardar_medida(repo, study_uid: str, medida: dict) -> None:
    """Guarda a medida nova; a confirmação que já existia continua valendo."""
    import json
    antes = guardada(repo, study_uid) or {}
    d = {k: v for k, v in medida.items() if k not in ("estado", "revisor", "confirmado_em")}
    estado, usuario = "auto", ""
    if antes.get("grau"):
        d["grau"] = antes["grau"]
        estado, usuario = antes.get("estado") or "aceito", antes.get("revisor", "")
    repo.salvar_revisao_ia(study_uid, MODULO, estado, estado == "editado", usuario,
                           json.dumps(d, ensure_ascii=False, default=str))


def confirmar(repo, study_uid: str, medida: dict, grau: str, usuario: str = "") -> None:
    import json
    if grau not in GRAUS:
        raise ValueError("grau inválido (ausente, leve, moderada ou acentuada)")
    d = {k: v for k, v in (medida or {}).items() if k not in ("estado", "revisor", "confirmado_em")}
    d["grau"] = grau
    estado = "aceito" if grau == (d.get("sugestao") or "") else "editado"
    repo.salvar_revisao_ia(study_uid, MODULO, estado, estado == "editado", usuario,
                           json.dumps(d, ensure_ascii=False, default=str))


def frase_do_laudo(grau: str) -> str:
    return {"ausente": "Não há calcificações vasculares.",
            "leve": "Calcificações vasculares leves.",
            "moderada": "Calcificações vasculares moderadas.",
            "acentuada": "Calcificações vasculares acentuadas."}.get(grau, "")


# ------------------------------------------------------------------ prévia
def previa(ds, vista: dict, largura: int = 360) -> np.ndarray:
    """RGB (uint8) da imagem reduzida com a calcificação marcada (contorno branco e setas numeradas, desde a 0.100.91)
    — para a janela, para o navegador e para as imagens que vão ao PACS."""
    img = oito_bits(ds)
    k = max(1, img.shape[1] // largura)
    peq = img[::k, ::k][: img.shape[0] // k, : img.shape[1] // k]
    rgb = np.repeat(peq[..., None], 3, axis=2).astype(np.uint8)
    if vista.get("mascara") and vista.get("forma"):
        m = descompactar(vista["mascara"], tuple(vista["forma"]))
        # a máscara está em 1/ESCALA; leva para o tamanho da prévia
        ys = np.minimum((np.arange(rgb.shape[0]) * k) // ESCALA, m.shape[0] - 1)
        xs = np.minimum((np.arange(rgb.shape[1]) * k) // ESCALA, m.shape[1] - 1)
        mm = m[ys][:, xs]
        passo = float(vista.get("passo_mm") or 0.1) * k
        try:
            return marcar(rgb, mm, passo)
        except Exception:  # noqa: BLE001 - sem OpenCV/PIL: o jeito antigo, pintado
            log.debug("marcas das calcificações vasculares", exc_info=True)
            rgb[mm] = (np.array([255, 40, 40]) * 0.75 + rgb[mm] * 0.25).astype(np.uint8)
    return rgb


#: 0.100.91: marcas que aparecem também no monitor monocromático e no PACS de fora (o vermelho virava cinza escuro):
#: um contorno branco com borda preta, afastado ~1 mm do que a rede achou, e uma seta em cada ponta de cada vaso,
#: com o número dele (a mesma ordem da lista de vasos das escalas: do mais comprido ao mais curto)
AFASTAR_MM = 1.0


def vasos_da_mascara(mm: np.ndarray, passo: float) -> tuple[list[np.ndarray], np.ndarray]:
    """([pontos (y, x) de cada vaso, do mais comprido ao mais curto], máscara dos puntiformes) — os trechos a até
    `JUNTAR_MM` uns dos outros são um vaso, como nas escalas; grupo sem trecho alongado é puntiforme."""
    import cv2

    from ipe.ai import calc_vascular_escalas as E
    m8 = mm.astype(np.uint8)
    if not m8.any():
        return [], np.zeros_like(mm, bool)
    r = max(1, round(E.JUNTAR_MM / 2 / passo))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    n, grupo = cv2.connectedComponents(cv2.dilate(m8, ker), connectivity=8)
    vasos, punt = [], np.zeros_like(mm, bool)
    for g in range(1, n):
        dentro = (grupo == g) & mm
        ys, xs = np.nonzero(dentro)
        if not len(ys):
            continue
        pts = np.stack([ys, xs], axis=1).astype(float)
        _c, _u, comp, _l = E._eixo(pts)
        if comp * passo < E.ALONGADO_MM:
            punt |= dentro
            continue
        vasos.append((comp, pts))
    vasos.sort(key=lambda x: -x[0])
    return [p for _c, p in vasos], punt


def marcar(rgb: np.ndarray, mm: np.ndarray, passo: float) -> np.ndarray:
    """A imagem (RGB) com o contorno de alto contraste e as setas numeradas."""
    import cv2
    from PIL import Image, ImageDraw

    from ipe.ai import calc_vascular_escalas as E
    h, w = mm.shape
    esp = max(1, round(w / 450))                              # espessura da linha: ~1 px na prévia, 3 px no PACS
    r = max(1, round(AFASTAR_MM / passo))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    rf = max(1, round(E.TRILHO_MM[1] / 2 / passo))           # as duas paredes do trilho num tubo só
    fecha = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rf + 1, 2 * rf + 1))
    tubo = cv2.dilate(cv2.morphologyEx(mm.astype(np.uint8), cv2.MORPH_CLOSE, fecha), ker)
    cont, _h = cv2.findContours(tubo, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    tubo = cv2.drawContours(np.zeros_like(tubo), cont, -1, 1, thickness=cv2.FILLED)   # sem buracos por dentro
    k1 = np.ones((2 * esp + 1,) * 2, np.uint8)
    fora1 = cv2.dilate(tubo, k1).astype(bool)
    fora2 = cv2.dilate(fora1.astype(np.uint8), k1).astype(bool)
    dentro = tubo.astype(bool)
    borda = fora1 & ~dentro                                   # a linha branca, logo fora do tubo
    perto = cv2.dilate(mm.astype(np.uint8), k1).astype(bool)  # a borda preta nunca encosta na calcificação
    halo = (fora2 & ~fora1) | (dentro & ~cv2.erode(tubo, k1).astype(bool) & ~perto)
    out = rgb.copy()
    out[halo] = (0, 0, 0)
    out[borda] = (255, 255, 255)
    im = Image.fromarray(out)
    d = ImageDraw.Draw(im)
    vasos, _punt = vasos_da_mascara(mm, passo)
    seta = max(12, round(w / 22))                             # comprimento da seta
    from ipe.ai.mama_sr import _fonte
    fonte = _fonte(max(11, round(w / 30)))
    for numero, pts in enumerate(vasos[:30], 1):
        c, u, _comp, _l = E._eixo(pts)
        proj = (pts - c) @ u
        pontas = [pts[int(np.argmin(proj))], pts[int(np.argmax(proj))]]
        for i, (py, px) in enumerate(pontas):
            sinal = -1 if i == 0 else 1
            fora = np.array([u[0] * sinal, u[1] * sinal])        # para fora do vaso, pelo eixo dele
            cabeca = np.array([py, px]) + fora * (r + 3 * esp)
            cauda = cabeca + fora * seta
            lado = np.array([-fora[1], fora[0]])
            asa1 = cabeca + fora * seta * 0.4 + lado * seta * 0.25
            asa2 = cabeca + fora * seta * 0.4 - lado * seta * 0.25
            xy = lambda q: (float(q[1]), float(q[0]))          # noqa: E731
            d.line([xy(cauda), xy(cabeca)], fill=(0, 0, 0), width=esp * 3 + 2)
            d.line([xy(cauda), xy(cabeca)], fill=(255, 255, 255), width=esp * 2)
            d.polygon([xy(cabeca), xy(asa1), xy(asa2)], fill=(255, 255, 255), outline=(0, 0, 0))
            if i == 0:
                t = cauda + fora * seta * 0.35
                d.text(xy(t), str(numero), font=fonte, fill=(255, 255, 255), anchor="mm",
                       stroke_width=max(2, esp + 1), stroke_fill=(0, 0, 0))
    return np.asarray(im)


def previa_png(ds, vista: dict, largura: int = 360) -> bytes:
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(previa(ds, vista, largura)).save(b, "PNG", optimize=True)
    return b.getvalue()
