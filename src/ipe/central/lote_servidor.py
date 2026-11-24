"""0.100.98: o lote a partir de planilha rodando **no servidor central**, pedido pelo Ipê cliente.

No cliente, as imagens não ficam no computador: quem busca, baixa, roda as IAs, envia e imprime é o servidor, com os
nós, as impressoras e a fila de IA dele. O cliente monta o lote na mesma janela (a planilha é lida no cliente e
mandada linha a linha), acompanha o andamento e baixa a planilha de saída — e, se quiser, os arquivos exportados (um
zip) e **os exames, para o banco deste computador** (o cache do cliente).

- Os nós são os que o servidor compartilha com os clientes (como na busca pelo servidor); as impressoras, as dele.
- O lote é de quem pediu: só ele (ou quem gerencia usuários) vê o andamento e baixa a saída. Cada lote tem um nome;
  mandar de novo com o mesmo nome **continua** de onde parou (o andamento fica na pasta do lote, no servidor).
- "Trazer para este computador": o exame que o lote baixou só é apagado do servidor (se pedido) depois que o cliente
  avisa que o copiou (`lote_copiado`).
- Permissões: as mesmas da janela no Ipê de mesa, conferidas aqui, com a sessão de quem pediu.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import re
import threading
import time
import zipfile
from collections import deque
from pathlib import Path

from ipe.automation import lote as L
from ipe.automation import lote_ias as LIA

log = logging.getLogger(__name__)

RPC = ("lote_opcoes", "lote_iniciar", "lote_estado", "lote_parar", "lote_lista", "lote_arquivo", "lote_copiado",
       "lote_ia_feita")
ESPERA_IA_CLIENTE_S = 3 * 60 * 60      # 0.100.100: o cliente que não roda a IA em 3 h deixa o exame com erro
_LOTES: dict[str, "Execucao"] = {}
_TRAVA = threading.Lock()


class Execucao:
    def __init__(self, ident: str, dono: str, nome: str, pasta: Path):
        self.id, self.dono, self.nome, self.pasta = ident, dono, nome, pasta
        self.lote: L.Lote | None = None
        self.parar = threading.Event()
        self.linha: threading.Thread | None = None
        self.diario: deque = deque(maxlen=2000)
        self.n_diario = 0                       # quantas linhas o diário já teve (para o cliente pedir só as novas)
        self.andamento: L.Andamento | None = None
        self.erro = ""
        self.inicio = time.time()
        self.fim = 0.0
        self.simular = False
        self.trazer = False
        self.para_copiar: list[str] = []        # exames prontos que o cliente pode copiar
        self.copiados: set[str] = set()
        self.apagar_quando_copiar: set[str] = set()
        self.ia_no_cliente = False               # 0.100.100: as IAs rodam no computador de quem pediu
        self.pedidos_ia: dict[str, dict] = {}    # study_uid → {"tipos", "refazer", "estado", "mensagem"}
        self.trava_ia = threading.Condition()

    @property
    def rodando(self) -> bool:
        return self.linha is not None and self.linha.is_alive()

    def anotar(self, texto: str) -> None:
        self.diario.append(texto)
        self.n_diario += 1

    def resumo(self) -> dict:
        a = self.andamento
        return {"id": self.id, "nome": self.nome, "dono": self.dono, "rodando": self.rodando, "erro": self.erro,
                "simular": self.simular, "inicio": self.inicio, "fim": self.fim,
                "total": a.total if a else 0, "feitos": a.feitos if a else 0,
                "contagem": dict(a.contagem) if a else {}, "esperando": a.esperando if a else "",
                "falta_s": a.falta_s() if a else None,
                "saida": bool(self.lote and self.lote.saida.exists()),
                "chave": bool(self.lote and self.lote.cfg.anonimizar and self.lote.arquivo_chave.exists()),
                "exportados": (self.pasta / "exportados").is_dir()}


def _exigir(s, perm: str) -> None:
    if perm not in (getattr(s, "perms", None) or set()):
        raise PermissionError(f"seu perfil não permite ({perm})")


def _pasta(c) -> Path:
    p = Path(c.storage).parent / "Lotes"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ident(dono: str, nome: str) -> str:
    return hashlib.sha1(f"{dono}\n{nome}".encode()).hexdigest()[:12]


def _meu(c, s, ident: str) -> Execucao:
    e = _LOTES.get(str(ident))
    if e is None:
        raise KeyError("lote não encontrado (o servidor pode ter sido reiniciado: mande de novo com o mesmo nome "
                       "para continuar)")
    if e.dono != s.username and "users" not in (getattr(s, "perms", None) or set()):
        raise PermissionError("o lote é de outro usuário")
    return e


def opcoes(c, s) -> dict:
    """O que o cliente pode escolher: os nós compartilhados, as IAs, as impressoras e os destinos do servidor."""
    from ipe.central import pacs_servidor as PS
    from ipe.printing import dispatch as D
    nos = [{"id": str(n["id"]), "name": n.get("name", "")} for n in PS.compartilhados(c, s)]
    imprimir = []
    st = c.settings
    if st is not None:
        for d in D.all_destinations(st):
            imprimir.append({"id": f"dest:{d.name}", "nome": f"Destino do servidor: {d.name}"})
        for x in st.get("printing.dicom_printers", []) or []:
            imprimir.append({"id": f"dicom:{x.get('name', '')}", "nome": f"Impressora DICOM: {x.get('name', '')}"})
    return {"nos": nos, "ias": [list(x) for x in LIA.catalogo(getattr(c, "auto", None))], "imprimir": imprimir,
            "modelos": {k: v.to_dict() for k, v in L.modelos(st).items()} if st is not None else {}}


def _permissoes(cfg: L.Config, simular: bool) -> list[str]:
    out = ["query"] if cfg.nos else []
    if simular:
        return out
    if cfg.nos:
        out.append("retrieve")
    if cfg.enviar_nos:
        out.append("send")
    if cfg.imprimir:
        out.append("print")
    if cfg.exportar_pasta:
        out.append("export")
        if not cfg.anonimizar:
            out.append("export_identified")
    return out


def iniciar(c, s, corpo: dict) -> dict:
    """Começa (ou continua) um lote. `corpo`: nome, cabecalho, dados (as linhas da planilha), config, simular,
    limite, exportar (bool: os arquivos ficam no servidor e o cliente baixa um zip), trazer (bool)."""
    from ipe.automation import lote_ipe as LP
    from ipe.central import pacs_servidor as PS
    nome = re.sub(r"\s+", " ", str(corpo.get("nome") or "").strip())[:80]
    if not nome:
        raise ValueError("dê um nome ao lote")
    cfg = L.Config.from_dict(corpo.get("config") or {})
    simular = bool(corpo.get("simular"))
    permitidos = {str(n["id"]) for n in PS.compartilhados(c, s)}
    fora = [n for n in list(cfg.nos) + list(cfg.enviar_nos) if str(n) not in permitidos]
    if fora:
        raise PermissionError("nó não compartilhado pelo servidor: " + ", ".join(map(str, fora)))
    ident = _ident(s.username, nome)
    pasta = _pasta(c) / ident
    pasta.mkdir(parents=True, exist_ok=True)
    cfg.exportar_pasta = str(pasta / "exportados") if corpo.get("exportar") else ""
    if cfg.exportar_pasta:
        Path(cfg.exportar_pasta).mkdir(parents=True, exist_ok=True)
    for p in _permissoes(cfg, simular):
        _exigir(s, p)
    with _TRAVA:
        e = _LOTES.get(ident)
        if e is not None and e.rodando:
            raise RuntimeError("esse lote já está rodando")
        e = Execucao(ident, s.username, nome, pasta)
        _LOTES[ident] = e
    e.simular, e.trazer = simular, bool(corpo.get("trazer"))
    cabecalho = list(corpo.get("cabecalho") or [])
    dados = [list(x) for x in corpo.get("dados") or []]
    linhas = L.montar_linhas(dados, cfg.colunas)
    serv = LP.servicos(c.repo, c.db, c.net, c.settings, c.storage, getattr(c, "auto", None),
                       chamar=lambda fn: c.ponte.chamar(fn, espera=900), parar=e.parar)
    e.ia_no_cliente = bool(corpo.get("ia_no_cliente")) and not simular and bool(cfg.ias)
    if e.ia_no_cliente:
        recolher = serv.ias                      # depois que o cliente roda e sobe, o servidor só recolhe

        def ias_pelo_cliente(uid, tipos, refazer, parar_=None):
            with e.trava_ia:
                e.pedidos_ia[uid] = {"tipos": list(tipos), "refazer": bool(refazer), "estado": "pedido",
                                     "mensagem": ""}
                fim = time.time() + ESPERA_IA_CLIENTE_S
                while e.pedidos_ia[uid]["estado"] == "pedido":
                    if (parar_ is not None and parar_.is_set()) or time.time() > fim:
                        break
                    e.trava_ia.wait(2.0)
                p = e.pedidos_ia.pop(uid)
            if p["estado"] != "feito":
                motivo = p["mensagem"] or ("lote parado" if parar_ is not None and parar_.is_set() else
                                           "o computador do cliente não rodou as IAs (a janela foi fechada?)")
                return {t: {"titulo": t, "situacao": LIA.ERRO, "motivo": motivo, "campos": {}, "series": []}
                        for t in tipos}
            return recolher(uid, tipos, False, parar_)
        serv.ias = ias_pelo_cliente
    if e.trazer:
        # 0.100.111: o cliente começa a trazer o exame assim que ele chega do PACS ao servidor, sem esperar as IAs,
        # os envios e a impressão da linha; no fim da linha traz de novo o que faltar (as séries das IAs)
        def baixado(uid: str) -> None:
            if uid not in e.para_copiar:
                e.para_copiar.append(uid)
        serv.baixado = baixado
    if e.trazer and cfg.apagar_depois:
        def so_depois_da_copia(uid: str) -> None:
            # só apaga depois da cópia feita **no fim da linha** (com os resultados das IAs): a cópia de antes não vale
            e.copiados.discard(uid)
            e.apagar_quando_copiar.add(uid)
        serv.apagar = so_depois_da_copia
    e.lote = L.Lote(cabecalho, dados, linhas, cfg, serv, pasta / "saida.xlsx", simular=simular,
                    limite=int(corpo.get("limite") or 0))
    c.repo.audit("lote", f"lote no servidor “{nome}”: {len(linhas)} linha(s); {', '.join(cfg.acoes())}"
                 + (" (simulação)" if simular else ""), user=s.username)

    def avisar(a, linha, r):
        e.andamento = a
        if linha is None:
            return
        partes = [r.get("situacao", "")]                 # o cliente traduz cada parte
        if r.get("observacao"):
            partes.append(r["observacao"])
        for x in r.get("exames") or []:
            ias = x.get("ias") or {}
            if ias:
                ok = sum(1 for y in ias.values() if y.get("situacao") in (LIA.FEITA, LIA.JA_FEITA))
                partes.append(["IAs: {} de {}", ok, len(ias)])
            if x.get("observacao"):
                partes.append(x["observacao"])
            if e.trazer and x.get("study_uid") and x.get("situacao") in (L.FEITO, L.FEITO_COM_FALHAS):
                e.copiados.discard(x["study_uid"])          # traz de novo o que mudou (IAs): o cliente só baixa o que falta
                if x["study_uid"] not in e.para_copiar:
                    e.para_copiar.append(x["study_uid"])
        e.anotar({"linha": linha.n + 2, "partes": [p for p in partes if p]})

    def rodar():
        try:
            e.andamento = e.lote.rodar(e.parar, avisar)
        except Exception as x:  # noqa: BLE001
            log.exception("lote no servidor")
            e.erro = str(x)
        finally:
            e.fim = time.time()
            e.anotar({"partes": ["Parado." if e.parar.is_set() else ("Terminado." if not e.erro else e.erro)]})
    e.anotar({"partes": ["Simulação" if simular else ["O que fazer: {}", ", ".join(cfg.acoes())]], "faixa": True})
    e.linha = threading.Thread(target=rodar, name=f"lote-{ident}", daemon=True)
    e.linha.start()
    return {"id": ident}


def estado(c, s, ident: str, desde: int = 0) -> dict:
    e = _meu(c, s, ident)
    d = e.resumo()
    primeiro = e.n_diario - len(e.diario)
    novas = list(e.diario)[max(0, int(desde) - primeiro):]
    d["diario"], d["n_diario"] = novas, e.n_diario
    d["para_copiar"] = [u for u in e.para_copiar if u not in e.copiados]
    d["pedidos_ia"] = [dict(p, study_uid=u) for u, p in list(e.pedidos_ia.items()) if p["estado"] == "pedido"]
    return d


def parar(c, s, ident: str) -> dict:
    e = _meu(c, s, ident)
    e.parar.set()
    return {"ok": True}


def lista(c, s) -> list[dict]:
    todos = "users" in (getattr(s, "perms", None) or set())
    return [e.resumo() for e in _LOTES.values() if todos or e.dono == s.username]


def arquivo(c, s, ident: str, qual: str) -> dict:
    """A planilha de saída, a chave (anonimizada) ou os exportados (zip), em base64."""
    e = _meu(c, s, ident)
    if e.lote is None:
        raise KeyError("lote sem saída")
    if qual == "saida":
        caminho, nome = e.lote.saida, f"{e.nome}.xlsx"
    elif qual == "chave":
        caminho, nome = e.lote.arquivo_chave, f"{e.nome}-chave.xlsx"
    elif qual == "exportados":
        pasta = e.pasta / "exportados"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(pasta.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(pasta).as_posix())
        c.repo.audit("exportar", f"lote “{e.nome}”: exportados baixados pelo cliente", user=s.username)
        return {"nome": f"{e.nome}-exportados.zip", "dados": base64.b64encode(buf.getvalue()).decode()}
    else:
        raise ValueError(f"arquivo desconhecido: {qual}")
    if not caminho.exists():
        raise FileNotFoundError("ainda não gravado")
    return {"nome": nome, "dados": base64.b64encode(caminho.read_bytes()).decode()}


def ia_feita(c, s, ident: str, study_uid: str, ok: bool, mensagem: str = "") -> dict:
    """O cliente rodou as IAs do exame e subiu o resultado (0.100.100): o lote segue."""
    e = _meu(c, s, ident)
    with e.trava_ia:
        p = e.pedidos_ia.get(study_uid)
        if p is not None:
            p["estado"], p["mensagem"] = ("feito" if ok else "erro"), str(mensagem or "")[:300]
            e.trava_ia.notify_all()
    return {"ok": True}


def copiado(c, s, ident: str, study_uid: str, imagens: int = -1) -> dict:
    """O cliente copiou o exame para o banco dele: se o lote apaga o que baixou, agora pode. 0.100.111: com o
    número de imagens que o cliente tem, confere — se o servidor tem mais (as IAs gravaram séries depois da cópia),
    pede a cópia de novo em vez de apagar."""
    e = _meu(c, s, ident)
    if int(imagens) >= 0:
        try:
            aqui = int(c.repo.instance_counts([study_uid]).get(study_uid, 0) or 0)
        except Exception:  # noqa: BLE001
            aqui = 0
        if int(imagens) < aqui:
            e.copiados.discard(study_uid)
            if study_uid not in e.para_copiar:
                e.para_copiar.append(study_uid)
            return {"ok": True, "de_novo": True}
    e.copiados.add(study_uid)
    if study_uid in e.apagar_quando_copiar:
        e.apagar_quando_copiar.discard(study_uid)
        try:
            c.repo.delete_study(study_uid, c.storage)
        except Exception as x:  # noqa: BLE001
            log.warning("lote: apagar %s depois da cópia: %s", study_uid, x)
    return {"ok": True}


def rpc(c, s, method: str, args: list, kwargs: dict, host: str = ""):
    a = list(args)

    def arg(i, nome, padrao=None):
        return a[i] if len(a) > i else kwargs.get(nome, padrao)
    if method == "lote_opcoes":
        return opcoes(c, s)
    if method == "lote_iniciar":
        return iniciar(c, s, arg(0, "corpo", {}) or {})
    if method == "lote_estado":
        return estado(c, s, arg(0, "ident", ""), int(arg(1, "desde", 0) or 0))
    if method == "lote_parar":
        return parar(c, s, arg(0, "ident", ""))
    if method == "lote_lista":
        return lista(c, s)
    if method == "lote_arquivo":
        return arquivo(c, s, arg(0, "ident", ""), arg(1, "qual", "saida"))
    if method == "lote_ia_feita":
        return ia_feita(c, s, arg(0, "ident", ""), arg(1, "study_uid", ""), bool(arg(2, "ok", False)),
                        arg(3, "mensagem", ""))
    if method == "lote_copiado":
        return copiado(c, s, arg(0, "ident", ""), arg(1, "study_uid", ""), int(arg(2, "imagens", -1)))
    raise PermissionError(f"método não permitido: {method}")
