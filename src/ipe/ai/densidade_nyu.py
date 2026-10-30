"""Rede da NYU para categoria de densidade mamária (BI-RADS a–d), em ONNX, na CPU.

Wu, Geras, Shen, Su, Kim, Kim, Wolfson, Moy, Cho. *Breast density classification with deep
convolutional neural networks*. ICASSP 2018. Código e pesos em github.com/nyukat/
breast_density_classifier, **licença BSD 2-Clause** — pesquisa e uso comercial permitidos, com a
atribuição. Os pesos foram convertidos para ONNX sem mudar nada: na imagem de exemplo do próprio
repositório, a saída bate com a do PyTorch até 3 × 10⁻⁸.

**Por que ela entra**: o limiar e o agrupamento nebuloso medem a mesma coisa do mesmo jeito — área
clara dentro da mama. A rede foi treinada para reproduzir **a categoria que o radiologista
escreve**, olhando as quatro incidências juntas. É opinião de outra natureza, e é isso que a torna
útil como conferência.

**O que ela não é**: não foi treinada no parque de aparelhos do IMEB. Descobrir se ela atravessa
para o Pristina faz parte do teste — não é pressuposto.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

ARQUIVO = "densidade_nyu.onnx"
VISTAS = ("L-CC", "R-CC", "L-MLO", "R-MLO")
ALTURA, LARGURA = 2600, 2000
FAIXAS = ("a", "b", "c", "d")
#: o que cada saída quer dizer, na ordem em que a rede devolve
ROTULOS = ("Quase toda gordurosa", "Áreas esparsas de tecido fibroglandular",
           "Heterogeneamente densa", "Extremamente densa")

_sessao = None
_de_onde = ""


def pastas(dados: Path | None = None) -> list:
    """Onde o modelo é procurado: a pasta de dados do usuário primeiro, depois a do programa."""
    saida = []
    if dados is None:                            # sem ninguém dizer, vale a pasta de dados do app
        try:
            from ipe.core.config import get_paths
            dados = get_paths().data
        except Exception:  # noqa: BLE001
            dados = None
    if dados is not None:
        saida.append(Path(dados) / "modelos")
    from ipe.core.runtime import resource_dir
    try:
        saida.append(Path(resource_dir()) / "modelos")
    except Exception:  # noqa: BLE001
        pass
    saida.append(Path(__file__).resolve().parents[3] / "modelos")
    return saida


def caminho(dados: Path | None = None) -> Path | None:
    for pasta in pastas(dados):
        alvo = pasta / ARQUIVO
        if alvo.is_file():
            return alvo
    return None


def disponivel(dados: Path | None = None) -> tuple[bool, str]:
    """(dá para rodar?, e se não dá, **por quê**, com o que fazer para resolver)."""
    try:
        import onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False, ("O pacote onnxruntime não está instalado: a rede não roda. "
                       "Instale com “pip install onnxruntime”.")
    alvo = caminho(dados)
    if alvo is None:
        procurei = " · ".join(str(p) for p in pastas(dados))
        return False, ("Não achei o arquivo do modelo. Ponha o “densidade_nyu.onnx” numa destas "
                       "pastas: {}").format(procurei)
    return True, ""


def sessao(dados: Path | None = None):
    """A sessão do onnxruntime, criada uma vez só (carregar 23 MB a cada exame seria desperdício)."""
    global _sessao, _de_onde
    alvo = caminho(dados)
    if alvo is None:
        return None
    if _sessao is not None and _de_onde == str(alvo):
        return _sessao
    import onnxruntime as ort
    opcoes = ort.SessionOptions()
    opcoes.log_severity_level = 3
    _sessao = ort.InferenceSession(str(alvo), opcoes, providers=["CPUExecutionProvider"])
    _de_onde = str(alvo)
    return _sessao


# ------------------------------------------------------------------ preparo
def _redimensiona(a: np.ndarray, altura: int, largura: int) -> np.ndarray:
    """Redimensiona por interpolação bilinear, só com numpy (não há scipy aqui)."""
    h, w = a.shape
    if (h, w) == (altura, largura):
        return a
    ys = np.linspace(0, h - 1, altura)
    xs = np.linspace(0, w - 1, largura)
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    fy = (ys - y0)[:, None]
    fx = (xs - x0)[None, :]
    cima = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    baixo = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return cima * (1 - fy) + baixo * fy


def preparar(arr: np.ndarray, parede_a_esquerda: bool) -> np.ndarray:
    """Deixa a imagem como a rede espera: parede torácica à esquerda, 2600 × 2000, normalizada.

    Nas quatro imagens de exemplo do repositório da NYU a mama **sempre** começa na coluna 0 — as
    da direita vêm espelhadas. Por isso o espelhamento aqui não é enfeite: sem ele, metade das
    imagens entra ao contrário do que a rede viu no treino.

    A normalização é a do próprio repositório: tira a média e divide pelo desvio padrão.
    """
    a = np.asarray(arr, dtype=np.float32)
    if not parede_a_esquerda:
        a = a[:, ::-1]
    a = _redimensiona(a, ALTURA, int(round(a.shape[1] * ALTURA / max(1, a.shape[0]))))
    if a.shape[1] >= LARGURA:
        a = a[:, :LARGURA]                       # sobra do lado do mamilo: corta
    else:
        a = np.pad(a, ((0, 0), (0, LARGURA - a.shape[1])), constant_values=float(a.min()))
    desvio = float(a.std())
    return ((a - float(a.mean())) / (desvio if desvio > 1e-6 else 1.0)).astype(np.float32)


def prever(imagens: dict, dados: Path | None = None) -> tuple[np.ndarray, str]:
    """Probabilidade de cada faixa a/b/c/d. `imagens`: {"L-CC": array já preparado, ...}.

    Devolve (probabilidades, aviso). Faltando incidência ou faltando o modelo, devolve vazio **e o
    motivo** — a rede pede as quatro juntas, é assim que ela foi treinada.
    """
    faltam = [v for v in VISTAS if v not in imagens]
    if faltam:
        return np.zeros(0), ("A rede precisa das quatro incidências juntas. Faltam na tela: "
                             "{}").format(", ".join(faltam))
    pode, motivo = disponivel(dados)
    if not pode:
        return np.zeros(0), motivo
    s = sessao(dados)
    if s is None:
        return np.zeros(0), "Não consegui abrir o modelo."
    try:
        entrada = {v: np.asarray(imagens[v], dtype=np.float32)[None, None] for v in VISTAS}
        saida = s.run(None, entrada)[0][0]
    except Exception as e:  # noqa: BLE001
        log.debug("rede de densidade: %s", e, exc_info=True)
        return np.zeros(0), "A rede falhou ao rodar; os outros métodos continuam valendo."
    return np.asarray(saida, dtype=float), ""


def faixa_de(probabilidades: np.ndarray) -> str:
    if probabilidades.size != 4:
        return ""
    return FAIXAS[int(np.argmax(probabilidades))]


def chave(lado: str, incidencia: str) -> str:
    """Nome da incidência como a rede espera ("L-CC"), ou vazio se não for uma das quatro."""
    l = (lado or "").upper()[:1]
    v = (incidencia or "").upper()
    v = "CC" if v == "CC" else ("MLO" if v in ("MLO", "SIO", "LMO") else "")
    return f"{l}-{v}" if l in ("L", "R") and v else ""


def do_dicom(ds) -> np.ndarray:
    """Prepara **uma** imagem DICOM para a rede, do jeito que o resto do programa a enxerga."""
    from ipe.imaging import density as D
    from ipe.imaging.mammo import chest_wall_side, display_values
    bruto = ds.pixel_array
    if getattr(bruto, "ndim", 0) != 2:
        raise ValueError("a rede só recebe imagem 2D")
    arr = display_values(D._na_janela(ds, bruto),
                         str(getattr(ds, "PhotometricInterpretation", "")) == "MONOCHROME1")
    return preparar(arr, chest_wall_side(arr) == "left")


def do_exame(caminhos: dict, dados=None) -> tuple[np.ndarray, str]:
    """Roda a rede a partir dos arquivos: {"L-CC": caminho, ...}. Devolve (probabilidades, aviso)."""
    import pydicom
    faltam = [v for v in VISTAS if v not in caminhos]
    if faltam:
        return np.zeros(0), ("A rede precisa das quatro incidências juntas. Faltam na tela: "
                             "{}").format(", ".join(faltam))
    pode, motivo = disponivel(dados)
    if not pode:
        return np.zeros(0), motivo
    imagens = {}
    for v in VISTAS:
        try:
            imagens[v] = do_dicom(pydicom.dcmread(str(caminhos[v]), force=True))
        except Exception as e:  # noqa: BLE001
            log.debug("rede de densidade, %s: %s", v, e, exc_info=True)
            return np.zeros(0), "Não consegui preparar uma das imagens para a rede."
    return prever(imagens, dados)
