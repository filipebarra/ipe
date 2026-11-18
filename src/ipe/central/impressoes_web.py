"""0.100.68: a aba Impressões e o Painel de filmes no Ipê Web.

É a aba **Impressões** do Ipê de mesa (`ui/prints_tab.py`) e o **Painel de filmes e impressões**
(`ui/film_dashboard.py`) atendidos pelo servidor: a lista do que chegou pela impressora DICOM, do que foi montado no
compositor e do filme que veio dentro do exame; a folha desenhada; identificar o paciente (com o OCR do cabeçalho);
enviar, reimprimir, juntar como páginas, apagar; os parados e a liberação; o histórico de envios; e as contas do painel.

- **Administradores e técnicos** (pelo papel do usuário, não pela permissão de imprimir: a tela mostra os filmes de
  todos os pacientes e manda para qualquer destino).
- **Os destinos são os do servidor, todos** (Configurações de impressão ▸ Destinos) — aqui não vale o "Compartilhar
  com os clientes" das impressoras DICOM, como na Gestão DICOM.
- **Tudo roda no servidor**: quem desenha a folha, lê o cabeçalho e fala com a impressora é ele, com o IP e o AE dele.
- As regras são as mesmas: o envio é o de `printing.dispatch.send`; depois de identificar o paciente, o filme segue
  pela regra (`encaminhar`), como no Ipê de mesa. As configurações (servidores, destinos, regras, modelos, origens)
  continuam no Ipê de mesa.
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

log = logging.getLogger(__name__)

PAPEIS = ("admin", "tecnico")
TIPO_TXT = {"scp": "Recebido", "aw": "Veio no exame", "film": "Montado aqui"}
FILTROS = [("", "Todos"), ("scp", "Recebidos pela impressora"), ("film", "Montados aqui"), ("aw", "Vieram no exame"),
           ("new", "Na lista"), ("sent", "Enviados"), ("held", "Parados")]
PERIODOS = [("30d", "Últimos 30 dias"), ("7d", "Últimos 7 dias"), ("hoje", "Hoje"), ("90d", "Últimos 90 dias"),
            ("12m", "Últimos 12 meses"), ("ano", "Este ano"), ("tudo", "Tudo"), ("datas", "Escolher as datas")]
MAX_LINHAS = 2000
_trava_envio = threading.Lock()          # um envio por vez: a impressora DICOM recebe uma associação de cada vez


def pode(s) -> bool:
    return getattr(s, "role", "") in PAPEIS


def _exigir(s) -> None:
    if not pode(s):
        raise PermissionError("as Impressões no navegador são só para administradores e técnicos")


# ====================================================================== linhas
def _k(r: dict) -> str:
    return f"aw:{r.get('study_uid') or ''}" if r.get("kind") == "aw" else f"{r.get('kind', 'scp')}:{r.get('id', '')}"


def _linhas(c) -> tuple[list[dict], list[str]]:
    """Todas as linhas, como a aba do Ipê de mesa monta (recebidos, filme da AW, montados aqui)."""
    repo = c.repo
    linhas: list[dict] = []
    problemas: list[str] = []

    def tenta(nome, fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - uma fonte que falha não derruba a lista
            log.exception("impressões no navegador: %s", nome)
            problemas.append(f"{nome}: {e}")
            return []
    for r in tenta("trabalhos recebidos", repo.print_jobs):
        linhas.append(dict(r, kind="scp"))
    from ipe.printing import aw_film as AW
    linhas.extend(tenta("filme que veio no exame", lambda: AW.studies(repo)))
    for f in tenta("filmes montados aqui", repo.films):
        linhas.append({"kind": "film", "id": f["id"], "source": "film", "uid": "",
                       "patient_name": f["patient_name"], "calling_ae": "",
                       "label": f["name"], "received_at": f["updated_at"], "sheets": f["sheets"],
                       "images": f["images"], "film_size": "",
                       "status": "sent" if f.get("printed_at") else "new", "destination": "", "folder": "",
                       "study_uid": (f["study_uids"] or [""])[0], "message": "",
                       "id_source": f.get("id_source", "") or "", "patient_id": f.get("patient_id", "") or ""})
    faltam = {r.get("study_uid") for r in linhas
              if r.get("kind") in ("film", "aw") and not r.get("modality") and r.get("study_uid")}
    if faltam:
        mods = tenta("modalidade dos filmes", lambda: repo.study_modalities(list(faltam))) or {}
        for r in linhas:
            if r.get("kind") in ("film", "aw") and not r.get("modality"):
                r["modality"] = mods.get(r.get("study_uid") or "", "")
    linhas.sort(key=lambda r: r.get("received_at") or datetime.min, reverse=True)
    return linhas, problemas


def _situacao(st, r: dict) -> str:
    from ipe.printing import held as H
    status = r.get("status", "new") or "new"
    if status == "new" and r.get("kind") == "film" and r.get("id_source") == "aguardando":
        return "Esperando paciente"
    if status == "new" and r.get("kind", "scp") == "scp":
        try:
            motivo = H.reason(st, r)
        except Exception:  # noqa: BLE001
            motivo = ""
        return {H.SEM_PACIENTE: "Esperando paciente", H.SEM_CADASTRO: "Parado: aparelho sem cadastro",
                H.DESLIGADA: "Parado: origem desligada", H.SEM_REGRA: "Na lista (nenhuma regra)"}.get(motivo, "Na lista")
    return {"new": "Na lista", "sent": "Enviado", "error": "Erro"}.get(status, status)


def _de_onde(st, r: dict) -> str:
    if r.get("kind") == "film":
        return "compositor"
    if r.get("kind") == "aw":
        return "veio no exame (estação AW)"
    from ipe.printing import origins as O
    o = O.job_origin(st, r)
    if o is not None and o.registered:
        return o.name
    return f"{r.get('calling_ae') or '?'} (não cadastrada)"


def _quando(v) -> tuple[str, str]:
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M"), v.strftime("%Y%m%d%H%M%S")
    return "", ""


def _json(st, r: dict) -> dict:
    txt, ordem = _quando(r.get("received_at"))
    pode_id = r["kind"] == "scp" or (r["kind"] == "film" and bool(r.get("id_source")))
    return {"k": _k(r), "kind": r["kind"], "tipo": TIPO_TXT.get(r["kind"], r["kind"]),
            "paciente": r.get("patient_name") or "", "rotulo": r.get("label") or "",
            "id": r.get("patient_id", "") or "",
            "modalidade": "/".join(m for m in str(r.get("modality") or "").split("\\") if m),
            "de_onde": _de_onde(st, r), "quando": txt, "ordem": ordem,
            "folhas": int(r.get("sheets") or 0), "imagens": int(r.get("images") or 0),
            "filme": r.get("film_size", "") or "", "situacao": _situacao(st, r), "status": r.get("status") or "new",
            "destino": r.get("destination", "") or "", "study_uid": r.get("study_uid") or "",
            "pode_identificar": pode_id, "sem_nome": r["kind"] == "scp" and not r.get("patient_name")}


def _achar(c, k: str) -> dict:
    for r in _linhas(c)[0]:
        if _k(r) == k:
            return r
    raise LookupError("este trabalho não está mais na lista")


def _varios(c, ks) -> list[dict]:
    quero = [str(k) for k in (ks or [])]
    mapa = {_k(r): r for r in _linhas(c)[0]}
    return [mapa[k] for k in quero if k in mapa]


def _destinos(c) -> list[dict]:
    from ipe.printing import dispatch as D
    return [{"nome": d.name, "rotulo": d.label(), "tipo": d.kind} for d in D.all_destinations(c.settings)]


def _modelos(c) -> list[str]:
    from ipe.printing.layout import all_templates
    try:
        return [m.name for m in all_templates(c.settings)]
    except Exception:  # noqa: BLE001
        log.exception("modelos de folha")
        return []


def lista(c, s, query: dict) -> dict:
    """A lista, com o filtro de tipo/situação e o texto; a faixa dos parados; os destinos e os modelos."""
    from ipe.printing import held as H
    from ipe.printing import ocr
    from ipe.printing import origins as O
    _exigir(s)
    st = c.settings
    todas, problemas = _linhas(c)
    so = (query.get("tipo") or [""])[0]
    texto = (query.get("q") or [""])[0].strip().lower()
    linhas = todas
    if so in ("scp", "film", "aw"):
        linhas = [r for r in linhas if r["kind"] == so]
    elif so in ("new", "sent"):
        linhas = [r for r in linhas if (r.get("status") or "new") == so]
    elif so == "held":
        linhas = H.held(linhas)
    if texto:
        linhas = [r for r in linhas if texto in " ".join(
            str(r.get(k, "")) for k in ("patient_name", "patient_id", "calling_ae", "label")).lower()]
    grupos = H.groups(st, todas)
    parados = sum(g.trabalhos for g in grupos)
    pendentes = O.pending(st)
    faixa = []
    if pendentes:
        quem = ", ".join(f"{o.calling_ae or '?'} ({o.remote_host or '?'})" for o in pendentes[:4])
        faixa.append(f"{len(pendentes)} origem(ns) sem cadastro: {quem + ('…' if len(pendentes) > 4 else '')}.")
    if parados:
        faixa.append(H.resumo(grupos))
    return {"linhas": [_json(st, r) for r in linhas[:MAX_LINHAS]], "total": len(linhas), "de": len(todas),
            "parados": parados, "faixa": faixa, "aviso": " · ".join(problemas[:2]),
            "destinos": _destinos(c), "modelos": _modelos(c),
            "filtros": [{"k": k, "nome": n} for k, n in FILTROS],
            "ocr": {"disponivel": bool(ocr.available()), "motivo": "" if ocr.available() else ocr.motivo_indisponivel()},
            "pode_apagar": pode(s), "papel": getattr(s, "role", "")}


# ====================================================================== a folha (prévia)
def _raiz_dos_filmes(c) -> Path:
    base = getattr(getattr(c, "net", None), "print_root", None)
    return Path(base) / "filmes" if base else Path.home() / ".dicomviewer-filmes"


def _memoria(c) -> OrderedDict:
    m = getattr(c, "_impressoes_memoria", None)
    if m is None:
        m = c._impressoes_memoria = OrderedDict()
    return m


def _lembrar(c, chave, fazer, maximo: int = 24):
    m = _memoria(c)
    if chave in m:
        m.move_to_end(chave)
        return m[chave]
    v = fazer()
    m[chave] = v
    while len(m) > maximo:
        m.popitem(last=False)
    return v


def _na_tela(c, fn, espera: float = 120):
    """Roda `fn` na linha da tela: o desenho das folhas usa as células do compositor, que são QWidget."""
    return c.ponte.chamar(fn, espera=espera)


def _job(c, r: dict):
    """(PrintJob, pasta) do recebido ou do filme da AW; (None, None) se não há mais."""
    from ipe.printing import jobs as J
    if r.get("kind") == "aw":
        from ipe.printing import aw_film as AW
        uid = str(r.get("study_uid") or "")
        return _lembrar(c, ("aw", uid), lambda: AW.to_job(c.repo, uid, _raiz_dos_filmes(c)), 6)
    if r.get("kind") != "scp" or not r.get("folder"):
        return None, None
    pasta = Path(r["folder"])
    return J.load(pasta), pasta


def _filme(c, r: dict):
    from ipe.printing.film import Film
    dados = c.repo.film_data(int(r["id"]))
    return Film.from_dict(dados) if dados else None


def _png(img) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def _n_folhas(c, r: dict) -> int:
    if r["kind"] == "film":
        f = _filme(c, r)
        return len(f.sheets) if f is not None else 0
    job, _pasta = _job(c, r)
    return len(job.films) if job is not None else 0


def folha(c, s, query: dict) -> bytes:
    """A folha `i` do trabalho `k`, em PNG (a mesma que a aba do Ipê de mesa mostra)."""
    _exigir(s)
    r = _achar(c, (query.get("k") or [""])[0])
    i = int((query.get("i") or ["0"])[0] or 0)
    grande = (query.get("grande") or [""])[0] == "1"

    def desenhar() -> bytes:
        from ipe.printing import dispatch as D
        if r["kind"] == "film":
            from ipe.imaging.series import FrameCache
            from ipe.ui.film.render import FrameSource, render_sheet_image
            filme = _filme(c, r)
            if filme is None or not 0 <= i < len(filme.sheets):
                raise LookupError("folha fora do filme")
            fonte = FrameSource(c.repo)
            try:
                return _png(render_sheet_image(filme, i, fonte, FrameCache(max_mb=128), c.settings,
                                               dpi=110 if grande else 60))
            finally:
                fonte.clear()
        job, pasta = _job(c, r)
        if job is None:
            raise LookupError("a pasta deste trabalho não está mais no servidor")
        if not 0 <= i < len(job.films):
            raise LookupError("folha fora do trabalho")
        return _png(D.sheet_qimage(pasta, job.films[i], dpi=130 if grande else 72))
    chave = ("png", _k(r), i, grande, str(r.get("received_at") or ""), int(r.get("sheets") or 0))
    return _lembrar(c, chave, lambda: _na_tela(c, desenhar))


# ====================================================================== detalhes e histórico
def _ref(r: dict) -> tuple[str, str]:
    if r.get("kind") == "aw":
        return "aw", str(r.get("study_uid") or "")
    return r.get("kind", "scp"), str(r.get("id", ""))


def _envios(c, r: dict) -> list[dict]:
    try:
        return c.repo.sends(*_ref(r))
    except Exception:  # noqa: BLE001
        log.exception("histórico de envios")
        return []


def _envio_json(e: dict) -> dict:
    quando = e["at"].strftime("%d/%m/%Y %H:%M:%S") if isinstance(e.get("at"), datetime) else ""
    como = {"regra": "pela regra", "reimpressão": "reimpressão", "compositor": "no compositor"}.get(e.get("how", ""), "à mão")
    ok = bool(e.get("ok", True))
    return {"quando": quando, "destino": e.get("destination", "") or "", "quem": e.get("user", "") or "", "como": como,
            "modelo": e.get("template") or "como veio", "ok": ok,
            "resultado": "ok" if ok else f"falhou: {e.get('message', '')}"}


def detalhes(c, s, query: dict) -> dict:
    """O que a aba mostra ao lado da folha: as linhas do trabalho, quantas folhas e os envios."""
    from ipe.printing import jobs as J
    _exigir(s)
    r = _achar(c, (query.get("k") or [""])[0])
    out = {"k": _k(r), "folhas": 0, "linhas": [], "titulo": "", "envios": [_envio_json(e) for e in _envios(c, r)],
           "mensagem": ""}
    if r["kind"] == "film":
        out["folhas"] = _n_folhas(c, r)
        out["titulo"] = r.get("label", "") or ""
        out["linhas"] = [r.get("patient_name") or "",
                         f"{r.get('sheets', 0)} folha(s), {r.get('images', 0)} imagem(ns)", "Montado no compositor"]
        if not out["folhas"]:
            out["mensagem"] = "Não deu para desenhar este filme."
        return out
    job, _pasta = _job(c, r)
    if job is None:
        out["mensagem"] = "A pasta deste trabalho não está mais aqui."
        return out
    job.patient_name = r.get("patient_name") or job.patient_name
    out["folhas"] = len(job.films)
    film = job.films[0] if job.films else None
    out["titulo"] = job.title()
    if film is not None:
        mm_w, mm_h = J.sheet_mm(film)
        grade = film.display_format.replace(chr(92), " ")
        if r["kind"] == "aw":
            out["titulo"] = r.get("patient_name") or ""
            out["linhas"] = [f"Folha da estação AW, {mm_w:.0f}×{mm_h:.0f} mm",
                             f"{r.get('sheets', 0)} folha(s) e {r.get('images', 0)} imagem(ns) no exame",
                             "Veio dentro do exame, não pela impressora DICOM"]
        else:
            out["linhas"] = [f"Grade {grade}, filme {film.film_size or '?'} ({mm_w:.0f}×{mm_h:.0f} mm)",
                             f"{job.copies} cópia(s) em {job.medium or '?'}, saída {job.destination or '?'}",
                             f"Rótulo da sessão: {job.label or '(vazio)'}",
                             f"Chegou de {job.calling_ae or '?'} ({job.remote_host or '?'})"]
            if job.server:
                out["linhas"].append(f"Recebido em: {job.server}")
        out["linhas"] += [f"Anotação: {a.get('text', '')}" for a in film.annotations[:4]]
    out["mensagem"] = r.get("message") or ""
    return out


# ====================================================================== enviar
def _local_ae(c) -> str:
    net = getattr(c, "net", None)
    if net is not None and getattr(net, "local_ae", ""):
        return net.local_ae
    st = c.settings
    return str((st.get("dicom", {}) or {}).get("ae_title", "") if st is not None else "") or "DICOMVIEWER"


def _preparar(c, r: dict):
    """O trabalho pronto para sair: o recebido vem do disco; o montado aqui é desenhado agora."""
    if r["kind"] in ("scp", "aw"):
        return _job(c, r)
    from ipe.ui.prints_tab import film_to_job
    return _na_tela(c, lambda: film_to_job(c.repo, c.settings, int(r["id"]), _raiz_dos_filmes(c)), 600)


def enviar_linhas(c, usuario: str, linhas: list[dict], dest, template: str = "", how: str = "manual") -> dict:
    """Manda cada trabalho para o destino e anota o resultado e o histórico — o `send_rows` da aba do Ipê de mesa.
    Devolve {"ok", "falhas", "mensagens"}."""
    from ipe.printing import dispatch as D
    ok = falhas = 0
    msgs: list[str] = []
    repo = c.repo
    repo.audit("imprimir", f"impressoes (navegador): {len(linhas)} para {dest.label()}", user=usuario or "local")
    ae = _local_ae(c)
    with _trava_envio:
        for r in linhas:
            try:
                job, pasta = _preparar(c, r)
                if job is None:
                    raise D.PrintError("Não foi possível montar este trabalho.")
                if D.needs_gui(dest):
                    msg = _na_tela(c, lambda j=job, p=pasta: D.send(j, p, dest, c.settings, ae, template), 600)
                else:
                    msg = D.send(job, pasta, dest, c.settings, ae, template)
                ok += 1
                if r["kind"] == "scp":
                    repo.update_print_job(r["id"], status="sent", destination=dest.name, message=msg)
                elif r["kind"] == "film":
                    repo.mark_film_printed(r["id"], usuario or "", dest.label())
                bom, texto = True, msg
            except Exception as e:  # noqa: BLE001 - um trabalho ruim não para os outros
                falhas += 1
                log.exception("Falha ao enviar impressão (navegador)")
                if r["kind"] == "scp":
                    repo.update_print_job(r["id"], status="error", destination=dest.name, message=str(e))
                bom, texto = False, str(e)
            msgs.append(texto if bom else f"Falha ao enviar: {texto}")
            try:
                repo.add_send(*_ref(r), dest.name, usuario or "", how, bom, texto or "", template=template)
            except Exception:  # noqa: BLE001 - o histórico não derruba o envio
                log.exception("histórico de envios")
    return {"ok": ok, "falhas": falhas, "mensagens": msgs}


def _resultado(r: dict) -> dict:
    if r["falhas"]:
        r["mensagem"] = f"{r['ok']} enviado(s), {r['falhas']} com erro. Veja a coluna Situação."
    else:
        r["mensagem"] = f"{r['ok']} trabalho(s) enviados."
    return r


def enviar(c, s, corpo: dict) -> dict:
    from ipe.printing.dispatch import find_destination
    _exigir(s)
    linhas = _varios(c, corpo.get("ks"))
    if not linhas:
        raise ValueError("escolha um trabalho")
    dest = find_destination(c.settings, str(corpo.get("destino") or ""))
    if dest is None:
        raise LookupError("destino de impressão não encontrado")
    modelo = str(corpo.get("modelo") or "")
    if modelo and modelo not in _modelos(c):
        raise LookupError("modelo de folha não encontrado")
    return _resultado(enviar_linhas(c, s.username, linhas, dest, modelo, "manual"))


def _ultimo_destino(c, r: dict):
    from ipe.printing import dispatch as D
    ok = [e for e in _envios(c, r) if e.get("ok", True)]
    candidatos = [(e.get("destination", ""), e.get("template", "")) for e in ok[:1]]
    if r.get("kind") == "scp" and r.get("destination"):
        candidatos.append((r["destination"], ""))
    for nome, modelo in candidatos:
        d = D.find_destination(c.settings, nome)
        if d is None:                     # o compositor grava o rótulo do destino, não o nome
            d = next((x for x in D.all_destinations(c.settings) if x.label() == nome), None)
        if d is not None:
            return d, modelo or ""
    return None, ""


def _plano(c, linhas: list[dict]):
    grupos: dict = {}
    sem: list[dict] = []
    for r in linhas:
        d, modelo = _ultimo_destino(c, r)
        if d is None:
            sem.append(r)
        else:
            grupos.setdefault((d.name, modelo), (d, []))[1].append(r)
    return grupos, sem


def reimprimir(c, s, corpo: dict) -> dict:
    """Cada trabalho de novo para o último destino que deu certo. Sem `confirmar`, devolve só o plano."""
    _exigir(s)
    linhas = _varios(c, corpo.get("ks"))
    grupos, sem = _plano(c, linhas)
    if not grupos:
        return {"plano": "", "n": 0, "sem": len(sem), "mensagem": "Nenhum dos trabalhos escolhidos foi enviado antes, "
                "então não há destino para repetir. Use “Enviar para…”."}
    partes = [(f"para {d.name}, com o modelo {m}: {len(rs)}" if m else f"para {d.name}: {len(rs)}")
              for (_n, m), (d, rs) in grupos.items()]
    n = sum(len(rs) for _d, rs in grupos.values())
    plano = f"Reimprimir {n} trabalho(s) — " + "; ".join(partes) + "."
    if not corpo.get("confirmar"):
        return {"plano": plano, "n": n, "sem": len(sem),
                "aviso": f"Ficam de fora {len(sem)} que nunca foram enviados." if sem else ""}
    ok = falhas = 0
    for (_n, modelo), (d, rs) in grupos.items():
        r = enviar_linhas(c, s.username, rs, d, modelo, "reimpressão")
        ok, falhas = ok + r["ok"], falhas + r["falhas"]
    return {"ok": ok, "falhas": falhas, "mensagem": f"Reimpressos: {ok}; com erro: {falhas}. Veja o Histórico."
            if falhas else f"Reimpressos: {ok} trabalho(s)."}


# ====================================================================== encaminhar pela regra
def encaminhar(c, usuario: str, row: dict) -> tuple[bool, str]:
    """Manda **um** trabalho recebido pelo caminho das regras (o `forward_row` do Ipê de mesa).
    Devolve (saiu, motivo de não ter saído)."""
    from ipe.printing import arrival
    from ipe.printing import held as HELD
    from ipe.printing import jobs as J
    from ipe.printing import origins as O
    from ipe.printing.dispatch import find_destination
    if not row or not row.get("folder"):
        return False, ""
    job = J.load(row["folder"])
    if job is None:
        return False, ""
    st = c.settings
    pode_ir, motivo = O.may_forward(st, row)
    if not pode_ir:
        return False, motivo
    if arrival.falta_paciente(st, row):
        return False, ("O OCR não identificou o paciente do filme: ele ficou esperando você "
                       "confirmar em Impressões › Identificar paciente.")
    alvos = HELD.alvos(st, row, job)
    if not alvos:
        return False, ""                          # sem regra: fica na lista
    saiu = False
    for nome, modelo in alvos:
        dest = find_destination(st, nome)
        if dest is None:
            return False, f"Destino “{nome}” não existe mais; o trabalho ficou na lista."
        r = enviar_linhas(c, usuario, [dict(row, kind="scp")], dest, modelo, "regra")
        saiu = saiu or bool(r["ok"])
    return saiu, ""


def _liberar_filme_montado(c, usuario: str, film_id: int) -> str:
    """Filme montado com imagens recebidas, que esperava o paciente: segue pela regra de quando chegou."""
    from ipe.printing import held as HELD
    from ipe.printing import origins as O
    from ipe.printing.dispatch import find_destination
    dados = c.repo.film_data(film_id) or {}
    enc = (dados.get("paciente") or {}).get("encaminhar") or {}
    linha = dict(enc.get("linha") or {})
    if not linha:
        return ""
    pode_ir, motivo = O.may_forward(c.settings, linha)
    if not pode_ir:
        return motivo
    alvos = [(enc["destino"], enc.get("modelo", ""))] if enc.get("destino") else HELD.alvos(c.settings, linha)
    saiu = False
    for destino, modelo in alvos:
        dest = find_destination(c.settings, destino)
        if dest is None:
            return f"Destino “{destino}” não existe mais; o filme ficou na lista."
        atual = next((r for r in _linhas(c)[0] if r["kind"] == "film" and r["id"] == film_id), None)
        if atual is not None:
            saiu = bool(enviar_linhas(c, usuario, [atual], dest, modelo, "regra")["ok"]) or saiu
    if not alvos:
        return "Paciente confirmado. Nenhuma regra manda este filme para lugar nenhum: ele ficou na lista."
    return "Paciente confirmado; o filme seguiu pela regra." if saiu else "Paciente confirmado."


# ====================================================================== identificar o paciente
def _candidato_json(cand: dict) -> dict:
    from ipe.printing.matching import describe
    texto = describe(cand)
    if cand.get("ocr"):
        texto = f"OCR {cand.get('score', 0) * 100:.0f}% · {texto}"
    return {"texto": texto, "nome": cand.get("patient_name", "") or "", "id": cand.get("patient_id", "") or "",
            "study_uid": cand.get("study_uid", "") or "", "ocr": bool(cand.get("ocr"))}


def _para_identificar(c, k: str) -> dict:
    r = _achar(c, k)
    if not (r["kind"] == "scp" or (r["kind"] == "film" and r.get("id_source"))):
        raise ValueError("este trabalho não é identificado por aqui")
    return r


def identificar_abrir(c, s, corpo: dict) -> dict:
    """O que a janela "Identificar o paciente" abre mostrando: o nome e o ID de agora e os exames do mesmo aparelho
    e horário."""
    from ipe.printing import ocr
    _exigir(s)
    r = _para_identificar(c, str(corpo.get("k") or ""))
    cands = []
    nome, ident = r.get("patient_name", "") or "", r.get("patient_id", "") or ""
    if r["kind"] == "scp":
        job, _pasta = _job(c, r)
        if job is not None:
            from ipe.printing.matching import candidates
            cands = candidates(c.repo, job)
    else:
        pac = (c.repo.film_data(int(r["id"])) or {}).get("paciente") or {}
        nome = pac.get("patient_name", "") or (nome if r.get("id_source") != "aguardando" else "")
        ident = pac.get("patient_id", "") or ident
    return {"k": _k(r), "nome": nome, "id": ident, "candidatos": [_candidato_json(x) for x in cands],
            "ocr": bool(ocr.available()), "motivo": "" if ocr.available() else ocr.motivo_indisponivel()}


def _ler_cabecalho(c, r: dict) -> str:
    from ipe.printing import arrival
    from ipe.printing import jobs as J
    from ipe.printing.ocr import read_header
    if r["kind"] == "film":
        filme = _filme(c, r)
        if filme is None:
            return ""
        textos = []
        for _onde, f in arrival.fontes_do_filme(c.repo, filme, quantas=1):
            if len(textos) == 2:                  # alto e rodapé; a imagem inteira fica de fora
                break
            textos.append(f())
        return "\n".join(t for t in textos if t and t.strip())
    job, pasta = _job(c, r)
    if job is None:
        return ""
    partes = [arrival.texto_sem_ocr(job)]
    if job.films:
        pagina = J.compose_sheet(pasta, job.films[0], width=1600)
        partes += [read_header(pagina, parte="cima"), read_header(pagina, parte="baixo")]
    return "\n".join(p for p in partes if p and p.strip())


def ocr(c, s, corpo: dict) -> dict:
    """Lê o cabeçalho da primeira folha (alto e rodapé) e procura o paciente no banco. É sugestão: quem confirma é
    a pessoa."""
    from ipe.printing import ocr as OCR
    _exigir(s)
    r = _para_identificar(c, str(corpo.get("k") or ""))
    if not OCR.available():
        raise RuntimeError(OCR.motivo_indisponivel())
    texto = _ler_cabecalho(c, r)
    achados = []
    if texto.strip():
        try:
            achados = OCR.combinar(texto, c.repo.studies_for_ocr())
        except Exception:  # noqa: BLE001
            log.exception("comparar o OCR com o banco")
    nome, ident = OCR.guess(texto)
    certo = bool(achados) and OCR.escolher(achados) is not None
    c.repo.audit("ocr", f"impressoes (navegador): {_k(r)}", user=s.username)
    msg = ""
    if not achados and not nome and not ident:
        msg = "Não consegui ler um nome nem um ID no cabeçalho da folha. O texto lido está na janela, para você conferir."
    return {"texto": texto.strip(), "candidatos": [_candidato_json(dict(a, ocr=True)) for a in achados],
            "nome": nome or "", "id": ident or "", "certo": certo, "mensagem": msg}


def identificar(c, s, corpo: dict) -> dict:
    """Grava o paciente confirmado e deixa o filme seguir pela regra, como no Ipê de mesa."""
    from ipe.printing import jobs as J
    _exigir(s)
    r = _para_identificar(c, str(corpo.get("k") or ""))
    nome, ident = str(corpo.get("nome") or "").strip(), str(corpo.get("id") or "").strip()
    if not nome and not ident:
        raise ValueError("escreva o nome ou o ID do paciente")
    escolhido = str(corpo.get("study_uid") or "")
    origem = "exame" if escolhido else "manual"
    repo = c.repo
    repo.audit("identificar", f"impressoes (navegador): {_k(r)} → {ident or nome}", user=s.username)
    if r["kind"] == "film":
        repo.set_film_patient(int(r["id"]), nome, ident, origem)
        msg = "Paciente confirmado."
        if r.get("id_source") == "aguardando" and (r.get("status") or "new") == "new":
            msg = _liberar_filme_montado(c, s.username, int(r["id"])) or msg
        return {"ok": True, "mensagem": msg}
    campos = {"patient_name": nome, "patient_id": ident, "id_source": origem}
    from ipe.printing.modalidade import descobrir
    campos["modality"] = descobrir(repo, c.settings, dict(r, patient_id=ident)) or r.get("modality", "")
    repo.update_print_job(r["id"], **campos)
    job, pasta = _job(c, r)
    if job is not None and pasta is not None:
        job.patient_name, job.patient_id = nome, ident
        job.id_source, job.modality = campos["id_source"], campos["modality"]
        J.save(job, pasta.parent)
    atual = repo.print_job(r["id"]) or dict(r, **campos)
    msg = "Paciente confirmado."
    if (atual.get("status") or "new") == "new" and (atual.get("source") or "scp") == "scp":
        saiu, motivo = encaminhar(c, s.username, atual)
        msg = "Paciente confirmado; o filme seguiu pela regra." if saiu else (motivo or msg)
    return {"ok": True, "mensagem": msg}


# ====================================================================== juntar e apagar
def juntar(c, s, corpo: dict) -> dict:
    """Folhas recebidas separadas → páginas de um trabalho só (o que chegou primeiro). Sem `confirmar`, só avisa."""
    from ipe.printing import juntar as JUN
    _exigir(s)
    sel = [r for r in _varios(c, corpo.get("ks")) if r.get("kind") == "scp"]
    if len(sel) < 2:
        raise ValueError("escolha dois ou mais trabalhos recebidos pela impressora")
    sel.sort(key=lambda r: JUN._quando(r.get("received_at")) or datetime.min)
    base, resto = sel[0], sel[1:]
    avisos = []
    if any(not JUN.mesma_origem(base, r) for r in resto):
        avisos.append("vieram de origens diferentes")
    if any(JUN.mesmo_paciente(base, r) is False for r in resto):
        avisos.append("o paciente identificado não é o mesmo em todas")
    if any(r.get("status") != "new" for r in sel):
        avisos.append("alguma já foi enviada (o histórico de envio das juntadas sai junto)")
    if not corpo.get("confirmar"):
        quem = base.get("patient_name") or base.get("label") or "um trabalho"
        return {"plano": f"Juntar {len(sel)} trabalhos como páginas de “{quem}”?",
                "aviso": ("Atenção: " + "; ".join(avisos) + ".") if avisos else ""}
    sink = getattr(getattr(c, "net", None), "sink", None)
    novo = JUN.juntar(c.repo, base, resto, sink, getattr(sink, "storage", None))
    c.repo.audit("imprimir", f"impressoes (navegador): {len(sel)} juntados", user=s.username)
    _memoria(c).clear()
    return {"ok": True, "k": f"scp:{(novo or base).get('id', base.get('id'))}",
            "mensagem": f"{len(sel)} trabalhos juntados: {(novo or {}).get('sheets', 0)} folha(s) em um só."}


def apagar(c, s, corpo: dict) -> dict:
    """Tira da lista os recebidos e os montados aqui (o filme que veio no exame é do exame). Os exames já guardados
    no banco não são apagados."""
    _exigir(s)
    sel = _varios(c, corpo.get("ks"))
    recebidos = [r for r in sel if r["kind"] == "scp"]
    filmes = [r for r in sel if r["kind"] == "film"]
    do_exame = [r for r in sel if r["kind"] == "aw"]
    n = len(recebidos) + len(filmes)
    if not n:
        raise ValueError("O filme que veio no exame não se apaga daqui: ele é do exame. Apague o exame no banco.")
    repo = c.repo
    for r in recebidos + filmes:
        try:
            repo.delete_sends(*_ref(r))
        except Exception:  # noqa: BLE001
            log.exception("apagar o histórico de envios")
    for r in recebidos:
        pasta = repo.delete_print_job(r["id"])
        if pasta:
            shutil.rmtree(pasta, ignore_errors=True)
    for r in filmes:
        repo.delete_film(r["id"])
    repo.audit("apagar", f"impressoes (navegador): {n} trabalho(s) da lista", user=s.username)
    _memoria(c).clear()
    msg = f"{n} trabalho(s) apagado(s) da lista de impressões."
    if do_exame:
        msg += " " + f"{len(do_exame)} filme(s) que vieram no exame ficam como estão."
    return {"ok": True, "n": n, "mensagem": msg}


# ====================================================================== parados
def _carregar(row: dict):
    from ipe.printing import jobs as J
    pasta = (row or {}).get("folder", "")
    return J.load(pasta) if pasta else None


def parados(c, s) -> dict:
    """A fila dos parados, por aparelho, com o motivo de cada grupo."""
    from ipe.printing import held as H
    _exigir(s)
    gs = H.groups(c.settings, _linhas(c)[0], _carregar)
    simbolo = {H.PRONTO: "✔"}
    return {"grupos": [{"id": g.origin_id, "nome": g.label(), "motivo": H.TEXTO.get(g.motivo, g.motivo),
                        "simbolo": simbolo.get(g.motivo, "⌛"), "trabalhos": g.trabalhos, "folhas": g.folhas,
                        "imagens": g.imagens, "desde": g.desde()[:16], "pode_liberar": g.pode_liberar,
                        "ks": [_k(dict(r, kind="scp")) for r in g.rows]} for g in gs],
            "resumo": H.resumo(gs), "prontos": sum(g.trabalhos for g in gs if g.pode_liberar)}


def liberar(c, s, corpo: dict) -> dict:
    """Solta os parados que já têm para onde ir — todos, ou só os de um aparelho. Um por um, pela regra."""
    from ipe.printing import held as H
    _exigir(s)
    linhas = H.releasable(c.settings, _linhas(c)[0], str(corpo.get("id") or ""), _carregar)
    enviados = falhas = 0
    for row in linhas:
        atual = c.repo.print_job_by_uid(row.get("uid", "")) or row
        try:
            ok, _motivo = encaminhar(c, s.username, atual)
        except Exception:  # noqa: BLE001 - um filme ruim não para a fila
            log.exception("Liberando o trabalho %s", row.get("uid", ""))
            ok = False
        enviados += 1 if ok else 0
        falhas += 0 if ok else 1
    return {"ok": enviados, "falhas": falhas,
            "mensagem": f"{enviados} trabalho(s) enviados, {falhas} com erro." if falhas
            else f"{enviados} trabalho(s) enviados."}


# ====================================================================== painel
def _data(v) -> str:
    return v.strftime("%d/%m/%Y %H:%M") if isinstance(v, datetime) else ""


def _tempo(t) -> dict:
    from ipe.core import film_stats as F
    return {"mediana": F.duracao(t.mediana), "p90": F.duracao(t.p90), "n": t.n, "negativos": t.negativos,
            "horas": t.mediana}


def _dia(txt: str) -> date | None:
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def painel(c, s, query: dict) -> dict:
    """As contas do Painel de filmes e impressões (`core.film_stats`), com os mesmos filtros."""
    from ipe.core import film_stats as F
    from ipe.printing import origins as O
    _exigir(s)

    def q(nome: str, padrao: str = "") -> str:
        return (query.get(nome) or [padrao])[0]
    repo = c.repo
    dicom = []
    try:
        dicom = repo.print_job_stats_rows()
    except Exception:  # noqa: BLE001
        log.exception("painel: impressões recebidas")
    for r in dicom:
        o = O.job_origin(c.settings, r) if c.settings is not None else None
        r["created_by"] = (o.name if o is not None and o.registered else "") or r.get("calling_ae") \
            or "(aparelho desconhecido)"
    todas = F.linhas(repo.film_stats_rows() + dicom)
    chave = q("periodo", "30d")
    de, ate = (_dia(q("de")), _dia(q("ate"))) if chave == "datas" else F.periodo(chave)
    flt = F.Filtro(de, ate, q("mod"), q("user"), q("tipo"))
    ls = [l for l in todas if flt.aceita(l)]
    try:
        dias = max(0, min(365, int(q("dias", "2") or 2)))
    except ValueError:
        dias = 2
    r = F.resumo(ls, dias_parado=dias)
    n_dicom = sum(1 for l in ls if l.tipo == "dicom")

    def grupo(g) -> dict:
        return {"nome": g.nome, "filmes": g.filmes, "impressos": g.impressos, "pct": F.porcentagem(g.pct),
                "exame_filme": F.duracao(g.exame_filme.mediana), "filme_impressao": F.duracao(g.filme_impressao.mediana),
                "folhas_impressas": g.folhas_impressas, "reimpressoes": g.reimpressoes}

    def linha(l) -> dict:
        return {"id": l.id, "tipo": l.tipo, "origem": l.origem, "criado": _data(l.criado),
                "ordem": l.criado.strftime("%Y%m%d%H%M%S"), "criado_por": l.criado_por, "paciente": l.paciente,
                "modalidade": l.modalidade, "exame": _data(l.exame), "descricao": l.exame_descricao,
                "folhas": l.folhas, "imagens": l.imagens, "impresso": l.impresso, "impresso_em": _data(l.impresso_em),
                "impresso_por": l.impresso_por, "destino": l.destino if l.impresso else "",
                "impressoes": l.impressoes, "exame_filme": F.duracao(l.h_exame_filme),
                "filme_impressao": F.duracao(l.h_filme_impressao), "exame_impressao": F.duracao(l.h_exame_impressao),
                "study_uid": l.study_uid, "k": (f"scp:{l.id}" if l.tipo == "dicom" else f"film:{l.id}")}
    so_nao = q("so_nao") == "1"
    visiveis = [l for l in ls if not l.impresso] if so_nao else ls
    visiveis = sorted(visiveis, key=lambda l: l.criado, reverse=True)
    return {
        "periodos": [{"k": k, "nome": n} for k, n in PERIODOS],
        "de": de.isoformat() if de else "", "ate": ate.isoformat() if ate else "",
        "modalidades": sorted({m for l in todas for m in (l.modalidades or [F.SEM_MODALIDADE])}),
        "usuarios": sorted({l.criado_por for l in todas}),
        "cartoes": {
            "filmes": r.filmes, "compositor": r.filmes - n_dicom, "dicom": n_dicom, "folhas": r.folhas,
            "imagens": r.imagens, "pct": F.porcentagem(r.pct), "impressos": r.impressos, "reimpressos": r.reimpressos,
            "parados": len(r.parados), "nao_impressos": r.nao_impressos, "dias": dias,
            "parados_lista": [f"{_data(l.criado)} — {l.paciente} ({l.modalidade})" for l in r.parados[:15]],
            "exame_filme": _tempo(r.exame_filme), "filme_impressao": _tempo(r.filme_impressao),
            "exame_impressao": _tempo(r.exame_impressao),
            "em_24h": f"{100 * r.impressos_24h / r.impressos:.0f}%" if r.impressos else "",
            "folhas_impressas": r.folhas_impressas, "impressoes": r.impressoes,
            "destinos": [{"nome": d, "n": n} for d, n in r.por_destino[:8]]},
        "por_mes": [{"mes": m, "impressos": a, "nao": b} for m, a, b in r.por_mes],
        "por_modalidade": [grupo(g) for g in r.por_modalidade],
        "por_usuario": [grupo(g) for g in r.por_usuario],
        "linhas": [linha(l) for l in visiveis[:MAX_LINHAS]], "total": len(visiveis), "no_periodo": len(ls)}


# ====================================================================== no idioma do navegador
_TRADUZ = {"tipo", "situacao", "de_onde", "mensagem", "aviso", "faixa", "linhas_txt", "como", "resultado", "modelo",
           "motivo", "resumo", "plano", "nome_filtro", "origem", "titulo_txt"}
_NOMES = {"filtros", "periodos"}            # listas de {k, nome}: o nome é texto do programa


def traduzir(r, lang: str, dentro: str = ""):
    """Traduz, na resposta, só o que é texto do programa (nunca pacientes, nomes de destino ou de aparelho)."""
    from ipe.central.gestao_web import _t
    from ipe.core import i18n as I
    lang = I.normalize(lang or "")
    if not lang or lang == I.BASE_LANG:
        return r
    if isinstance(r, list):
        return [(_t(x, lang) if isinstance(x, str) and dentro in ("faixa", "linhas", "parados_lista")
                 else traduzir(x, lang, dentro)) for x in r]
    if not isinstance(r, dict):
        return r
    out = {}
    for k, v in r.items():
        if k in ("destinos", "modelos", "candidatos", "modalidades", "usuarios", "ks"):
            out[k] = v
        elif isinstance(v, str) and (k in _TRADUZ or (k == "nome" and dentro in _NOMES)
                                     or (k == "motivo") or (k == "modalidade" and v.startswith("("))):
            out[k] = _t(v, lang)
        elif isinstance(v, list) and k == "linhas" and v and isinstance(v[0], str):
            out[k] = [_t(x, lang) for x in v]
        elif isinstance(v, (dict, list)):
            out[k] = traduzir(v, lang, k if isinstance(v, list) else dentro)
        else:
            out[k] = v
    return out


def rota(c, s, method: str, acao: str, query: dict, corpo: dict):
    """As rotas JSON (`/api/web/impressoes/<ação>`); a folha em PNG é `folha` (o servidor a trata à parte)."""
    lang = (query.get("lang") or [""])[0]
    return traduzir(_rota(c, s, method, acao, query, corpo), lang)


def _rota(c, s, method: str, acao: str, query: dict, corpo: dict):
    if method == "GET":
        if acao == "lista":
            return lista(c, s, query)
        if acao == "detalhes":
            return detalhes(c, s, query)
        if acao == "parados":
            return parados(c, s)
        if acao == "painel":
            return painel(c, s, query)
        raise LookupError("rota")
    if method != "POST":
        raise LookupError("método")
    fn = {"enviar": enviar, "reimprimir": reimprimir, "identificar_abrir": identificar_abrir, "ocr": ocr,
          "identificar": identificar, "juntar": juntar, "apagar": apagar, "liberar": liberar}.get(acao)
    if fn is None:
        raise LookupError("rota")
    return fn(c, s, corpo)
