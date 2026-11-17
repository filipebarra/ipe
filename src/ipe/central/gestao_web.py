"""0.100.63: a Gestão DICOM no Ipê Web — conferir se os exames das modalidades estão no PACS e mandar o que falta.

É a janela de Gestão do Ipê de mesa (`ui/gestao_dialog.py`) atendida pelo servidor: a regra de rede é a mesma
(`network/gestao.py`); aqui ficam o estado da conferência, a fila de envio e as rotas do navegador.

- **Só administradores.** A tela mostra os exames de todos os equipamentos e dispara envios.
- **Os nós são os do servidor, todos** (os DIMSE ativos) — aqui não vale o "Compartilhar com os clientes" dos nós:
  quem administra a rede vê a rede como o servidor a vê.
- **Tudo roda no servidor**: a conferência e o envio seguem com a aba do navegador fechada; quem abrir a tela de novo
  (ou outro administrador) vê o mesmo estado. Uma operação por vez.
- O que foi escolhido (modalidades, identidades, PACS, período…) fica em `settings["gestao"]`, o mesmo lugar que a
  janela do Ipê de mesa usa no computador do servidor.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from ipe.network import gestao as G
from ipe.network.client import DicomError

log = logging.getLogger(__name__)

CHAVE = "gestao"
PERIODOS = [("hoje", "Hoje"), ("ontem", "Ontem"), ("2dias", "Ontem e hoje"), ("7dias", "Últimos 7 dias"),
            ("datas", "Escolher as datas")]
SIMBOLO = {"erro": "⚠", "ausente": "✖", "outro_uid": "≠", "incompleto": "◐", "sem_contagem": "?", "completo": "✔"}
RESUMO = {"completo": "completo(s)", "incompleto": "incompleto(s)", "ausente": "ausente(s) no PACS",
          "outro_uid": "com outro UID no PACS", "sem_contagem": "sem contagem", "erro": "com erro"}
FILA_MAX = 300


def _admin(s) -> None:
    if getattr(s, "role", "") != "admin":
        raise PermissionError("a Gestão DICOM no navegador é só para administradores")


def _net(c):
    net = getattr(c, "net", None)
    if net is None:
        raise RuntimeError("este servidor não tem a rede DICOM ligada")
    return net


def _chave(conf: G.Conferencia) -> str:
    return f"{conf.fonte_id}|{conf.study_uid}"


def _linha(conf: G.Conferencia) -> dict:
    e = conf.estudo
    ser, img = conf.contagem()
    return {
        "k": _chave(conf), "fonte": conf.fonte, "situacao": conf.situacao, "texto": conf.texto(),
        "problema": conf.problema, "detalhe": conf.detalhe, "envio": conf.envio,
        "data": e.get("study_date", ""), "hora": e.get("study_time", ""), "paciente": e.get("patient_name", ""),
        "id": e.get("patient_id", ""), "accession": e.get("accession", ""), "descricao": e.get("description", ""),
        "series_txt": ser, "imagens_txt": img,
        "series": [{"numero": s.numero, "descricao": s.descricao, "modalidade": s.modalidade,
                    "origem": s.imagens_origem, "pacs": s.imagens_pacs, "situacao": s.situacao,
                    "texto": G.SITUACOES_SERIE.get(s.situacao, s.situacao), "faltam": s.faltam}
                   for s in conf.series],
    }


class Estado:
    """A conferência e a fila do servidor (uma só, de todos os administradores)."""

    def __init__(self):
        self.trava = threading.RLock()
        self.v = 1                       # muda a cada alteração: o navegador só recebe o estado de novo se mudou
        self.ocupado = ""                # "" | "conferindo" | "enviando"
        self.mensagem = ""
        self.feitos = self.total = 0
        self.resultados: dict[str, G.Conferencia] = {}
        self.ordem: list[str] = []
        self.erros: list[str] = []
        self.fontes: dict = {}           # id do nó → Fonte usada na conferência
        self.pacs: G.Fonte | None = None
        self.cfg: dict = {}
        self.cancel = threading.Event()
        self.fila: list[dict] = []
        self.lote = 0
        self.quem = ""
        self.quando = ""

    def mudou(self) -> None:
        with self.trava:
            self.v += 1

    def por(self, conf: G.Conferencia) -> None:
        with self.trava:
            k = _chave(conf)
            if k not in self.resultados:
                self.ordem.append(k)
            self.resultados[k] = conf
            self.v += 1

    def resumo(self) -> str:
        with self.trava:
            res = [self.resultados[k] for k in self.ordem]
            if not res:
                if self.ocupado == "conferindo":
                    return "Conferindo…"
                if not self.quando:
                    return ""
                return "Nenhum exame conferido." if self.erros else "Nenhum exame encontrado nas modalidades no período."
            cont: dict[str, int] = {}
            for c in res:
                cont[c.situacao] = cont.get(c.situacao, 0) + 1
            partes = [f"{len(res)} exame(s)"]
            partes += [f"{SIMBOLO[k]} {cont[k]} {nome}" for k, nome in RESUMO.items() if cont.get(k)]
            return " · ".join(partes)

    def texto_dos_erros(self) -> str:
        with self.trava:
            partes = []
            if self.erros:
                partes.append("Alguns nós não puderam ser conferidos:\n" + "\n".join(f"• {e}" for e in self.erros))
            por_motivo: dict[str, int] = {}
            for k in self.ordem:
                c = self.resultados[k]
                if c.situacao == "erro":
                    por_motivo[c.detalhe] = por_motivo.get(c.detalhe, 0) + 1
            if por_motivo:
                partes.append("Exames com erro:\n" + "\n".join(
                    f"• {n} exame(s): {m}" for m, n in sorted(por_motivo.items(), key=lambda x: -x[1])))
            return "\n\n".join(partes)

    def json(self) -> dict:
        with self.trava:
            return {"v": self.v, "ocupado": self.ocupado, "mensagem": self.mensagem, "feitos": self.feitos,
                    "total": self.total, "linhas": [_linha(self.resultados[k]) for k in self.ordem],
                    "resumo": self.resumo(), "erros": self.texto_dos_erros(), "fila": list(self.fila),
                    "pacs": self.pacs.nome if self.pacs else "", "quem": self.quem, "quando": self.quando,
                    "periodo": [self.cfg.get("de", ""), self.cfg.get("ate", "")]}


def _estado(c) -> Estado:
    e = getattr(c, "_gestao_web", None)
    if e is None:
        e = c._gestao_web = Estado()
    return e


# ---------------------------------------------------------------------- o que a tela mostra
def _cfg(c) -> dict:
    cfg = c.settings.get(CHAVE, {}) if c.settings is not None else {}
    return dict(cfg) if isinstance(cfg, dict) else {}


def _ident(i: dict) -> dict:
    return {"id": i["id"], "nome": i.get("name", ""), "ae": i.get("ae_title", "")}


def nos(c, s) -> dict:
    """Os nós DIMSE ativos do servidor (todos), as identidades que cada um aceita, os destinos de envio e o que
    ficou guardado da última vez."""
    _admin(s)
    net = _net(c)
    from ipe.network.nodes import send_nodes
    todos = c.repo.nodes(only_active=True)
    dimse = [n for n in todos if n.get("kind") == "dimse"]
    return {
        "nos": [{"id": n["id"], "nome": n["name"], "ae": n.get("ae_title", ""), "host": n.get("host", ""),
                 "porta": n.get("port", 0), "identidades": [_ident(i) for i in net.identities_for(n)]}
                for n in dimse],
        "dicomweb": [n["name"] for n in todos if n.get("kind") == "dicomweb"],
        "destinos": [{"id": n["id"], "nome": n["name"], "identidades": [_ident(i) for i in net.identities_for(n)]}
                     for n in send_nodes(c.repo)],
        "local_ae": net.local_ae,
        "cfg": {k: v for k, v in _cfg(c).items() if k != "geometria"},
        "modos": [{"k": k, "nome": v} for k, v in G.MODOS_ENVIO.items()],
        "periodos": [{"k": k, "nome": v} for k, v in PERIODOS],
    }


def estado(c, s, v=None) -> dict:
    _admin(s)
    e = _estado(c)
    try:
        if v is not None and int(v) == e.v:
            return {"v": e.v, "igual": True}
    except (TypeError, ValueError):
        pass
    return e.json()


def _fonte(c, d: dict | None) -> G.Fonte | None:
    if not d or not d.get("no"):
        return None
    no = c.repo.node(int(d["no"]))
    if no is None or no.get("kind") != "dimse":
        return None
    return G.Fonte(no, c.repo.identity(int(d["ident"])) if d.get("ident") else None)


def eco(c, s, corpo: dict) -> dict:
    """C-ECHO: o nó responde ao servidor, com esta identidade?"""
    _admin(s)
    net = _net(c)
    f = _fonte(c, corpo)
    if f is None:
        raise KeyError("nó desconhecido")
    t0 = time.perf_counter()
    try:
        ok, msg = net.client.echo(net.target(f.no, f.identidade))
    except Exception as e:  # noqa: BLE001
        ok, msg = False, str(e)
    return {"ok": bool(ok), "mensagem": msg, "ms": round((time.perf_counter() - t0) * 1000)}


def _datas(corpo: dict) -> tuple[str, str]:
    import re
    k = str(corpo.get("periodo") or "hoje")
    if k != "datas":
        return G.periodo(k)
    de, ate = str(corpo.get("de") or ""), str(corpo.get("ate") or "")
    for d in (de, ate):
        if not re.fullmatch(r"\d{8}", d):
            raise ValueError("datas: AAAAMMDD")
    return (ate, de) if de > ate else (de, ate)


def _guardar(c, corpo: dict, fontes_todas: list[dict]) -> None:
    if c.settings is None:
        return
    cfg = _cfg(c)
    cfg.update({
        "fontes": {str(f["no"]): {"on": bool(f.get("on", True)), "ident": f.get("ident") or None} for f in fontes_todas},
        "pacs": (corpo.get("pacs") or {}).get("no"), "pacs_ident": (corpo.get("pacs") or {}).get("ident") or None,
        "destino": str(corpo.get("destino") or "").strip(), "modo": corpo.get("modo") or "auto",
        "periodo": corpo.get("periodo") or "hoje", "ignorar": str(corpo.get("ignorar") or "").strip(),
        "exato": bool(corpo.get("exato")), "so_problemas": bool(corpo.get("so_problemas"))})
    try:
        c.settings.set(CHAVE, cfg)
        c.settings.save()
    except Exception:  # noqa: BLE001
        log.warning("não guardei as escolhas da gestão", exc_info=True)


def _linha_de_trabalho(nome: str, fn) -> None:
    threading.Thread(target=fn, name=nome, daemon=True).start()


def conferir(c, s, corpo: dict, host: str = "") -> dict:
    _admin(s)
    net = _net(c)
    e = _estado(c)
    todas = [f for f in (corpo.get("fontes") or []) if isinstance(f, dict) and f.get("no")]
    pacs = _fonte(c, corpo.get("pacs"))
    if pacs is None:
        raise ValueError("escolha o PACS")
    fontes = [f for f in (_fonte(c, x) for x in todas if x.get("on", True)) if f is not None
              and f.no["id"] != pacs.no["id"]]
    if not fontes:
        raise ValueError("marque pelo menos uma modalidade (que não seja o próprio PACS)")
    de, ate = _datas(corpo)
    ignorar = [x.strip() for x in str(corpo.get("ignorar") or "").split(";") if x.strip()]
    exato = bool(corpo.get("exato"))
    modo = corpo.get("modo") if corpo.get("modo") in G.MODOS_ENVIO else "auto"
    destino = str(corpo.get("destino") or "").strip() or pacs.no.get("ae_title", "")
    with e.trava:
        if e.ocupado:
            raise ValueError("já há uma operação da gestão em andamento neste servidor")
        e.ocupado, e.mensagem, e.feitos, e.total = "conferindo", "Conferindo…", 0, 0
        e.resultados, e.ordem, e.erros = {}, [], []
        e.fontes = {f.no["id"]: f for f in fontes}
        e.pacs = pacs
        e.cfg = {"ignorar": ignorar, "exato": exato, "de": de, "ate": ate, "destino": destino, "modo": modo}
        e.cancel = cancel = threading.Event()
        e.quem, e.quando = s.username, datetime.now().strftime("%d/%m/%Y %H:%M")
        e.v += 1
    _guardar(c, corpo, todas)
    conferidor = G.Conferidor(net.client, net.target)

    def progresso(feitos: int, total: int, msg: str) -> None:
        with e.trava:
            e.feitos, e.total, e.mensagem = feitos, total, msg
            e.v += 1

    def trabalho() -> None:
        erro = None
        try:
            _res, erros = conferidor.conferir(fontes, pacs, de, ate, ignorar=ignorar, exato=exato, cancel=cancel,
                                              progresso=progresso, ao_conferir=e.por)
            with e.trava:
                e.erros = list(erros)
        except Exception as ex:  # noqa: BLE001
            erro = ex
            log.warning("conferência da gestão (web) parou: %s", ex)
        with e.trava:
            e.ocupado = ""
            if erro is not None:
                e.mensagem = f"Conferência parou: {erro}"
                e.erros = e.erros + [str(erro)]
            else:
                txt = e.texto_dos_erros()
                e.mensagem = txt.splitlines()[0] if txt else ("Conferência interrompida." if cancel.is_set() else "")
            e.v += 1
        try:
            quem = ", ".join(f.nome for f in fontes)
            c.repo.audit("gestão", f"conferência (navegador) {de}–{ate}: {quem} × {pacs.nome} — {e.resumo()}",
                         user=s.username, host=host)
        except Exception:  # noqa: BLE001
            log.debug("auditoria da gestão", exc_info=True)
    _linha_de_trabalho("gestao-web-conferir", trabalho)
    return e.json()


def parar(c, s) -> dict:
    _admin(s)
    e = _estado(c)
    with e.trava:
        if e.ocupado:
            e.cancel.set()
            e.mensagem = "Parando…"
            e.v += 1
    return e.json()


# ---------------------------------------------------------------------- enviar
def _fila_entrar(e: Estado, sel: list[G.Conferencia], destino: str, modo_txt: str) -> int:
    with e.trava:
        e.lote += 1
        hora = datetime.now().strftime("%H:%M")
        for conf in sel:
            e.fila.append({"lote": e.lote, "k": _chave(conf), "estado": "fila",
                           "paciente": conf.estudo.get("patient_name", "") or "",
                           "accession": conf.estudo.get("accession", "") or "", "destino": destino, "modo": modo_txt,
                           "hora": hora, "resultado": ""})
        del e.fila[:-FILA_MAX]
        e.v += 1
        return e.lote


def _fila_estado(e: Estado, lote: int, k: str, estado_: str, msg: str) -> None:
    with e.trava:
        for it in e.fila:
            if it["lote"] == lote and it["k"] == k:
                it["estado"], it["resultado"] = estado_, msg
        e.v += 1


def _fila_fechar(e: Estado, lote: int) -> None:
    with e.trava:
        for it in e.fila:
            if it["lote"] == lote and it["estado"] in ("fila", "enviando"):
                it["estado"], it["resultado"] = "parado", "o envio foi interrompido"
        e.v += 1


def _reconferir_um(conferidor, f, pacs, conf, cfg, envio: str = "", espera: float = 2.0):
    """Depois do envio, perguntar de novo: "enviado" não é "está no PACS" (igual à janela do Ipê de mesa)."""
    novo = conf
    for tentativa in range(3):
        time.sleep(espera if tentativa else min(espera, 1.0))
        try:
            novo = conferidor.reconferir(f, pacs, conf.study_uid, ignorar=cfg.get("ignorar", ()),
                                         exato=cfg.get("exato", False))
        except DicomError as ex:
            novo = conf
            envio = f"{envio} — não deu para conferir de novo: {ex}"
            break
        if novo.situacao == "completo":
            break
    novo.fonte_id = conf.fonte_id
    novo.envio = envio if novo.situacao == "completo" else f"{envio} — conferido de novo: {novo.texto().lower()}"
    return novo


def _selecao(e: Estado, chaves) -> list[G.Conferencia]:
    with e.trava:
        return [e.resultados[k] for k in dict.fromkeys(str(x) for x in (chaves or [])) if k in e.resultados]


def enviar(c, s, corpo: dict, host: str = "", espera: float = 2.0) -> dict:
    """Manda os exames marcados: ao PACS da conferência (o que falta, ou o exame inteiro) ou, com `para`, a outro
    destino de envio (o que falta é contado **lá**; se o destino não responde à busca, vai o exame inteiro)."""
    _admin(s)
    net = _net(c)
    e = _estado(c)
    inteiro = bool(corpo.get("inteiro"))
    para = _destino(c, corpo.get("para")) if corpo.get("para") else None
    with e.trava:
        if e.ocupado:
            raise ValueError("já há uma operação da gestão em andamento neste servidor")
        pacs = e.pacs
        if pacs is None:
            raise ValueError("faça a conferência antes de enviar")
        sel = _selecao(e, corpo.get("chaves"))
        if para is None:
            sel = [x for x in sel if x.situacao != "erro" and (inteiro or x.situacao in ("incompleto", "ausente"))]
        else:
            sel = [x for x in sel if x.situacao != "erro"]
        if not sel:
            raise ValueError("nenhum dos exames marcados tem o que enviar")
        fontes, cfg = dict(e.fontes), dict(e.cfg)
        modo = corpo.get("modo") if corpo.get("modo") in G.MODOS_ENVIO else cfg.get("modo", "auto")
        destino_ae = str(corpo.get("destino") or "").strip() or cfg.get("destino", "")
        alvo_nome = (para or pacs).nome
        e.cancel = cancel = threading.Event()
        e.ocupado = "enviando"
        e.mensagem = f"Enviando {len(sel)} exame(s) para {alvo_nome}…"
        e.feitos, e.total = 0, len(sel)
        for x in sel:
            x.envio = "Na fila…" if para is None else f"Na fila para {alvo_nome}…"
        lote = _fila_entrar(e, sel, alvo_nome, f"{'inteiro' if inteiro else 'o que falta'} · {G.MODOS_ENVIO[modo]}")
    rem = G.Remetente(net.client, net.target, sink=net.sink, repo=c.repo)
    conferidor = G.Conferidor(net.client, net.target)

    def um(conf: G.Conferencia, f: G.Fonte) -> None:
        k = _chave(conf)
        if para is None:
            try:
                r = rem.enviar(modo, f, pacs, conf, destino_ae, inteiro=inteiro, cancel=cancel)
            except Exception as ex:  # noqa: BLE001
                log.warning("Envio da gestão (web) falhou (%s): %s", conf.study_uid, ex)
                conf.envio = f"Falhou: {ex}"
                _fila_estado(e, lote, k, "falhou", str(ex))
                e.mudou()
                return
            msg = r["mensagem"]
            c.repo.audit("gestão", f"envio ao {pacs.nome} (navegador): {conf.estudo.get('accession', '')} "
                                   f"{conf.estudo.get('patient_name', '')} — {msg}",
                         user=s.username, study_uid=conf.study_uid, host=host)
            _fila_estado(e, lote, k, "nada" if msg.startswith("Nada a enviar") else "ok", msg)
            e.por(_reconferir_um(conferidor, f, pacs, conf, cfg, msg, espera))
            return
        nota, estado_ = "", "ok"
        try:
            alvo, tudo = conf, inteiro
            if not inteiro:
                try:
                    alvo = conferidor.reconferir(f, para, conf.study_uid, ignorar=cfg.get("ignorar", ()),
                                                 exato=cfg.get("exato", False))
                except DicomError as ex:
                    alvo, tudo = conf, True
                    nota = f" (não deu para conferir em {para.nome}: foi o exame inteiro — {ex})"
            if not tudo and alvo.situacao == "completo":
                msg, estado_ = f"já estava completo em {para.nome}", "nada"
            elif not tudo and alvo.situacao == "erro":
                raise RuntimeError(alvo.detalhe or "não deu para conferir")
            else:
                r = rem.enviar(modo, f, para, alvo, para.no.get("ae_title", ""), inteiro=tudo, cancel=cancel)
                msg = r["mensagem"] + nota
            c.repo.audit("gestão", f"envio a {para.nome} (navegador): {conf.estudo.get('accession', '')} "
                                   f"{conf.estudo.get('patient_name', '')} — {msg}",
                         user=s.username, study_uid=conf.study_uid, host=host)
            conf.envio = f"→ {para.nome}: {msg}"
            _fila_estado(e, lote, k, estado_, msg)
        except Exception as ex:  # noqa: BLE001
            log.warning("Envio da gestão (web) para %s falhou (%s): %s", para.nome, conf.study_uid, ex)
            conf.envio = f"→ {para.nome}: falhou: {ex}"
            _fila_estado(e, lote, k, "falhou", str(ex))
        e.mudou()

    def trabalho() -> None:
        feitos = 0
        try:
            for i, conf in enumerate(sel, 1):
                if cancel.is_set():
                    break
                f = fontes.get(conf.fonte_id)
                k = _chave(conf)
                if f is None:
                    _fila_estado(e, lote, k, "falhou", "o nó de origem saiu da lista")
                    continue
                _fila_estado(e, lote, k, "enviando", "")
                with e.trava:
                    e.feitos = i - 1
                    e.mensagem = f"{conf.estudo.get('patient_name', '')}: enviando ({i} de {len(sel)})…"
                    e.v += 1
                um(conf, f)
                feitos += 1
        finally:
            _fila_fechar(e, lote)
            with e.trava:
                e.ocupado = ""
                e.feitos = feitos
                e.mensagem = ("Envio interrompido." if cancel.is_set() else
                              f"{feitos} exame(s) tratado(s) no envio para {alvo_nome}.")
                e.v += 1
    _linha_de_trabalho("gestao-web-enviar", trabalho)
    return e.json()


def _destino(c, d: dict | None) -> G.Fonte:
    from ipe.network.nodes import send_nodes
    nid = int((d or {}).get("no") or 0)
    no = next((n for n in send_nodes(c.repo) if n["id"] == nid), None)
    if no is None:
        raise KeyError("destino de envio desconhecido")
    return G.Fonte(no, c.repo.identity(int(d["ident"])) if d.get("ident") else None)


def reconferir(c, s, corpo: dict) -> dict:
    """Pergunta de novo ao PACS pelos exames marcados."""
    _admin(s)
    net = _net(c)
    e = _estado(c)
    with e.trava:
        if e.ocupado:
            raise ValueError("já há uma operação da gestão em andamento neste servidor")
        sel = _selecao(e, corpo.get("chaves"))
        pacs = e.pacs
        if not sel or pacs is None:
            raise ValueError("nada a conferir de novo")
        fontes, cfg = dict(e.fontes), dict(e.cfg)
        e.cancel = cancel = threading.Event()
        e.ocupado, e.mensagem, e.feitos, e.total = "conferindo", "Conferindo de novo…", 0, len(sel)
        e.v += 1
    conferidor = G.Conferidor(net.client, net.target)

    def trabalho() -> None:
        try:
            for i, conf in enumerate(sel, 1):
                if cancel.is_set():
                    break
                f = fontes.get(conf.fonte_id)
                if f is None:
                    continue
                try:
                    novo = conferidor.reconferir(f, pacs, conf.study_uid, ignorar=cfg.get("ignorar", ()),
                                                 exato=cfg.get("exato", False))
                    novo.fonte_id, novo.envio = conf.fonte_id, conf.envio
                    e.por(novo)
                except DicomError as ex:
                    conf.envio = f"não deu para conferir de novo: {ex}"
                with e.trava:
                    e.feitos = i
                    e.v += 1
        finally:
            with e.trava:
                e.ocupado, e.mensagem = "", ""
                e.v += 1
    _linha_de_trabalho("gestao-web-reconferir", trabalho)
    return e.json()


def limpar_fila(c, s) -> dict:
    _admin(s)
    e = _estado(c)
    with e.trava:
        e.fila = [it for it in e.fila if it["estado"] in ("fila", "enviando")]
        e.v += 1
    return e.json()


def rota(c, s, method: str, acao: str, query: dict, corpo: dict, host: str = "") -> dict:
    if method == "GET" and acao == "nos":
        return nos(c, s)
    if method == "GET" and acao == "estado":
        return estado(c, s, (query.get("v") or [None])[0])
    if method != "POST":
        raise LookupError("método")
    if acao == "conferir":
        return conferir(c, s, corpo, host)
    if acao == "parar":
        return parar(c, s)
    if acao == "enviar":
        return enviar(c, s, corpo, host)
    if acao == "reconferir":
        return reconferir(c, s, corpo)
    if acao == "limpar_fila":
        return limpar_fila(c, s)
    if acao == "eco":
        return eco(c, s, corpo)
    raise LookupError("rota")
