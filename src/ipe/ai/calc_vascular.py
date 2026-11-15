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
VERSAO = 1
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


def medir_exame(repo, study_uid: str, dados=None, stop=None, cortes=CORTES) -> dict:
    """As quatro incidências 2D do exame (as mesmas que a densidade usa)."""
    import time

    import pydicom

    from ipe.imaging import densidade_revisao as R
    if hasattr(repo, "is_cached") and not repo.is_cached(study_uid):
        repo.download(study_uid)
    arquivos = [f for f in repo.files_for_study(study_uid) if f]
    vistas, aparelho, avisos = R.escolher_vistas([R.cabecalho(f) for f in arquivos])
    avisos = [a for a in avisos if "a rede pede as quatro" not in a] + (
        ["Faltam incidências: " + ", ".join(k for k in ("R-CC", "L-CC", "R-MLO", "L-MLO") if k not in vistas) + "."]
        if len(vistas) < 4 and vistas else [])
    out = {"versao": VERSAO, "modelo": "SCU-Net (Emory, MIT)", "limiar": LIMIAR, "cortes": list(cortes),
           "vistas": {}, "por_mama": {}, "area_mm2": None, "sugestao": None, "aviso": "", "avisos": avisos,
           "aparelho": aparelho, "quando": time.strftime("%Y-%m-%d %H:%M")}
    ok, motivo = disponivel(dados)
    if not ok:
        out["aviso"] = motivo
        return out
    if not vistas:
        out["aviso"] = "Nenhuma incidência de mamografia 2D com lado e incidência no exame."
        return out
    for chave, cam in sorted(vistas.items()):
        try:
            ds = pydicom.dcmread(cam, force=True)
            out["vistas"][chave] = medir_imagem(ds, dados, stop)
        except InterruptedError:
            raise
        except Exception as e:
            log.warning("calcificação vascular: %s falhou", chave, exc_info=True)
            out["avisos"].append(f"{chave}: {e}")
    protese = any(v.get("protese") for v in out["vistas"].values())
    if protese:
        out["avisos"].append("Prótese: a borda da prótese engana a rede; o que cai nela e em volta fica fora da conta, "
                             "mas confira nas imagens. Sem sugestão de grau.")
    for lado in ("R", "L"):
        areas = [v["area_mm2"] for k, v in out["vistas"].items() if k.startswith(lado + "-")]
        if areas:
            out["por_mama"][lado] = max(areas)
    if out["por_mama"]:
        out["area_mm2"] = max(out["por_mama"].values())
        out["sugestao"] = None if protese else grau_pela_area(out["area_mm2"], cortes)
    return out


def arquivos_das_vistas(repo, study_uid: str) -> dict:
    """{"R-CC": caminho, ...} neste computador (o caminho não vai guardado: no servidor e no cliente é outro)."""
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
    """RGB (uint8) da imagem reduzida com a calcificação em vermelho — para a janela e para o navegador."""
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
        rgb[mm] = (np.array([255, 40, 40]) * 0.75 + rgb[mm] * 0.25).astype(np.uint8)
    return rgb


def previa_png(ds, vista: dict, largura: int = 360) -> bytes:
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(previa(ds, vista, largura)).save(b, "PNG", optimize=True)
    return b.getvalue()
