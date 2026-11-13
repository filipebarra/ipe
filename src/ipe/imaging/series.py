"""Carga de séries: ordenação geométrica, leitura de pixels sob demanda e cache.

A série é tratada como uma lista de "quadros" (frames). Um arquivo comum tem
1 quadro; um multiframe (DBT, US cine, enhanced MR/CT) tem vários.
Os cortes são ordenados pela posição ao longo da normal do plano
(ImagePositionPatient · normal), não pelo InstanceNumber.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pydicom

log = logging.getLogger(__name__)


@dataclass
class Frame:
    path: str
    frame_index: int          # índice dentro do arquivo multiframe
    sop_uid: str
    instance_number: int
    position: np.ndarray | None = None      # (3,) mm
    orientation: np.ndarray | None = None   # (6,)
    acquisition_time: str = ""
    # quadros virtuais (MPR) trazem a função que gera a imagem
    provider: Callable[[int], "FrameImage"] | None = field(default=None, repr=False, compare=False)
    series_uid: str = ""
    #: 0.100.38: quantos quadros o arquivo tem, pelo banco (0 = não se sabe: o arquivo diz). Com isso a leitura
    #: não abre o cabeçalho de cada imagem só para saber se é multiframe.
    n_frames: int = field(default=0, compare=False)

    @property
    def is_virtual(self) -> bool:
        return self.provider is not None

    @property
    def normal(self) -> np.ndarray | None:
        if self.orientation is None:
            return None
        return np.cross(self.orientation[:3], self.orientation[3:])


@dataclass
class FrameImage:
    """Pixels já em unidades reais (HU etc.) + metadados de exibição."""
    pixels: np.ndarray                 # float32 2D, ou uint8 (H, W, 3) se colorido
    is_color: bool
    window: tuple[float, float] | None  # (largura, nível) sugerido pelo arquivo
    pixel_spacing: tuple[float, float] | None   # (linha, coluna) mm
    spacing_source: str = ""           # "PixelSpacing", "ImagerPixelSpacing" ou "RegiaoUS"
    photometric: str = ""
    header: dict = field(default_factory=dict)
    # regiões calibradas do ultrassom (imaging.us_regioes.Regiao); a escala muda por imagem
    us_regioes: tuple = ()
    # todas as janelas gravadas no arquivo, para o "Switch WL" (0.99.22): ((nome, largura, nível), …)
    janelas: tuple = ()


def quadro_na_posicao(frames: list, ponto, fracao: float = 0.5) -> int:
    """Em que corte da série entrar para continuar **no mesmo lugar do paciente**.

    Trocar de série ia para o meio: entre a T1 e a T2 do mesmo exame o médico perdia o nível e
    tinha de rolar de volta. Com a posição em milímetros isso não acontece nem quando uma série
    tem 40 cortes e a outra 120. Sem geometria comparável (`ponto` None, ou série sem posição),
    entra pela fração — o corte proporcional ao que estava à vista.
    """
    if not frames:
        return 0
    if ponto is not None:
        com_pos = [(i, f) for i, f in enumerate(frames) if f.position is not None]
        base = next((f for _i, f in com_pos if f.orientation is not None), None)
        if com_pos and base is not None:
            n = np.cross(base.orientation[:3], base.orientation[3:])
            norma = float(np.linalg.norm(n))
            if norma > 1e-6:
                n = n / norma
                p = np.asarray(ponto, float)
                return min(com_pos, key=lambda it: abs(float((np.asarray(it[1].position) - p) @ n)))[0]
    return int(round(min(max(fracao, 0.0), 1.0) * (len(frames) - 1)))


def _vec(text: str, n: int) -> np.ndarray | None:
    try:
        vals = [float(x) for x in text.split("\\")] if text else []
        return np.array(vals, dtype=float) if len(vals) == n else None
    except ValueError:
        return None


def build_frames(instances: list[dict], series_uid: str = "") -> list[Frame]:
    """Cria a lista de quadros da série e ordena geometricamente."""
    frames: list[Frame] = []
    for inst in instances:
        pos = _vec(inst.get("position", ""), 3)
        ori = _vec(inst.get("orientation", ""), 6)
        n = max(1, int(inst.get("frames") or 1))
        for k in range(n):
            frames.append(Frame(inst["path"], k, inst["sop_uid"],
                                int(inst.get("instance_number") or 0), pos, ori,
                                inst.get("acquisition_time", ""),
                                series_uid=series_uid or inst.get("series_uid", ""),
                                n_frames=n if inst.get("frames") else 0))
    return sort_frames(frames)


def sort_frames(frames: list[Frame]) -> list[Frame]:
    with_geo = [f for f in frames if f.position is not None and f.orientation is not None]
    if len(with_geo) == len(frames) and len(frames) > 1:
        normal = np.cross(frames[0].orientation[:3], frames[0].orientation[3:])
        # só ordena por geometria se todos os cortes forem paralelos
        parallel = all(np.allclose(np.cross(f.orientation[:3], f.orientation[3:]), normal, atol=1e-3)
                       for f in frames)
        if parallel:
            # empate de posição (ex.: RM dinâmica com fases no mesmo arquivo de série):
            # desempata por tempo de aquisição e número da instância
            return sorted(frames, key=lambda f: (float(np.dot(f.position, normal)),
                                                 f.acquisition_time, f.instance_number,
                                                 f.frame_index))
    return sorted(frames, key=lambda f: (f.instance_number, f.frame_index))


def _first(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (list, tuple, pydicom.multival.MultiValue)):
            return float(v[0])
        return float(v)
    except (TypeError, ValueError):
        return None


def _escala(ds) -> tuple[tuple[float, float] | None, str, tuple]:
    """Escala do quadro: (espaçamento, de onde veio, regiões do ultrassom).

    No ultrassom a régua é a região do próprio arquivo, não o PixelSpacing: é ela que o
    aparelho atualiza quando o médico muda a profundidade. Quando a região existe e está em
    centímetros, ela vence; sem região, fica o que houver (ou nada, e a medida sai em pixels).
    """
    from ipe.imaging import us_regioes as US
    sp, fonte = _spacing(ds)
    regs = tuple(US.regioes(ds))
    if regs and (str(ds.get("Modality", "")).upper() == "US" or sp is None):
        sp, fonte = US.espacamento(regs), "RegiaoUS"
    return sp, fonte, regs


def read_frame(frame: Frame) -> FrameImage:
    arr = None
    if frame.frame_index > 0 or frame.n_frames > 1 or (frame.n_frames == 0 and _is_multiframe(frame.path)):
        # multiframe (tomossíntese, cine…): decodifica só o quadro pedido, sem ler o arquivo todo
        try:
            from pydicom.pixels import pixel_array
            ds = pydicom.dcmread(frame.path, force=True, stop_before_pixels=True)
            plug = decodificador_preferido(_ts_de(ds))
            arr = pixel_array(frame.path, index=frame.frame_index, **({"decoding_plugin": plug} if plug else {}))
        except Exception:  # noqa: BLE001 - arquivo sem meta-informação etc.: caminho antigo
            arr = None
    if arr is None:
        ds = pydicom.dcmread(frame.path, force=True)
        _ensure_transfer_syntax(ds)
        arr = _htj2k_rapido(ds)
        if arr is None:
            arr = _jpegls_rapido(ds)
    if arr is None:
        plug = decodificador_preferido(_ts_de(ds))
        if plug:
            try:
                ds.pixel_array_options(decoding_plugin=plug)
            except Exception:  # noqa: BLE001
                pass
        try:
            arr = ds.pixel_array
        except Exception:  # noqa: BLE001
            if not plug:
                raise
            ds.pixel_array_options()             # o preferido não deu conta: os outros, na ordem do pydicom
            arr = ds.pixel_array
        if int(ds.get("NumberOfFrames", 1) or 1) > 1:
            arr = arr[frame.frame_index]
    photometric = str(ds.get("PhotometricInterpretation", "MONOCHROME2")).upper()
    n_frames = int(ds.get("NumberOfFrames", 1) or 1)
    spp = int(ds.get("SamplesPerPixel", 1) or 1)

    header = {k: str(ds.get(k, "")) for k in (
        "Modality", "SeriesDescription", "InstanceNumber", "SliceLocation",
        "SliceThickness", "KVP", "Exposure", "RepetitionTime", "EchoTime",
        "ImageLaterality", "ViewPosition", "LossyImageCompression", "LossyImageCompressionRatio",
        "LossyImageCompressionMethod", "ImageType", "FrameOfReferenceUID")}
    # para os selos de integridade (0.99.22): a sintaxe do arquivo e a Modality LUT em tabela,
    # que o programa não aplica (só slope/intercept)
    meta = getattr(ds, "file_meta", None)
    header["_ts"] = str(getattr(meta, "TransferSyntaxUID", "") or "") if meta is not None else ""
    if "ModalityLUTSequence" in ds:
        header["_modality_lut"] = "1"

    if spp == 3 or photometric.startswith(("RGB", "YBR")):
        if photometric.startswith("YBR"):
            from pydicom.pixels import convert_color_space
            arr = convert_color_space(arr, photometric, "RGB")
        sp, fonte, regs = _escala(ds)
        return FrameImage(np.ascontiguousarray(arr.astype(np.uint8)), True, None,
                          sp, fonte, photometric, header, regs)

    if photometric == "PALETTE COLOR":
        from pydicom.pixels import apply_color_lut
        rgb = apply_color_lut(arr, ds)
        if rgb.dtype != np.uint8:
            rgb = (rgb / 256).astype(np.uint8)
        sp, fonte, regs = _escala(ds)
        return FrameImage(np.ascontiguousarray(rgb), True, None, sp, fonte, photometric, header, regs)

    px = arr.astype(np.float32)
    slope = _first(ds.get("RescaleSlope")) or 1.0
    intercept = _first(ds.get("RescaleIntercept")) or 0.0
    # Enhanced multiframe guarda rescale por quadro
    if n_frames > 1 and "PerFrameFunctionalGroupsSequence" in ds:
        try:
            fg = ds.PerFrameFunctionalGroupsSequence[frame.frame_index]
            pvt = fg.PixelValueTransformationSequence[0]
            slope, intercept = float(pvt.RescaleSlope), float(pvt.RescaleIntercept)
        except (AttributeError, IndexError, KeyError):
            pass
    if slope != 1.0 or intercept != 0.0:
        px = px * slope + intercept

    window, func = voi_window(ds, frame.frame_index)
    if func:
        header["_voi_function"] = func
    if photometric == "MONOCHROME1":
        # MONOCHROME1: valor alto = preto. Invertido na exibição (ver windowing)
        header["_monochrome1"] = "1"
    sp, fonte, regs = _escala(ds)
    return FrameImage(px, False, window, sp, fonte, photometric, header, regs,
                      janelas_do_arquivo(ds, frame.frame_index))


def _lut_window(item) -> tuple[float, float] | None:
    """Janela equivalente a uma VOI LUT em tabela (faixa de entrada da tabela)."""
    try:
        seq = item.VOILUTSequence[0]
        desc = seq.LUTDescriptor
        n = int(desc[0]) or 65536
        first = float(desc[1])
        return float(n), first + n / 2.0
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None


def janelas_do_arquivo(ds, frame_index: int = 0) -> tuple[tuple[str, float, float], ...]:
    """Todas as janelas que o arquivo traz, com o nome (WindowCenterWidthExplanation ou
    LUTExplanation). A mamografia costuma trazer duas ou três ("NORMAL", "HARDER", "SOFTER"); a
    AW percorre todas com uma tecla (Switch WL)."""
    places = []
    for caminho in (lambda: ds.PerFrameFunctionalGroupsSequence[frame_index].FrameVOILUTSequence[0],
                    lambda: ds.SharedFunctionalGroupsSequence[0].FrameVOILUTSequence[0]):
        try:
            places.append(caminho())
        except (AttributeError, IndexError, KeyError, TypeError):
            pass
    places.append(ds)

    def lista(v):
        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple, pydicom.multival.MultiValue)):
            return list(v)
        return [v]
    out: list[tuple[str, float, float]] = []
    for item in places:
        ws, cs = lista(item.get("WindowWidth")), lista(item.get("WindowCenter"))
        nomes = [str(x) for x in lista(item.get("WindowCenterWidthExplanation"))]
        for i, (w, c) in enumerate(zip(ws, cs)):
            try:
                w, c = float(w), float(c)
            except (TypeError, ValueError):
                continue
            if w > 0 and not any(abs(w - a) < 1e-6 and abs(c - b) < 1e-6 for _n, a, b in out):
                out.append((nomes[i].strip() if i < len(nomes) and nomes[i].strip() else f"Janela {len(out) + 1}",
                            w, c))
        if out:
            break                   # a do quadro vence a compartilhada, que vence a do arquivo
    try:
        for i, seq in enumerate(ds.VOILUTSequence):
            n = int(seq.LUTDescriptor[0]) or 65536
            first = float(seq.LUTDescriptor[1])
            nome = str(seq.get("LUTExplanation", "") or "").strip() or f"Tabela {i + 1}"
            out.append((nome + " (VOI LUT)", float(n), first + n / 2.0))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        pass
    return tuple(out)


def voi_window(ds, frame_index: int = 0) -> tuple[tuple[float, float] | None, str]:
    """Janela sugerida pelo arquivo e a função VOI (LINEAR, SIGMOID…).

    Procura, nesta ordem: Frame VOI LUT do quadro (multiframe “enhanced”, ex.: tomossíntese), a Frame VOI LUT
    compartilhada e o módulo VOI LUT comum; se só houver tabela (VOI LUT Sequence), usa a faixa da tabela."""
    places = []
    try:
        places.append(ds.PerFrameFunctionalGroupsSequence[frame_index].FrameVOILUTSequence[0])
    except (AttributeError, IndexError, KeyError, TypeError):
        pass
    try:
        places.append(ds.SharedFunctionalGroupsSequence[0].FrameVOILUTSequence[0])
    except (AttributeError, IndexError, KeyError, TypeError):
        pass
    places.append(ds)
    func = ""
    for item in places:
        f = str(item.get("VOILUTFunction", "") or "").upper()
        func = func or f
        ww, wc = _first(item.get("WindowWidth")), _first(item.get("WindowCenter"))
        if ww and ww > 0 and wc is not None:
            return (ww, wc), (f or func)
    for item in places:
        w = _lut_window(item)
        if w is not None:
            return w, ""
    return None, func


_MULTI: dict[str, bool] = {}

# 0.99.86: o decodificador mais rápido por sintaxe. O pydicom tentava o gdcm primeiro; no JPEG-LS (a sintaxe
# da compressão sem perda do Ipê, e de toda a mamografia guardada) o pyjpegls (CharLS) é ~1,7× mais rápido
# numa mamografia 4096×3328 (340 ms contra 585 ms) e, ao contrário do gdcm, solta o GIL: os quatro quadros
# da mamografia decodificam em paralelo. Sem o pyjpegls instalado, fica o padrão.
# 0.100.29: o GDCM saiu (ver `ipe._sem_gdcm`). No JPEG 2000 o pydicom passaria a tentar o Pillow primeiro, que é
# 2× mais lento que o OpenJPEG do pylibjpeg (47 ms contra 24 ms num corte de TC): fica o pylibjpeg, e, se ele
# falhar, os outros na ordem do pydicom.
_PREFERIDOS = {"1.2.840.10008.1.2.4.80": "pyjpegls", "1.2.840.10008.1.2.4.81": "pyjpegls",
               "1.2.840.10008.1.2.4.90": "pylibjpeg", "1.2.840.10008.1.2.4.91": "pylibjpeg"}
_DISPONIVEL: dict[str, str | None] = {}


def _ts_de(ds) -> str:
    meta = getattr(ds, "file_meta", None)
    return str(getattr(meta, "TransferSyntaxUID", "") or "") if meta is not None else ""


#: 0.100.0: HTJ2K (a cópia que o servidor central manda ao cliente) — o OpenJPH do imagecodecs decodifica um corte
#: de TC em ~1 ms, contra ~3,5 ms do OpenJPEG pelo pydicom
HTJ2K = {"1.2.840.10008.1.2.4.201", "1.2.840.10008.1.2.4.202", "1.2.840.10008.1.2.4.203"}


def _htj2k_rapido(ds):
    """O quadro único em HTJ2K, monocromático, pelo imagecodecs; None para o caminho de sempre."""
    if _ts_de(ds) not in HTJ2K or int(ds.get("NumberOfFrames", 1) or 1) != 1 \
            or int(ds.get("SamplesPerPixel", 1) or 1) != 1 or "PixelData" not in ds:
        return None
    try:
        import imagecodecs
        from pydicom.encaps import generate_frames
        dados = next(generate_frames(ds.PixelData, number_of_frames=1))
        arr = np.asarray(imagecodecs.htj2k_decode(dados))
        if arr.shape != (int(ds.Rows), int(ds.Columns)):
            return None
        if int(ds.get("PixelRepresentation", 0) or 0) == 1 and arr.dtype.kind == "u":
            arr = arr.view(arr.dtype.str.replace("u", "i"))
        return arr
    except Exception:  # noqa: BLE001
        return None


JPEGLS = {"1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81"}


def _jpegls_rapido(ds):
    """0.100.38: o quadro único em JPEG-LS, monocromático, pelo imagecodecs (o mesmo CharLS, a mesma imagem) —
    ele **solta a trava do Python** enquanto decodifica: as linhas que adiantam a leitura da série trabalham de
    verdade em paralelo e não seguram a tela (o pyjpegls decodificava um quadro de cada vez, com a tela esperando).
    None para o caminho de sempre (cor, multiframe, com sinal em menos de 16 bits)."""
    if _ts_de(ds) not in JPEGLS or int(ds.get("NumberOfFrames", 1) or 1) != 1 \
            or int(ds.get("SamplesPerPixel", 1) or 1) != 1 or "PixelData" not in ds:
        return None
    try:
        aloc, guard = int(ds.BitsAllocated), int(ds.get("BitsStored", ds.BitsAllocated))
        sinal = int(ds.get("PixelRepresentation", 0) or 0) == 1
        if aloc not in (8, 16) or (sinal and guard != aloc):
            return None
        import imagecodecs
        from pydicom.encaps import generate_frames
        dados = next(generate_frames(ds.PixelData, number_of_frames=1))
        arr = np.asarray(imagecodecs.jpegls_decode(dados))
        if arr.shape != (int(ds.Rows), int(ds.Columns)) or arr.dtype.itemsize * 8 != aloc:
            return None
        if sinal:
            arr = arr.view(arr.dtype.str.replace("u", "i"))
        return arr
    except Exception:  # noqa: BLE001
        return None


def decodificador_preferido(ts: str) -> str | None:
    if ts not in _PREFERIDOS:
        return None
    if ts not in _DISPONIVEL:
        try:
            from pydicom.pixels import get_decoder
            plug = _PREFERIDOS[ts]
            _DISPONIVEL[ts] = plug if plug in get_decoder(ts).available_plugins else None
        except Exception:  # noqa: BLE001
            _DISPONIVEL[ts] = None
    return _DISPONIVEL[ts]


def preaquecer() -> None:
    """Carrega os decodificadores antes do primeiro exame (o primeiro import do CharLS, do libjpeg e do
    OpenJPEG custava ~0,3 s na primeira imagem). Roda numa linha à parte depois que a janela abre."""
    try:
        from pydicom.pixels import get_decoder
        from pydicom.uid import JPEG2000, JPEG2000Lossless, JPEGBaseline8Bit, JPEGLossless, JPEGLSLossless, RLELossless
        for ts in (JPEGLSLossless, JPEG2000Lossless, JPEG2000, JPEGBaseline8Bit, JPEGLossless, RLELossless):
            get_decoder(ts).available_plugins
            decodificador_preferido(str(ts))
        for mod in ("jpeg_ls", "openjpeg", "libjpeg", "imagecodecs"):
            try:
                __import__(mod)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        log.debug("preaquecer os decodificadores", exc_info=True)


def _is_multiframe(path: str) -> bool:
    v = _MULTI.get(path)
    if v is None:
        try:
            hdr = pydicom.dcmread(path, force=True, stop_before_pixels=True,
                                  specific_tags=["NumberOfFrames"])
            v = int(hdr.get("NumberOfFrames", 1) or 1) > 1
        except Exception:  # noqa: BLE001
            v = False
        if len(_MULTI) > 20000:
            _MULTI.clear()
        _MULTI[path] = v
    return v


def _ensure_transfer_syntax(ds) -> None:
    """Arquivos sem cabeçalho de meta-informação (CDs antigos) não dizem a sintaxe
    de transferência; deduz pela forma como o pydicom leu o arquivo."""
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ExplicitVRBigEndian, ExplicitVRLittleEndian, ImplicitVRLittleEndian
    meta = getattr(ds, "file_meta", None)
    if meta is not None and "TransferSyntaxUID" in meta:
        return
    if meta is None:
        ds.file_meta = meta = FileMetaDataset()
    implicit = getattr(ds, "original_encoding", (None, True))[0]
    little = getattr(ds, "original_encoding", (True, True))[1]
    if implicit is None:
        implicit = True
    meta.TransferSyntaxUID = (ImplicitVRLittleEndian if implicit
                              else ExplicitVRLittleEndian if little else ExplicitVRBigEndian)


def _spacing(ds) -> tuple[tuple[float, float] | None, str]:
    for kw in ("PixelSpacing", "ImagerPixelSpacing"):
        v = ds.get(kw)
        if v is not None and len(v) == 2:
            try:
                return (float(v[0]), float(v[1])), kw
            except (TypeError, ValueError):
                pass
    try:
        pm = ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing
        return (float(pm[0]), float(pm[1])), "PixelSpacing"
    except (AttributeError, IndexError, KeyError):
        return None, ""


class FrameCache:
    """Cache LRU de quadros decodificados, com limite de memória em MB."""

    def __init__(self, max_mb: int = 1024):
        self.max_bytes = max_mb * 1024 * 1024
        self._data: OrderedDict[tuple[str, int], FrameImage] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, frame: Frame) -> FrameImage:
        if frame.provider is not None:
            return frame.provider(frame.frame_index)
        key = (frame.path, frame.frame_index)
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
        img = read_frame(frame)
        self.put(key, img)
        return img

    def aquecer(self, frames: list[Frame], linhas: int = 0) -> None:
        """0.100.38: decodifica **em paralelo** os quadros que ainda não estão no cache e só volta quando todos
        estão (ou falharam — aí quem pedir depois vê o erro de sempre). Para o que vai aparecer junto na tela: as
        quatro incidências da mamografia, um quadro de cada série do protocolo. Os decodificadores do
        imagecodecs soltam a trava do Python, então isto usa os núcleos de verdade."""
        unicos = {(f.path, f.frame_index): f for f in frames if f is not None and f.provider is None}
        faltam = [f for f in unicos.values() if not self.contains(f)]
        if len(faltam) < 2:
            return
        import os
        from concurrent.futures import ThreadPoolExecutor
        n = linhas or min(len(faltam), max(2, (os.cpu_count() or 2)))

        def um(f: Frame) -> None:
            try:
                self.get(f)
            except Exception:  # noqa: BLE001
                log.debug("aquecer %s", f.path, exc_info=True)
        with ThreadPoolExecutor(max_workers=n, thread_name_prefix="ipe-aquecer") as ex:
            list(ex.map(um, faltam))

    def contains(self, frame: Frame) -> bool:
        if frame.provider is not None:
            return True
        with self._lock:
            return (frame.path, frame.frame_index) in self._data

    def put(self, key: tuple[str, int], img: FrameImage) -> None:
        with self._lock:
            if key in self._data:
                return
            self._data[key] = img
            self._bytes += img.pixels.nbytes
            while self._bytes > self.max_bytes and len(self._data) > 1:
                _, old = self._data.popitem(last=False)
                self._bytes -= old.pixels.nbytes

    def clear(self) -> None:
        """Esvazia o cache (usado ao trocar de local)."""
        with self._lock:
            self._data.clear()
            self._bytes = 0

    def set_limit(self, max_mb: int) -> None:
        """Muda o teto do cache; libera as imagens menos usadas se precisar."""
        with self._lock:
            self.max_bytes = max(64, int(max_mb)) * 1024 * 1024
            while self._bytes > self.max_bytes and len(self._data) > 1:
                _, old = self._data.popitem(last=False)
                self._bytes -= old.pixels.nbytes

    @property
    def used_mb(self) -> float:
        return self._bytes / 1024 / 1024
