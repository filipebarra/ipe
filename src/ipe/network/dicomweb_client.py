"""Cliente DICOMweb (QIDO-RS, WADO-RS e STOW-RS) para nós remotos — Orthanc, dcm4chee e afins.

Por que existe, se já há DIMSE. O DIMSE precisa de porta aberta **neste** computador quando o
PACS usa C-MOVE, e de AE cadastrado do outro lado. O DICOMweb é HTTP: atravessa firewall e proxy,
não exige AE nem porta de volta, e a autenticação é usuário e senha. Num PACS que fica em outra
rede, costuma ser o único caminho que funciona sem pedir nada à TI.

O que este módulo **não** é: o DICOMweb do servidor central do programa (`central/dicomweb.py`)
fala com uma instalação nossa, com login próprio. Este aqui fala o padrão, com um PACS de
terceiros.

As respostas são traduzidas para os **mesmos dicionários** que o cliente DIMSE devolve, para que
a busca, a fila de download, a pré-busca de anteriores e a chamada externa funcionem sem saber
qual protocolo está embaixo.
"""

from __future__ import annotations

import base64
import json
import logging
import ssl
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ipe.central import dicomweb as DW
from ipe.network.client import DicomError, display_pn

log = logging.getLogger(__name__)

# Etiquetas DICOM no JSON do QIDO-RS (o padrão usa o número da tag como chave).
T_PACIENTE = "00100010"
T_ID = "00100020"
T_NASCIMENTO = "00100030"
T_SEXO = "00100040"
T_DATA = "00080020"
T_HORA = "00080030"
T_ACCESSION = "00080050"
T_DESCRICAO = "00081030"
T_MODALIDADES = "00080061"
T_ESTUDO = "0020000D"
T_SERIES_N = "00201206"
T_IMAGENS_N = "00201208"
T_SERIE = "0020000E"
T_MODALIDADE = "00080060"
T_NUM_SERIE = "00200011"
T_DESC_SERIE = "0008103E"
T_REGIAO = "00180015"
T_IMG_SERIE = "00201209"


@dataclass
class WebTarget:
    """Para onde e como, no DICOMweb."""
    name: str
    base_url: str
    user: str = ""
    password: str = ""
    verify_tls: bool = True
    timeout: int = 30

    @staticmethod
    def build(node: dict, timeout: int = 30) -> "WebTarget":
        url = str(node.get("base_url") or "").strip().rstrip("/")
        if not url:
            raise DicomError("Endereço DICOMweb vazio no nó " + str(node.get("name", "")))
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        return WebTarget(node.get("name", ""), url, node.get("username", "") or "",
                         node.get("password", "") or "",
                         bool(node.get("verify_tls", True)), timeout)


def _texto(item: dict, tag: str) -> str:
    """Valor de uma etiqueta no JSON do QIDO. Nome de pessoa vem dentro de {"Alphabetic": …}."""
    campo = item.get(tag) or {}
    valores = campo.get("Value") or []
    if not valores:
        return ""
    v = valores[0]
    if isinstance(v, dict):
        v = v.get("Alphabetic", "") or ""
    return str(v)


def _lista(item: dict, tag: str) -> str:
    campo = item.get(tag) or {}
    return "\\".join(str(v) for v in (campo.get("Value") or []) if v)


def _inteiro(item: dict, tag: str) -> int:
    try:
        return int(float(_texto(item, tag) or 0))
    except (TypeError, ValueError):
        return 0


class DicomWebClient:
    """Mesma interface do cliente DIMSE, nos métodos que o programa usa."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    # ------------------------------------------------------------ HTTP
    def _abrir(self, t: WebTarget, caminho: str, aceita: str, timeout: int | None = None,
               corpo: bytes | None = None, tipo: str = ""):
        url = t.base_url + caminho
        req = urllib.request.Request(url, data=corpo, method="POST" if corpo is not None else "GET")
        req.add_header("Accept", aceita)
        if tipo:
            req.add_header("Content-Type", tipo)
        if t.user:
            cred = base64.b64encode(f"{t.user}:{t.password}".encode("utf-8")).decode("ascii")
            req.add_header("Authorization", "Basic " + cred)
        ctx = None
        if url.startswith("https://") and not t.verify_tls:
            # Certificado autoassinado é o caso comum num PACS de intranet. Isso só acontece
            # quando o usuário marcou a caixa: silenciar verificação de TLS por conta própria
            # seria esconder dele que a conexão não está sendo conferida.
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        try:
            return urllib.request.urlopen(req, timeout=timeout or t.timeout, context=ctx)
        except urllib.error.HTTPError as e:
            detalhe = {401: "usuário ou senha recusados", 403: "acesso negado",
                       404: "endereço não encontrado (confira a base /dicom-web/)",
                       405: "o servidor não aceita esse pedido"}.get(e.code, e.reason)
            raise DicomError(f"Nó {t.name}: HTTP {e.code} — {detalhe}") from e
        except urllib.error.URLError as e:
            motivo = getattr(e, "reason", e)
            if isinstance(motivo, ssl.SSLError):
                raise DicomError(f"Nó {t.name}: o certificado não foi aceito. Se o PACS usa "
                                 f"certificado próprio, marque “aceitar certificado não "
                                 f"verificado” no nó. ({motivo})") from e
            raise DicomError(f"Nó {t.name}: não consegui falar com o servidor ({motivo})") from e

    def _qido(self, t: WebTarget, caminho: str, params: dict) -> list[dict]:
        limpos = {k: v for k, v in params.items() if v not in ("", None)}
        q = urllib.parse.urlencode(limpos)
        with self._abrir(t, caminho + (f"?{q}" if q else ""), "application/dicom+json") as r:
            bruto = r.read()
        if not bruto.strip():
            return []                      # 204: nada encontrado, e isso não é erro
        try:
            dados = json.loads(bruto)
        except ValueError as e:
            raise DicomError(f"Nó {t.name}: resposta que não é JSON do DICOMweb") from e
        return dados if isinstance(dados, list) else [dados]

    # ------------------------------------------------------------ eco
    def echo(self, t: WebTarget) -> tuple[bool, str]:
        """Não existe C-ECHO no DICOMweb: o equivalente é pedir uma busca mínima e ver se responde."""
        self._qido(t, "/studies", {"limit": "1"})
        return True, f"Nó {t.name}: DICOMweb respondeu em {t.base_url}"

    # ------------------------------------------------------------ busca
    def find_studies(self, t: WebTarget, *, name: str = "", patient_id: str = "",
                     accession: str = "", date_from: str = "", date_to: str = "",
                     modality: str = "", description: str = "", study_uid: str = "",
                     limit: int = 500, cancel: threading.Event | None = None) -> list[dict]:
        nome = name.strip()
        if nome and "*" not in nome and "?" not in nome:
            nome = nome.replace(", ", "^") + "*"
        data = ""
        if date_from or date_to:
            data = f"{date_from}-{date_to}" if date_from != date_to else date_from
        params = {
            "PatientName": nome, "PatientID": patient_id.strip(),
            "AccessionNumber": accession.strip(), "StudyDate": data,
            "ModalitiesInStudy": modality.strip(), "StudyDescription": description.strip(),
            "StudyInstanceUID": study_uid.strip(),
            "includefield": "00081030,00080061,00201206,00201208",
            "limit": str(limit),
        }
        out = []
        for item in self._qido(t, "/studies", params):
            if cancel is not None and cancel.is_set():
                break
            out.append({
                "study_uid": _texto(item, T_ESTUDO),
                "patient_name": display_pn(_texto(item, T_PACIENTE)),
                "patient_id": _texto(item, T_ID),
                "birth_date": _texto(item, T_NASCIMENTO),
                "sex": _texto(item, T_SEXO),
                "study_date": _texto(item, T_DATA),
                "study_time": _texto(item, T_HORA),
                "accession": _texto(item, T_ACCESSION),
                "description": _texto(item, T_DESCRICAO),
                "modalities": _lista(item, T_MODALIDADES),
                "num_series": _inteiro(item, T_SERIES_N),
                "num_images": _inteiro(item, T_IMAGENS_N),
            })
        return [r for r in out if r["study_uid"]]

    def find_series(self, t: WebTarget, study_uid: str) -> list[dict]:
        params = {"includefield": "0008103E,00200011,00201209,00180015"}
        out = [{"series_uid": _texto(i, T_SERIE),
                "modality": _texto(i, T_MODALIDADE),
                "series_number": _inteiro(i, T_NUM_SERIE),
                "description": _texto(i, T_DESC_SERIE),
                "body_part": _texto(i, T_REGIAO),
                "num_images": _inteiro(i, T_IMG_SERIE)}
               for i in self._qido(t, f"/studies/{study_uid}/series", params)]
        return sorted([s for s in out if s["series_uid"]], key=lambda s: s["series_number"] or 0)

    # ------------------------------------------------------------ download
    def get(self, t: WebTarget, study_uid: str, series_uids: list[str] | None, sink,
            progress=None, cancel: threading.Event | None = None) -> int:
        """WADO-RS. Entrega as imagens ao mesmo `sink` do C-GET: a indexação é a de sempre."""
        import pydicom
        alvos = series_uids or [None]
        recebidas = 0
        for n, serie in enumerate(alvos, 1):
            if cancel is not None and cancel.is_set():
                break
            caminho = f"/studies/{study_uid}" + (f"/series/{serie}" if serie else "")
            pasta = Path(tempfile.mkdtemp(prefix="dv_wado_"))
            try:
                r = self._abrir(t, caminho, 'multipart/related; type="application/dicom"',
                                timeout=max(t.timeout, 120))
                try:
                    limite = DW.boundary_of(r.headers.get("Content-Type", ""))
                    arquivos = DW.MultipartReader(r, limite, pasta).run()
                finally:
                    r.close()
                for arq in arquivos:
                    if cancel is not None and cancel.is_set():
                        break
                    try:
                        ds = pydicom.dcmread(str(arq), force=True)
                    except Exception:  # noqa: BLE001 - um arquivo ruim não derruba o download
                        log.warning("WADO-RS: arquivo que não abriu (%s)", arq.name)
                        continue
                    sink.store(ds, getattr(ds, "file_meta", None), origin="retrieved")
                    recebidas += 1
                    if progress is not None:
                        progress(recebidas, max(recebidas, len(arquivos) * len(alvos)),
                                 "recebidas " + f"{recebidas} imagem(ns)")
            except ValueError as e:
                raise DicomError(f"Nó {t.name}: resposta WADO-RS sem separador multipart ({e})") from e
            finally:
                for arq in pasta.glob("*"):
                    arq.unlink(missing_ok=True)
                pasta.rmdir()
        if not recebidas:
            raise DicomError(f"Nó {t.name}: o servidor não devolveu nenhuma imagem deste exame.")
        return recebidas

    def move(self, t: WebTarget, study_uid: str, series_uids, progress=None, cancel=None) -> int:
        raise DicomError("C-MOVE não existe no DICOMweb; o download é pelo WADO-RS.")

    # ------------------------------------------------------------ envio
    def store(self, t: WebTarget, paths: list[str], progress=None,
              cancel: threading.Event | None = None) -> tuple[int, int]:
        """STOW-RS. Devolve (enviados, falhas), como o C-STORE."""
        enviados, falhas = 0, 0
        lote: list[str] = []
        tamanho = 0
        limite = 64 << 20

        def despachar(arquivos: list[str]) -> None:
            nonlocal enviados, falhas
            if not arquivos:
                return
            limite_b = DW.new_boundary()
            corpo = b"".join(DW.multipart_iter(arquivos, limite_b))
            tipo = f'multipart/related; type="application/dicom"; boundary={limite_b}'
            try:
                with self._abrir(t, "/studies", "application/dicom+json",
                                 timeout=max(t.timeout, 300), corpo=corpo, tipo=tipo):
                    enviados += len(arquivos)
            except DicomError:
                falhas += len(arquivos)
                raise

        for p in paths:
            if cancel is not None and cancel.is_set():
                break
            lote.append(p)
            tamanho += Path(p).stat().st_size
            if tamanho >= limite:
                despachar(lote)
                lote, tamanho = [], 0
                if progress is not None:
                    progress(enviados, len(paths), f"enviadas {enviados}" + f" de {len(paths)}")
        despachar(lote)
        if progress is not None:
            progress(enviados, len(paths), f"enviadas {enviados}" + f" de {len(paths)}")
        return enviados, falhas
