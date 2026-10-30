"""Gestão de exames: o que as modalidades fizeram chegou ao PACS? Se não chegou, mandar.

Pedido dele: *"tenho uma clínica com 8 ressonâncias, 5 mamografias, PET-CTs e CTs. hoje eu confiro
diariamente manualmente se os exames dessas modalidades estão no meu PACS. verifico por exames e
por número de sequências. uso o OsiriX para poder fazer o envio de uma modalidade para o PACS.
quero (...) usar os nós já cadastrados, buscar em um ou mais nós específicos (às vezes se passando
por outro cliente), verificar se os exames estão presentes e se possível completos e se for preciso
enviar de uma modalidade para o PACS, tudo pelo nosso sistema"*.

Três peças, nesta ordem:

1. **Perguntar** (`Consulta`): uma associação aberta por nó para todas as perguntas da conferência.
   Modalidade não é PACS: abrir e fechar uma conexão por pergunta (2 a 3 por exame, dezenas de
   exames por dia) pesa no console e alguns limitam conexões simultâneas.
2. **Comparar** (`comparar_series`, `situacao_do_exame`): funções puras, sem rede, com as regras
   escritas uma vez só. Série a série, como ele faz à mão; imagem a imagem (SOP Instance UID)
   quando a contagem não vem ou quando ele pede a conferência exata.
3. **Mandar** (`Remetente`): o C-MOVE pedido **à modalidade** com destino **o PACS** — a modalidade
   manda direto, nada passa por este computador —, ou, quando a modalidade não conhece o PACS como
   destino, o caminho do OsiriX: baixar aqui e reenviar (C-STORE).

O que o padrão impõe e precisa ser dito: no C-MOVE quem decide se aceita o destino é **quem
envia** (a modalidade), pela tabela de destinos dela (AE → IP e porta). Este programa só escolhe o
nome do destino. Se a modalidade não tem o PACS cadastrado, a resposta é 0xA801 e o envio direto
não existe — por isso o modo "direto; se recusar, pelo computador" é o padrão.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from typing import Callable

from pydicom.dataset import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import (
    StudyRootQueryRetrieveInformationModelFind, StudyRootQueryRetrieveInformationModelMove,
)

from ipe.network.client import (
    DicomClient, DicomError, Target, linha_estudo, linha_serie, query_estudos, query_series,
)

log = logging.getLogger(__name__)

Progresso = Callable[[int, int, str], None]

# situação do exame, da pior para a melhor (a tabela ordena por aqui)
SITUACOES = {
    "erro": "Erro",
    "ausente": "Ausente no PACS",
    "outro_uid": "No PACS com outro UID",
    "incompleto": "Incompleto",
    "sem_contagem": "Sem contagem",
    "completo": "Completo",
}
ORDEM = {k: i for i, k in enumerate(SITUACOES)}
PROBLEMA = {"erro", "ausente", "outro_uid", "incompleto", "sem_contagem"}

SITUACOES_SERIE = {
    "falta": "Falta no PACS",
    "incompleta": "Incompleta",
    "sem_contagem": "Sem contagem",
    "ok": "Completa",
    "ignorada": "Ignorada",
    "so_no_pacs": "Só no PACS",
}
A_ENVIAR = ("falta", "incompleta")

MODOS_ENVIO = {
    "auto": "Direto; se a modalidade recusar, pelo computador",
    "direto": "Direto: a modalidade manda para o PACS (C-MOVE)",
    "computador": "Pelo computador: baixa aqui e reenvia ao PACS",
}


class DestinoDesconhecido(DicomError):
    """A modalidade não tem o destino do C-MOVE na tabela dela (status 0xA801)."""


# ---------------------------------------------------------------------- dados
@dataclass
class Fonte:
    """Um nó e a identidade com que se fala com ele (None = o AE deste programa)."""
    no: dict
    identidade: dict | None = None

    @property
    def nome(self) -> str:
        return str(self.no.get("name", ""))


@dataclass
class SerieComparada:
    uid: str
    numero: int
    descricao: str
    modalidade: str
    imagens_origem: int | None
    imagens_pacs: int | None
    situacao: str
    faltando: list[str] | None = None        # SOP Instance UIDs que faltam, quando conhecidos

    @property
    def faltam(self) -> int | None:
        if self.faltando is not None:
            return len(self.faltando)
        if self.imagens_origem is None:
            return None
        if self.situacao == "falta":
            return self.imagens_origem
        if self.imagens_pacs is None:
            return None
        return max(0, self.imagens_origem - self.imagens_pacs)


@dataclass
class Conferencia:
    fonte: str                       # nome do nó de origem
    fonte_id: int | None
    estudo: dict                     # como `linha_estudo` devolve, visto na origem
    pacs: dict | None = None         # o mesmo exame visto no PACS
    series: list[SerieComparada] = field(default_factory=list)
    situacao: str = "erro"
    detalhe: str = ""
    envio: str = ""                  # o que aconteceu no último envio deste exame

    @property
    def study_uid(self) -> str:
        return self.estudo.get("study_uid", "")

    @property
    def problema(self) -> bool:
        return self.situacao in PROBLEMA

    def a_enviar(self) -> list[SerieComparada]:
        return [s for s in self.series if s.situacao in A_ENVIAR]

    def contagem(self) -> tuple[str, str]:
        """("séries origem / PACS", "imagens origem / PACS"), só com as séries que contam."""
        conta = [s for s in self.series if s.situacao not in ("ignorada", "so_no_pacs")]
        if not conta:
            o, p = self.estudo, self.pacs or {}
            ser = f"{o.get('num_series') or '?'} / {p.get('num_series') or '—' if self.pacs else '—'}"
            img = f"{o.get('num_images') or '?'} / {p.get('num_images') or '—' if self.pacs else '—'}"
            return ser, img
        no_pacs = [s for s in conta if s.situacao != "falta"]
        io = [s.imagens_origem for s in conta]
        ip = [s.imagens_pacs for s in no_pacs]
        img_o = str(sum(io)) if all(v is not None for v in io) else "?"
        img_p = str(sum(ip)) if all(v is not None for v in ip) else "?"
        return f"{len(conta)} / {len(no_pacs)}", f"{img_o} / {img_p}"

    def texto(self) -> str:
        return SITUACOES.get(self.situacao, self.situacao)


# ---------------------------------------------------------------------- comparar (sem rede)
def ignorada(descricao: str, ignorar) -> bool:
    d = (descricao or "").casefold()
    return any(p and p.casefold() in d for p in (x.strip() for x in ignorar or ()))


def comparar_series(origem: list[dict], pacs: list[dict], ignorar=()) -> list[SerieComparada]:
    """Série a série. Cada dicionário é `linha_serie`, com `sops` (conjunto) quando se conhece.

    `num_images` 0 quer dizer "o nó não informou" — série DICOM sem imagem não existe. O PACS ter
    imagens **a mais** numa série não é defeito (objetos derivados, reenvio): completa é o PACS ter
    pelo menos o que a modalidade tem.
    """
    no_pacs = {s["series_uid"]: s for s in pacs}
    out: list[SerieComparada] = []
    for s in origem:
        uid = s["series_uid"]
        so = s.get("sops")
        n_o = len(so) if so is not None else (s.get("num_images") or None)
        base = dict(uid=uid, numero=int(s.get("series_number") or 0),
                    descricao=str(s.get("description", "")), modalidade=str(s.get("modality", "")))
        p = no_pacs.get(uid)
        if ignorada(base["descricao"], ignorar):
            n_p = None if p is None else (len(p["sops"]) if p.get("sops") is not None
                                          else (p.get("num_images") or None))
            out.append(SerieComparada(**base, imagens_origem=n_o, imagens_pacs=n_p, situacao="ignorada"))
            continue
        if p is None:
            out.append(SerieComparada(**base, imagens_origem=n_o, imagens_pacs=0, situacao="falta",
                                      faltando=sorted(so) if so is not None else None))
            continue
        sp = p.get("sops")
        if so is not None and sp is not None:
            falta = sorted(so - sp)
            out.append(SerieComparada(**base, imagens_origem=len(so), imagens_pacs=len(sp),
                                      situacao="incompleta" if falta else "ok", faltando=falta))
            continue
        n_p = len(sp) if sp is not None else (p.get("num_images") or None)
        if n_o and n_p:
            out.append(SerieComparada(**base, imagens_origem=n_o, imagens_pacs=n_p,
                                      situacao="ok" if n_p >= n_o else "incompleta"))
        else:
            out.append(SerieComparada(**base, imagens_origem=n_o, imagens_pacs=n_p,
                                      situacao="sem_contagem"))
    vistas = {s["series_uid"] for s in origem}
    for p in pacs:
        if p["series_uid"] not in vistas:
            n_p = len(p["sops"]) if p.get("sops") is not None else (p.get("num_images") or None)
            out.append(SerieComparada(uid=p["series_uid"], numero=int(p.get("series_number") or 0),
                                      descricao=str(p.get("description", "")),
                                      modalidade=str(p.get("modality", "")), imagens_origem=None,
                                      imagens_pacs=n_p, situacao="so_no_pacs"))
    return out


def situacao_do_exame(estudo: dict, pacs: dict | None, series: list[SerieComparada]) -> tuple[str, str]:
    """(situação, detalhe) do exame inteiro."""
    if pacs is None:
        return "ausente", ""
    conta = [s for s in series if s.situacao not in ("ignorada", "so_no_pacs")]
    if not conta:
        # a origem não listou séries (ou todas foram ignoradas): resta o total do exame
        if not series:
            no, np_ = estudo.get("num_images") or 0, pacs.get("num_images") or 0
            so, sp = estudo.get("num_series") or 0, pacs.get("num_series") or 0
            if no and np_:
                if np_ >= no and sp >= so:
                    return "completo", "conferido pelo total do exame (a origem não listou as séries)"
                return "incompleto", "conferido pelo total do exame (a origem não listou as séries)"
            return "sem_contagem", "a origem não listou as séries nem informou o total de imagens"
        return "completo", "todas as séries foram ignoradas pela regra"
    if any(s.situacao in A_ENVIAR for s in conta):
        faltam = [s for s in conta if s.situacao == "falta"]
        incomp = [s for s in conta if s.situacao == "incompleta"]
        partes = []
        if faltam:
            partes.append(f"{len(faltam)} série(s) faltando")
        if incomp:
            n = sum(s.faltam or 0 for s in incomp)
            partes.append(f"{len(incomp)} série(s) incompleta(s), {n} imagem(ns) a menos" if n
                          else f"{len(incomp)} série(s) incompleta(s)")
        return "incompleto", "; ".join(partes)
    if any(s.situacao == "sem_contagem" for s in conta):
        n = sum(1 for s in conta if s.situacao == "sem_contagem")
        return "sem_contagem", f"todas as séries estão no PACS; {n} sem contagem de imagens"
    return "completo", ""


# ---------------------------------------------------------------------- perguntar
class Consulta:
    """Uma associação aberta para várias buscas no mesmo nó (C-FIND, Study Root)."""

    def __init__(self, cliente: DicomClient, alvo: Target):
        self.cliente, self.alvo = cliente, alvo
        self.assoc = None
        self.nivel_imagem: bool | None = None       # o nó responde no nível IMAGE? (None: não tentou)

    def __enter__(self) -> "Consulta":
        self._abrir()
        return self

    def __exit__(self, *_exc) -> None:
        self.fechar()

    def _abrir(self) -> None:
        ae = self.cliente._ae(self.alvo.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        self.assoc = self.cliente._associate(ae, self.alvo)

    def fechar(self) -> None:
        if self.assoc is not None and self.assoc.is_established:
            self.assoc.release()
        self.assoc = None

    def find(self, q: Dataset, limite: int = 5000) -> list[Dataset]:
        for tentativa in (1, 2):
            if self.assoc is None or not self.assoc.is_established:
                self._abrir()
            try:
                return self._find(q, limite)
            except _Caiu:
                if tentativa == 2:
                    raise DicomError(f"{self.alvo.name} derrubou a conexão no meio da busca.")
                self.assoc = None
        return []

    def _find(self, q: Dataset, limite: int) -> list[Dataset]:
        out: list[Dataset] = []
        for status, ident in self.assoc.send_c_find(q, StudyRootQueryRetrieveInformationModelFind):
            if not status:
                if not self.assoc.is_established:
                    raise _Caiu()
                raise DicomError(f"{self.alvo.name} não respondeu à busca (tempo esgotado).")
            code = status.Status
            if code in (0xFF00, 0xFF01) and ident is not None:
                if len(out) < limite:
                    out.append(ident)
            elif code not in (0x0000, 0xFF00, 0xFF01):
                raise DicomError(explicar_busca(self.alvo, code))
        return out

    # -------------------------------------------------------------- perguntas da gestão
    def estudos(self, data_de: str, data_ate: str, modalidade: str = "") -> list[dict]:
        q = query_estudos(date_from=data_de, date_to=data_ate, modality=modalidade)
        return [r for r in (linha_estudo(d) for d in self.find(q)) if r["study_uid"]]

    def estudo(self, study_uid: str) -> dict | None:
        rows = [r for r in (linha_estudo(d) for d in self.find(query_estudos(study_uid=study_uid)))
                if r["study_uid"] == study_uid]
        return rows[0] if rows else None

    def por_accession(self, accession: str) -> list[dict]:
        if not accession.strip():
            return []
        return [r for r in (linha_estudo(d) for d in self.find(query_estudos(accession=accession)))
                if r["study_uid"]]

    def series(self, study_uid: str) -> list[dict]:
        out = [linha_serie(d) for d in self.find(query_series(study_uid))]
        return sorted([s for s in out if s["series_uid"]], key=lambda s: s["series_number"] or 0)

    def imagens(self, study_uid: str, series_uid: str) -> set[str] | None:
        """SOP Instance UIDs da série, ou None se o nó não responde no nível IMAGE."""
        if self.nivel_imagem is False:
            return None
        q = Dataset()
        q.QueryRetrieveLevel = "IMAGE"
        q.StudyInstanceUID = study_uid
        q.SeriesInstanceUID = series_uid
        q.SOPInstanceUID = ""
        q.InstanceNumber = ""
        try:
            sops = {str(d.get("SOPInstanceUID", "")) for d in self.find(q, limite=100000)}
        except DicomError as e:
            log.info("%s não respondeu no nível IMAGE: %s", self.alvo.name, e)
            self.nivel_imagem = False
            return None
        self.nivel_imagem = True
        sops.discard("")
        return sops


class _Caiu(Exception):
    pass


def explicar_busca(alvo: Target, code: int) -> str:
    """O status do C-FIND em português, com o que costuma causar cada um.

    Achado no PACS dele (DASIMEB, 09/10/2026): a conexão é aceita e toda busca volta 0xC001.
    "Devolveu erro (status 0xC001)" não diz a ninguém o que fazer; a causa mais comum é o PACS
    aceitar a conexão de qualquer AE mas só responder buscas de quem tem permissão de consulta.
    """
    base = f"{alvo.name} recusou a busca (status 0x{code:04X})"
    if 0xC000 <= code <= 0xCFFF:
        return (f"{base}: aceitou a conexão mas não processou a busca. Costuma ser o AE "
                f"{alvo.calling_ae} sem permissão de consulta nesse nó — escolha em \"Como\" a "
                f"identidade que tem essa permissão (a mesma que funciona no OsiriX).")
    if code == 0xA700:
        return f"{base}: sem recursos para responder agora; tente de novo em instantes."
    if code == 0xA900:
        return f"{base}: o nó não aceita esta pergunta (chaves ou nível de busca)."
    return f"{base}."


# ---------------------------------------------------------------------- conferir
AlvoDe = Callable[[dict, "dict | None"], Target]


class Conferidor:
    """Confere os exames de uma ou mais modalidades contra um PACS."""

    def __init__(self, cliente: DicomClient, alvo_de: AlvoDe):
        self.cliente, self.alvo_de = cliente, alvo_de

    def _consulta(self, f: Fonte) -> Consulta:
        return Consulta(self.cliente, self.alvo_de(f.no, f.identidade))

    def conferir(self, fontes: list[Fonte], pacs: Fonte, data_de: str, data_ate: str, *,
                 modalidade: str = "", ignorar=(), exato: bool = False,
                 cancel: threading.Event | None = None, progresso: Progresso | None = None,
                 ao_conferir: Callable[[Conferencia], None] | None = None,
                 ) -> tuple[list[Conferencia], list[str]]:
        """Devolve (conferências, erros por nó). Nó que falha não derruba os outros; o PACS sim."""
        resultados: list[Conferencia] = []
        erros: list[str] = []
        listas: list[tuple[Fonte, list[dict], Consulta | None]] = []
        for i, f in enumerate(fontes, 1):
            if cancel is not None and cancel.is_set():
                break
            if progresso:
                progresso(0, 0, f"Listando os exames de {f.nome} ({i} de {len(fontes)})…")
            c = None
            try:
                c = self._consulta(f).__enter__()
                listas.append((f, c.estudos(data_de, data_ate, modalidade), c))
            except Exception as e:  # noqa: BLE001
                if c is not None:
                    c.fechar()
                erros.append(f"{f.nome}: {e}")
        total = sum(len(rows) for _f, rows, _c in listas)
        feitos = 0
        try:
            with self._consulta(pacs) as cp:
                for f, rows, c in listas:
                    for estudo in rows:
                        if cancel is not None and cancel.is_set():
                            erros.append("Conferência interrompida.")
                            return resultados, erros
                        feitos += 1
                        if progresso:
                            progresso(feitos, total, f"{f.nome}: {estudo['patient_name']} "
                                                     f"({feitos} de {total})")
                        conf = self._um(f, c, cp, estudo, ignorar, exato)
                        resultados.append(conf)
                        if ao_conferir:
                            ao_conferir(conf)
                        repetido = _erro_repetido(resultados)
                        if repetido:
                            raise DicomError(repetido)
        finally:
            for _f, _rows, c in listas:
                if c is not None:
                    c.fechar()
        return resultados, erros

    def reconferir(self, fonte: Fonte, pacs: Fonte, study_uid: str, *, ignorar=(),
                   exato: bool = False) -> Conferencia:
        """Um exame só (depois de um envio)."""
        with self._consulta(fonte) as c, self._consulta(pacs) as cp:
            estudo = c.estudo(study_uid)
            if estudo is None:
                conf = Conferencia(fonte.nome, fonte.no.get("id"), {"study_uid": study_uid})
                conf.situacao, conf.detalhe = "erro", f"{fonte.nome} não encontrou mais o exame."
                return conf
            return self._um(fonte, c, cp, estudo, ignorar, exato)

    def _um(self, f: Fonte, c: Consulta, cp: Consulta, estudo: dict, ignorar, exato: bool
            ) -> Conferencia:
        conf = Conferencia(f.nome, f.no.get("id"), estudo)
        uid = estudo["study_uid"]
        try:
            pacs = cp.estudo(uid)
            if pacs is None:
                outros = [r for r in cp.por_accession(estudo.get("accession", ""))
                          if r["study_uid"] != uid]
                if outros:
                    conf.pacs = outros[0]
                    conf.situacao = "outro_uid"
                    conf.detalhe = (f"o PACS tem o accession {estudo.get('accession')} com outro "
                                    f"Study UID ({outros[0]['study_uid']}): exame refeito, fundido ou "
                                    f"corrigido no PACS")
                    return conf
                conf.series = comparar_series(self._series(c, uid, exato), [], ignorar)
                conf.situacao, conf.detalhe = "ausente", ""
                return conf
            conf.pacs = pacs
            so = self._series(c, uid, exato)
            sp = self._series(cp, uid, exato, so)
            conf.series = comparar_series(so, sp, ignorar)
            conf.situacao, conf.detalhe = situacao_do_exame(estudo, pacs, conf.series)
        except DicomError as e:
            conf.situacao, conf.detalhe = "erro", str(e)
        return conf

    @staticmethod
    def _series(c: Consulta, uid: str, exato: bool, referencia: list[dict] | None = None) -> list[dict]:
        """Séries do exame neste nó; com `sops` quando é preciso contar imagem por imagem.

        Conta imagem a imagem quando ele pede (exato), quando o nó não informa a contagem, ou —
        do lado do PACS — quando a origem foi contada assim (comparar conjunto com número não
        diz *quais* faltam)."""
        series = c.series(uid)
        precisa = set()
        if referencia is not None:
            precisa = {s["series_uid"] for s in referencia if s.get("sops") is not None}
        for s in series:
            if exato or not s.get("num_images") or s["series_uid"] in precisa:
                s["sops"] = c.imagens(uid, s["series_uid"])
                if s["sops"] is None:
                    s.pop("sops")
        return series

    # -------------------------------------------------------------- diagnóstico
    def diagnosticar(self, f: Fonte, destino_ae: str = "", data: str = "") -> list[tuple[bool | None, str]]:
        """O que este nó sabe fazer, pergunta a pergunta. (ok, texto); ok None = inconclusivo."""
        out: list[tuple[bool | None, str]] = []
        t = self.alvo_de(f.no, f.identidade)
        quem = f"como {t.calling_ae}"
        ok, msg = self.cliente.echo(t)
        out.append((ok, f"C-ECHO {quem}: {msg}"))
        if not ok:
            return out
        try:
            with Consulta(self.cliente, t) as c:
                rows = c.estudos(data, data)
                out.append((True, f"Busca por data ({data or 'qualquer'}): {len(rows)} exame(s)"))
                if rows:
                    com = sum(1 for r in rows if r["num_images"])
                    out.append((com == len(rows) or None,
                                f"Total de imagens por exame informado em {com} de {len(rows)}"))
                    se = c.series(rows[0]["study_uid"])
                    com_s = sum(1 for s in se if s["num_images"])
                    out.append((bool(se) or None, f"Séries do primeiro exame: {len(se)} "
                                f"(com contagem de imagens: {com_s})"))
                    if se:
                        sops = c.imagens(rows[0]["study_uid"], se[0]["series_uid"])
                        out.append((sops is not None or None,
                                    "Responde no nível imagem (conferência exata possível)"
                                    if sops is not None else
                                    "Não responde no nível imagem (só contagem)"))
        except DicomError as e:
            out.append((False, f"Busca: {e}"))
            return out
        if destino_ae:
            r = Remetente(self.cliente, self.alvo_de).testar_destino(f, destino_ae)
            out.append(r)
        return out


# ---------------------------------------------------------------------- mandar
def _pedido(study_uid: str, series_uid: str | None = None, sops: list[str] | None = None) -> Dataset:
    q = Dataset()
    q.QueryRetrieveLevel = "IMAGE" if sops else ("SERIES" if series_uid else "STUDY")
    q.StudyInstanceUID = study_uid
    if series_uid:
        q.SeriesInstanceUID = series_uid
    if sops:
        q.SOPInstanceUID = sops if len(sops) > 1 else sops[0]
    return q


class Remetente:
    """Manda o que falta para o PACS: direto da modalidade, ou passando por este computador."""

    def __init__(self, cliente: DicomClient, alvo_de: AlvoDe, sink=None, repo=None):
        self.cliente, self.alvo_de = cliente, alvo_de
        self.sink, self.repo = sink, repo

    # -------------------------------------------------------------- o que pedir
    @staticmethod
    def pedidos(conf: Conferencia, inteiro: bool = False) -> list[tuple[str | None, list[str] | None]]:
        """[(série, SOPs)]: série None = exame inteiro; SOPs None = a série inteira."""
        ignoradas = [s for s in conf.series if s.situacao == "ignorada"]
        if inteiro or (conf.situacao == "ausente" and not ignoradas):
            return [(None, None)]
        if conf.situacao == "ausente":
            return [(s.uid, None) for s in conf.series if s.situacao not in ("ignorada", "so_no_pacs")]
        out = []
        for s in conf.a_enviar():
            if s.situacao == "incompleta" and s.faltando:
                out.append((s.uid, list(s.faltando)))
            else:
                out.append((s.uid, None))
        return out

    def completar_faltantes(self, fonte: Fonte, pacs: Fonte | None, conf: Conferencia) -> int:
        """Descobre *quais* imagens faltam nas séries incompletas que só foram contadas.

        Sem isso, a série incompleta iria inteira — e PACS que recusa duplicata devolve falha em
        cada imagem que já tinha, o que faz um envio bem-sucedido parecer um envio com erro.
        Nó que não responde no nível imagem: a série vai inteira, como antes. Devolve quantas
        séries ficaram com a lista exata."""
        alvo = [s for s in conf.series if s.situacao == "incompleta" and s.faltando is None]
        if not alvo or pacs is None:
            return 0
        n = 0
        try:
            with Consulta(self.cliente, self.alvo_de(fonte.no, fonte.identidade)) as c, \
                    Consulta(self.cliente, self.alvo_de(pacs.no, pacs.identidade)) as cp:
                for s in alvo:
                    so = c.imagens(conf.study_uid, s.uid)
                    sp = cp.imagens(conf.study_uid, s.uid) if so is not None else None
                    if so is None or sp is None:
                        continue
                    s.faltando = sorted(so - sp)
                    n += 1
        except DicomError as e:
            log.info("Sem a lista de imagens que faltam (%s): a série vai inteira", e)
        return n

    # -------------------------------------------------------------- direto
    def direto(self, fonte: Fonte, conf: Conferencia, destino_ae: str, inteiro: bool = False,
               progresso: Progresso | None = None, cancel: threading.Event | None = None,
               pacs: Fonte | None = None) -> dict:
        """C-MOVE pedido à modalidade, com destino o PACS. Uma associação, um pedido por série."""
        t = replace(self.alvo_de(fonte.no, fonte.identidade), move_destination=destino_ae)
        if not inteiro:
            self.completar_faltantes(fonte, pacs, conf)
        pedidos = self.pedidos(conf, inteiro)
        if not pedidos:
            return {"modo": "direto", "imagens": 0, "falhas": 0, "avisos": 0,
                    "mensagem": "Nada a enviar."}
        ae = self.cliente._ae(t.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
        assoc = self.cliente._associate(ae, t)
        tot = {"imagens": 0, "falhas": 0, "avisos": 0}
        try:
            for i, (serie, sops) in enumerate(pedidos, 1):
                if progresso:
                    progresso(i - 1, len(pedidos), f"{t.name} → {destino_ae}: pedido {i} de "
                                                   f"{len(pedidos)}")
                r = self._um_move(assoc, t, _pedido(conf.study_uid, serie, sops), cancel)
                for k in tot:
                    tot[k] += r[k]
        finally:
            if assoc.is_established:
                assoc.release()
        if tot["falhas"] and not tot["imagens"]:
            raise DicomError(f"{t.name} não conseguiu enviar as {tot['falhas']} imagens para "
                             f"{destino_ae} (o PACS recusou ou não respondeu).")
        msg = f"{tot['imagens']} imagens enviadas direto de {t.name} para {destino_ae}"
        if tot["falhas"]:
            msg = f"{msg}; {tot['falhas']} falharam"
        return {"modo": "direto", **tot, "mensagem": msg}

    def mover(self, fonte: Fonte, destino_ae: str, study_uid: str, series_uids: list[str] | None = None,
              progresso: Progresso | None = None, cancel: threading.Event | None = None) -> dict:
        """C-MOVE do nó `fonte` direto para `destino_ae` — o exame não passa por este computador.

        É o "Baixar para" da tela do PACS (0.69.1): pedido dele, *"o exame vai do nó para o
        destino escolhido e não para o meu programa"*. Exame inteiro num pedido; séries
        escolhidas, um pedido por série, na mesma associação."""
        t = replace(self.alvo_de(fonte.no, fonte.identidade), move_destination=destino_ae)
        pedidos = [_pedido(study_uid, s) for s in series_uids] if series_uids else [_pedido(study_uid)]
        ae = self.cliente._ae(t.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
        assoc = self.cliente._associate(ae, t)
        tot = {"imagens": 0, "falhas": 0, "avisos": 0}
        try:
            for q in pedidos:
                base = tot["imagens"] + tot["falhas"] + tot["avisos"]

                def prog(feitas, total, msg, base=base):
                    if progresso:
                        progresso(base + feitas, base + total, msg)
                r = self._um_move(assoc, t, q, cancel, prog)
                for k in tot:
                    tot[k] += r[k]
        finally:
            if assoc.is_established:
                assoc.release()
        if tot["falhas"] and not tot["imagens"]:
            raise DicomError(f"{t.name} não conseguiu enviar as {tot['falhas']} imagens para "
                             f"{destino_ae} (o destino recusou ou não respondeu).")
        msg = f"{tot['imagens']} imagens enviadas de {t.name} para {destino_ae}"
        if tot["falhas"]:
            msg = f"{msg}; {tot['falhas']} falharam"
        return {**tot, "mensagem": msg}

    def _um_move(self, assoc, t: Target, q: Dataset, cancel, progresso: Progresso | None = None) -> dict:
        feitas = falhas = avisos = 0
        for status, _ident in assoc.send_c_move(q, t.move_destination,
                                                StudyRootQueryRetrieveInformationModelMove):
            if cancel is not None and cancel.is_set():
                assoc.abort()
                raise DicomError("Cancelado")
            if not status:
                raise DicomError(f"{t.name} parou de responder (tempo esgotado).")
            code = status.Status
            feitas = _n(status.get("NumberOfCompletedSuboperations"), feitas)
            falhas = _n(status.get("NumberOfFailedSuboperations"), falhas)
            avisos = _n(status.get("NumberOfWarningSuboperations"), avisos)
            resta = _n(status.get("NumberOfRemainingSuboperations"), 0)
            if progresso is not None and code in (0xFF00, 0xFF01):
                progresso(feitas + falhas + avisos, feitas + falhas + avisos + resta,
                          f"{feitas + falhas + avisos} de {feitas + falhas + avisos + resta} imagens")
            if code in (0xFF00, 0xFF01, 0x0000) or code & 0xF000 == 0xB000:
                continue
            if code == 0xA801:
                raise DestinoDesconhecido(
                    f"{t.name} não conhece o destino {t.move_destination}: ele precisa estar "
                    f"cadastrado em {t.name} (AE, IP e porta) para o envio direto.")
            if code == 0xFE00:
                raise DicomError("Cancelado")
            if code in (0xA701, 0xA702):
                raise DicomError(f"{t.name} sem recursos para enviar agora (status 0x{code:04X}).")
            raise DicomError(f"{t.name} devolveu erro no envio (status 0x{code:04X}).")
        return {"imagens": feitas, "falhas": falhas, "avisos": avisos}

    def testar_destino(self, fonte: Fonte, destino_ae: str) -> tuple[bool | None, str]:
        """C-MOVE de um exame que não existe, para ver se a modalidade conhece o destino.

        Não manda nada: o UID é inventado. Quem confere o destino antes de procurar o exame
        responde 0xA801 (não conhece) — isso é conclusivo. Quem procura o exame antes responde
        "zero imagens" sem olhar o destino — isso não prova que conhece."""
        from pydicom.uid import generate_uid
        t = replace(self.alvo_de(fonte.no, fonte.identidade), move_destination=destino_ae)
        try:
            ae = self.cliente._ae(t.calling_ae)
            ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
            assoc = self.cliente._associate(ae, t)
        except DicomError as e:
            return False, f"C-MOVE: {e}"
        try:
            self._um_move(assoc, t, _pedido(generate_uid()), None)
            return None, (f"C-MOVE para {destino_ae}: aceitou o pedido de teste (não prova que "
                          f"conhece o destino — o primeiro envio real é que confirma)")
        except DestinoDesconhecido:
            return False, (f"C-MOVE para {destino_ae}: a modalidade NÃO conhece este destino — "
                           f"envio direto impossível; use \"pelo computador\"")
        except DicomError as e:
            return None, f"C-MOVE para {destino_ae}: {e}"
        finally:
            if assoc.is_established:
                assoc.release()

    # -------------------------------------------------------------- pelo computador
    def pelo_computador(self, fonte: Fonte, pacs: Fonte, conf: Conferencia, inteiro: bool = False,
                        progresso: Progresso | None = None,
                        cancel: threading.Event | None = None) -> dict:
        """Baixa da modalidade para cá (C-GET, ou C-MOVE para este computador) e manda ao PACS."""
        if self.sink is None or self.repo is None:
            raise DicomError("Envio pelo computador indisponível (sem banco local).")
        t = self.alvo_de(fonte.no, fonte.identidade)
        tp = self.alvo_de(pacs.no, pacs.identidade)
        uid = conf.study_uid
        if not inteiro:
            self.completar_faltantes(fonte, pacs, conf)
        pedidos = self.pedidos(conf, inteiro)
        if not pedidos:
            return {"modo": "computador", "imagens": 0, "falhas": 0, "avisos": 0,
                    "mensagem": "Nada a enviar."}
        series = None if pedidos == [(None, None)] else [s for s, _ in pedidos]
        if progresso:
            progresso(0, 0, f"Baixando de {t.name}…")
        if t.retrieve == "move":
            self.sink.expected_studies.add(uid)
            recebidas = self.cliente.move(t, uid, series, progresso, cancel)
        else:
            recebidas = self.cliente.get(t, uid, series, self.sink, progresso, cancel)
        self.sink.flush(300)
        arquivos = self._arquivos(uid, pedidos)
        if not arquivos:
            raise DicomError(f"Nada chegou de {t.name} ({recebidas} imagens informadas).")
        if progresso:
            progresso(0, len(arquivos), f"Enviando ao {tp.name}…")
        enviadas, falhas = self.cliente.store(tp, arquivos, progresso, cancel)
        if falhas and not enviadas:
            raise DicomError(f"{tp.name} recusou as {falhas} imagens.")
        msg = f"{enviadas} imagens baixadas de {t.name} e reenviadas ao {tp.name} (como {tp.calling_ae})"
        if falhas:
            msg = f"{msg}; {falhas} falharam"
        return {"modo": "computador", "imagens": enviadas, "falhas": falhas, "avisos": 0,
                "mensagem": msg}

    def _arquivos(self, study_uid: str, pedidos) -> list[str]:
        if pedidos == [(None, None)]:
            return self.repo.files_for_study(study_uid)
        series = [s for s, _ in pedidos]
        sops = {u for _s, lista in pedidos if lista for u in lista}
        inteiras = {s for s, lista in pedidos if not lista}
        if not sops:
            return self.repo.files_for_study(study_uid, series)
        from sqlalchemy import select
        from ipe.db.models import Instance, Series, Study
        with self.repo.db.session() as s:
            q = (select(Instance.file_path, Instance.sop_uid, Series.series_uid)
                 .join(Series, Instance.series_fk == Series.id)
                 .join(Study, Series.study_fk == Study.id)
                 .where(Study.study_uid == study_uid, Series.series_uid.in_(series)))
            return [p for p, sop, se in s.execute(q) if se in inteiras or sop in sops]

    # -------------------------------------------------------------- os dois
    def enviar(self, modo: str, fonte: Fonte, pacs: Fonte, conf: Conferencia, destino_ae: str,
               inteiro: bool = False, progresso: Progresso | None = None,
               cancel: threading.Event | None = None) -> dict:
        if modo == "computador":
            return self.pelo_computador(fonte, pacs, conf, inteiro, progresso, cancel)
        try:
            return self.direto(fonte, conf, destino_ae, inteiro, progresso, cancel, pacs)
        except DestinoDesconhecido as e:
            if modo != "auto":
                raise
            r = self.pelo_computador(fonte, pacs, conf, inteiro, progresso, cancel)
            r["mensagem"] = f"{r['mensagem']} — o envio direto foi recusado ({e})"
            return r


REPETIDO = 3


def _erro_repetido(resultados: list[Conferencia]) -> str:
    """Os primeiros exames deram todos o mesmo erro: é do nó, não do exame — parar e dizer.

    Sem isto, um PACS que recusa a busca vira 39 linhas de "Erro" e nenhuma explicação à vista
    (foi o que ele viu na primeira conferência de verdade)."""
    if len(resultados) != REPETIDO:
        return ""
    detalhes = {r.detalhe for r in resultados}
    if all(r.situacao == "erro" for r in resultados) and len(detalhes) == 1:
        return f"O mesmo erro nos {REPETIDO} primeiros exames, então parei: {detalhes.pop()}"
    return ""


def _n(v, anterior: int) -> int:
    try:
        return int(v) if v not in (None, "") else anterior
    except (TypeError, ValueError):
        return anterior


def periodo(spec: str, hoje=None) -> tuple[str, str]:
    """"hoje", "ontem", "2dias" (ontem e hoje), "7dias" → (de, até) em AAAAMMDD."""
    from datetime import date, timedelta
    hoje = hoje or date.today()
    if spec == "ontem":
        d = hoje - timedelta(days=1)
        return d.strftime("%Y%m%d"), d.strftime("%Y%m%d")
    dias = {"hoje": 0, "2dias": 1, "7dias": 6}.get(spec, 0)
    return (hoje - timedelta(days=dias)).strftime("%Y%m%d"), hoje.strftime("%Y%m%d")
