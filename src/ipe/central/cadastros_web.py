"""0.100.71: Cadastros no Ipê Web — o que o administrador mantinha só no Ipê de mesa do servidor.

- **Usuários** (criar, editar, ativar/desativar, redefinir a senha, excluir) e **perfis e permissões**;
- **Nós DICOM** (DIMSE e DICOMweb), com o teste de rede, e as **identidades** (AE de origem);
- **Impressoras DICOM** (as mesmas de Filme ▸ Impressoras DICOM), com o teste de conexão;
- **Automações de IA** (Preferências ▸ CAD/IA: o que roda sozinho na chegada, em que exames e para onde vai);
- **Registro de acesso**, só de leitura.

Regras:
- **Só administradores** (pelo papel). A exceção é `minha_senha`: qualquer pessoa troca a própria senha.
- As regras são as das janelas do Ipê de mesa (`ui/users_dialog.py`, `ui/network_dialog.py`, `ui/film/dialogs.py`,
  `ui/cad_ia.py`): senha de 6 caracteres ou mais; sempre sobra um administrador ativo; ninguém exclui a si mesmo.
- **Senhas e segredos nunca saem do servidor**: a resposta diz só se há um guardado; campo vazio = fica o que estava.
- Tudo o que muda vai para o registro de acesso com o nome de quem mudou.
- Usuário desativado, excluído ou com a senha redefinida perde na hora as sessões abertas.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

AE_RE = re.compile(r"^[A-Za-z0-9_\-. ]{1,16}$")
CHAVE_IMPRESSORAS = "printing.dicom_printers"
PERIODOS_REGISTRO = [("1", "Hoje"), ("7", "Últimos 7 dias"), ("30", "Últimos 30 dias"), ("0", "Tudo")]


def _admin(s) -> None:
    if getattr(s, "role", "") != "admin":
        raise PermissionError("os cadastros no navegador são só para administradores")


def _settings(c):
    st = getattr(c, "settings", None)
    if st is None:
        raise RuntimeError("este servidor não tem as configurações carregadas")
    return st


def _registrar(c, s, acao: str, texto: str, host: str = "") -> None:
    try:
        c.repo.audit(acao, texto, user=getattr(s, "username", "?"), host=host)
    except Exception:  # noqa: BLE001 - o registro não pode impedir o cadastro
        log.exception("registro de acesso")


def _fez(antes, o_que: str, nome: str) -> str:
    """O texto do registro de acesso (fica em português, como o resto do registro)."""
    return ("criou " if antes is None else "editou ") + o_que + nome


def _quando(v) -> str:
    return v.strftime("%d/%m/%Y %H:%M") if isinstance(v, datetime) else ""


def _texto(d: dict, k: str, limite: int = 200) -> str:
    return str(d.get(k) or "").strip()[:limite]


def _inteiro(v, padrao: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return padrao


# ====================================================================== usuários e perfis
def usuarios(c, s) -> dict:
    _admin(s)
    from ipe.auth.permissions import PERMISSIONS, ROLES, role_permissions
    perfis = role_permissions(c.repo)
    return {
        "eu": getattr(s, "username", ""),
        "usuarios": [{"id": u["id"], "username": u["username"], "full_name": u["full_name"] or "", "role": u["role"],
                      "papel": ROLES.get(u["role"], u["role"]), "active": bool(u["active"]),
                      "must_change": bool(u["must_change"]), "conta_sistema": u.get("conta_sistema") or "",
                      "criado": _quando(u.get("created")), "ultimo": _quando(u.get("last_login"))}
                     for u in c.repo.users()],
        "papeis": [{"k": k, "nome": v} for k, v in ROLES.items()],
        "permissoes": [{"k": k, "nome": v} for k, v in PERMISSIONS.items()],
        "perfis": {r: sorted(p) for r, p in perfis.items()},
    }


def _admins_ativos(c, menos: int | None = None) -> int:
    return sum(1 for u in c.repo.users() if u["role"] == "admin" and u["active"] and u["id"] != menos)


def _encerrar_sessoes(c, user_id, menos=None) -> None:
    """Tira do servidor as sessões abertas deste usuário (navegador e Ipê cliente)."""
    with c._lock:
        for tok in [t for t, (ss, _q) in c.tokens.items() if ss.user_id == user_id and ss is not menos]:
            c.tokens.pop(tok, None)


def _atualizar_sessoes(c, user_id, role: str, nome: str) -> None:
    with c._lock:
        for ss, _q in c.tokens.values():
            if ss.user_id == user_id:
                ss.role, ss.full_name = role, nome


def usuario_gravar(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    from ipe.auth.passwords import password_problem
    from ipe.auth.permissions import ROLES
    uid = d.get("id") or None
    antes = next((u for u in c.repo.users() if u["id"] == uid), None) if uid else None
    if uid and antes is None:
        raise LookupError("usuário desconhecido")
    nome = _texto(d, "username", 64)
    if antes is None and not nome:
        raise ValueError("Preencha o usuário.")
    papel = str(d.get("role") or (antes or {}).get("role") or "medico")
    if papel not in ROLES:
        raise ValueError("Perfil desconhecido.")
    ativo = bool(d.get("active", True))
    senha = str(d.get("password") or "")
    if antes is None or senha:
        problema = password_problem(senha)
        if problema:
            raise ValueError(problema)
    if antes is not None and antes["role"] == "admin" and antes["active"] and (papel != "admin" or not ativo) \
            and _admins_ativos(c, menos=uid) == 0:
        raise ValueError("Precisa sobrar pelo menos um administrador ativo.")
    dados = {"full_name": _texto(d, "full_name", 120), "role": papel, "active": ativo}
    if "conta_sistema" in d:                             # só o Ipê de mesa usa (entrada automática): a tela não mexe
        dados["conta_sistema"] = _texto(d, "conta_sistema", 120)
    if antes is None:
        dados.update(username=nome, password=senha, must_change=bool(d.get("must_change", True)))
    else:
        dados["id"] = uid
        if senha:
            dados.update(password=senha, must_change=bool(d.get("must_change", True)))
    novo = c.repo.save_user(dados)
    quem = nome if antes is None else antes["username"]
    _registrar(c, s, "usuarios", _fez(antes, "", quem) + " (" + ROLES[papel] + ")" + ("" if ativo else ", desativado")
               + (", senha nova" if antes and senha else ""), host)
    if antes is not None:
        if not ativo or senha:
            _encerrar_sessoes(c, uid, menos=s if senha and ativo else None)
        else:
            _atualizar_sessoes(c, uid, papel, dados["full_name"])
    return {"ok": True, "id": novo, "mensagem": f"Usuário {quem} gravado."}


def usuario_senha(c, s, d: dict, host: str = "") -> dict:
    """Redefinir: a senha nova é provisória — no próximo acesso a pessoa escolhe a dela."""
    _admin(s)
    from ipe.auth.passwords import password_problem
    u = next((x for x in c.repo.users() if x["id"] == d.get("id")), None)
    if u is None:
        raise LookupError("usuário desconhecido")
    senha = str(d.get("senha") or "")
    problema = password_problem(senha)
    if problema:
        raise ValueError(problema)
    c.repo.set_password(u["id"], senha, must_change=True)
    _registrar(c, s, "usuarios", f"redefiniu a senha de {u['username']}", host)
    _encerrar_sessoes(c, u["id"], menos=s)
    return {"ok": True, "mensagem": f"Senha de {u['username']} redefinida: no próximo acesso ela será trocada."}


def usuario_excluir(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    u = next((x for x in c.repo.users() if x["id"] == d.get("id")), None)
    if u is None:
        raise LookupError("usuário desconhecido")
    if u["username"].lower() == str(getattr(s, "username", "")).lower():
        raise ValueError("Você não pode excluir o próprio usuário.")
    if u["role"] == "admin" and u["active"] and _admins_ativos(c, menos=u["id"]) == 0:
        raise ValueError("Precisa sobrar pelo menos um administrador ativo.")
    c.repo.delete_user(u["id"])
    _registrar(c, s, "usuarios", f"excluiu {u['username']}", host)
    _encerrar_sessoes(c, u["id"])
    return {"ok": True, "mensagem": f"Usuário {u['username']} excluído."}


def perfis_gravar(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    from ipe.auth.permissions import PERMISSIONS, ROLES
    if d.get("padrao"):
        c.repo.set_app_setting("roles", {})
        _registrar(c, s, "usuarios", "voltou os perfis ao padrão", host)
        return {"ok": True, "mensagem": "Perfis de volta ao padrão."}
    tabela = d.get("perfis")
    if not isinstance(tabela, dict):
        raise ValueError("Faltou a tabela dos perfis.")
    limpa = {r: [p for p in PERMISSIONS if p in set(tabela.get(r) or [])] for r in ROLES if r != "admin"}
    c.repo.set_app_setting("roles", limpa)
    _registrar(c, s, "usuarios", "alterou as permissões dos perfis", host)
    return {"ok": True, "mensagem": "Permissões dos perfis gravadas."}


def minha_senha(c, s, d: dict, host: str = "") -> dict:
    """Qualquer pessoa troca a própria senha (é o que a senha provisória pede no primeiro acesso)."""
    from ipe.auth.passwords import password_problem
    if not getattr(s, "user_id", None):
        raise PermissionError("esta sessão não tem usuário")
    atual, nova = str(d.get("atual") or ""), str(d.get("nova") or "")
    if c.repo.authenticate(s.username, atual) is None:
        raise ValueError("A senha atual não confere.")
    problema = password_problem(nova)
    if problema:
        raise ValueError(problema)
    if nova == atual:
        raise ValueError("A senha nova precisa ser diferente da atual.")
    c.repo.set_password(s.user_id, nova, must_change=False)
    s.must_change = False
    _registrar(c, s, "usuarios", "trocou a própria senha", host)
    return {"ok": True, "mensagem": "Senha trocada."}


# ====================================================================== nós DICOM e identidades
def _todos_os_nos(c) -> list[dict]:
    return [n for n in c.repo.nodes(todos=True) if n.get("kind") != "servidor"]


def _no_json(n: dict) -> dict:
    web = n.get("kind") == "dicomweb"
    return {
        "id": n["id"], "name": n.get("name") or "", "kind": "dicomweb" if web else "dimse",
        "ae_title": n.get("ae_title") or "", "host": n.get("host") or "", "port": int(n.get("port") or 0),
        "base_url": n.get("base_url") or "", "username": n.get("username") or "",
        "tem_senha": bool(n.get("password")), "verify_tls": n.get("verify_tls") is not False,
        "auth": n.get("auth") or "basic", "token_url": n.get("token_url") or "", "client_id": n.get("client_id") or "",
        "tem_segredo": bool(n.get("client_secret")), "scope": n.get("scope") or "",
        "retrieve": n.get("retrieve") or "get", "move_destination": n.get("move_destination") or "",
        "use_in_search": bool(n.get("use_in_search")), "use_in_priors": bool(n.get("use_in_priors")),
        "use_in_send": bool(n.get("use_in_send")), "stream_open": n.get("stream_open"),
        "compartilhar_clientes": bool(n.get("compartilhar_clientes")), "priority": int(n.get("priority") or 0),
        "active": bool(n.get("active")), "note": n.get("note") or "",
        "endereco": (n.get("base_url") or "") if web else " @ ".join([n.get("ae_title") or "", (n.get("host") or "") + ":" + str(n.get("port") or "")]),
    }


def nos(c, s) -> dict:
    _admin(s)
    from ipe.network import oauth
    lista = _todos_os_nos(c)
    net = getattr(c, "net", None)
    return {
        "nos": [_no_json(n) for n in lista],
        "identidades": [{"id": i["id"], "name": i.get("name") or "", "ae_title": i.get("ae_title") or "",
                         "move_destination": i.get("move_destination") or "", "note": i.get("note") or "",
                         "allowed_nodes": [int(x) for x in str(i.get("allowed_nodes") or "").split(",") if x.strip().isdigit()]}
                        for i in c.repo.identities(todos=True)],
        "auths": [{"k": k, "nome": v} for k, v in oauth.TIPOS.items()],
        "ae_local": getattr(net, "local_ae", "") if net is not None else "",
        "rede": net is not None,
    }


def _ae(v: str, o_que: str = "AE Title") -> str:
    v = (v or "").strip()
    if not AE_RE.match(v):
        raise ValueError(f"Campo “{o_que}”: até 16 caracteres (letras, números, - _ .).")
    return v


def _no_da_tela(c, d: dict) -> tuple[dict, dict | None]:
    """O nó como a tela mandou, conferido; e o que estava gravado (para os segredos que não voltam)."""
    nid = d.get("id") or None
    antes = next((n for n in _todos_os_nos(c) if n["id"] == nid), None) if nid else None
    if nid and antes is None:
        raise LookupError("nó desconhecido")
    nome = _texto(d, "name", 80)
    if not nome:
        raise ValueError("Preencha o nome.")
    comum = {"name": nome, "use_in_search": bool(d.get("use_in_search", True)),
             "use_in_priors": bool(d.get("use_in_priors", True)), "use_in_send": bool(d.get("use_in_send", True)),
             "compartilhar_clientes": bool(d.get("compartilhar_clientes", False)), "active": bool(d.get("active", True)),
             "stream_open": d.get("stream_open") if d.get("stream_open") in (True, False) else None,
             "priority": _inteiro(d.get("priority"), 0, 0, 99), "note": _texto(d, "note", 200)}
    if str(d.get("kind") or "dimse") == "dicomweb":
        from ipe.network import oauth
        url = _texto(d, "base_url", 300).rstrip("/")
        if not re.match(r"^https?://\S+$", url):
            raise ValueError("Preencha o endereço DICOMweb (a base, que costuma terminar em /dicom-web).")
        auth = str(d.get("auth") or "basic")
        if auth not in oauth.TIPOS:
            raise ValueError("Tipo de autenticação desconhecido.")
        token_url, client_id = _texto(d, "token_url", 300), _texto(d, "client_id", 200)
        if auth.startswith("oauth2") and not (token_url and client_id):
            raise ValueError("No OAuth2, preencha o endereço do token (ou do emissor OIDC) e o ID do cliente.")
        no = {**comum, "kind": "dicomweb", "base_url": url, "username": _texto(d, "username", 120),
              "verify_tls": bool(d.get("verify_tls", True)), "auth": auth, "token_url": token_url,
              "client_id": client_id, "scope": _texto(d, "scope", 200),
              "ae_title": "", "host": "", "port": 0, "retrieve": "get", "move_destination": ""}
        # segredos: vazio = fica o que estava; "apagar" = sem segredo
        for campo, apagar in (("password", "apagar_senha"), ("client_secret", "apagar_segredo")):
            novo = str(d.get(campo) or "")
            if novo:
                no[campo] = novo
            elif d.get(apagar) or antes is None or antes.get("kind") != "dicomweb":
                no[campo] = ""
        return no, antes
    host = _texto(d, "host", 200)
    if not host:
        raise ValueError("Preencha nome e endereço.")
    retrieve = str(d.get("retrieve") or "get")
    destino = _texto(d, "move_destination", 16)
    no = {**comum, "kind": "dimse", "ae_title": _ae(str(d.get("ae_title") or "")), "host": host,
          "port": _inteiro(d.get("port"), 104, 1, 65535), "base_url": "", "username": "", "password": "",
          "auth": "basic", "token_url": "", "client_id": "", "client_secret": "", "scope": "",
          "retrieve": retrieve if retrieve in ("get", "move") else "get",
          "move_destination": _ae(destino, "Destino do C-MOVE") if destino else ""}
    return no, antes


def _nos_mudaram(c) -> None:
    net = getattr(c, "net", None)
    if net is not None:
        try:
            net.refresh_acl()
        except Exception:  # noqa: BLE001
            log.exception("refresh_acl")


def no_gravar(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    no, antes = _no_da_tela(c, d)
    if antes is not None:
        no["id"] = antes["id"]
    nid = c.repo.save_node(no)
    _nos_mudaram(c)
    _registrar(c, s, "config", _fez(antes, "o nó DICOM ", no["name"]), host)
    return {"ok": True, "id": nid, "mensagem": f"Nó {no['name']} gravado."}


def no_excluir(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    n = next((x for x in _todos_os_nos(c) if x["id"] == d.get("id")), None)
    if n is None:
        raise LookupError("nó desconhecido")
    c.repo.delete_node(n["id"])
    _nos_mudaram(c)
    _registrar(c, s, "config", f"excluiu o nó DICOM {n['name']}", host)
    return {"ok": True, "mensagem": f"Nó {n['name']} excluído."}


def no_testar(c, s, d: dict) -> dict:
    """Testa o que está na tela, gravado ou não (C-ECHO; no DICOMweb, uma consulta mínima)."""
    _admin(s)
    net = getattr(c, "net", None)
    if net is None:
        raise RuntimeError("este servidor não tem a rede DICOM ligada")
    try:
        no, antes = _no_da_tela(c, d)
    except ValueError as e:
        return {"ok": False, "mensagem": str(e), "ms": 0}
    if antes is not None:
        no = {**antes, **no}
    no.setdefault("id", None)
    ident = None
    if d.get("identidade"):
        ident = next((i for i in c.repo.identities(todos=True) if i["id"] == d.get("identidade")), None)
    if no["kind"] == "dicomweb":
        from ipe.network import oauth
        oauth.TOKENS.esquecer({"auth": no["auth"], "token_url": no["token_url"], "client_id": no["client_id"],
                               "user": no["username"]})
    t0 = time.perf_counter()
    try:
        r = net.cliente(no).echo(net.target(no, ident))
        ok, msg = (bool(r[0]), str(r[1])) if isinstance(r, tuple) else (True, "ok")
    except Exception as e:  # noqa: BLE001
        ok, msg = False, str(e)
    ms = round((time.perf_counter() - t0) * 1000)
    return {"ok": ok, "ms": ms, "mensagem": f"Responde em {ms} ms." if ok else f"Sem resposta: {msg}"}


def identidade_gravar(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    iid = d.get("id") or None
    antes = next((i for i in c.repo.identities(todos=True) if i["id"] == iid), None) if iid else None
    if iid and antes is None:
        raise LookupError("identidade desconhecida")
    nome = _texto(d, "name", 80)
    if not nome:
        raise ValueError("Preencha o nome.")
    destino = _texto(d, "move_destination", 16)
    conhecidos = {n["id"] for n in _todos_os_nos(c)}
    dados = {"name": nome, "ae_title": _ae(str(d.get("ae_title") or "")),
             "move_destination": _ae(destino, "Destino do C-MOVE") if destino else "",
             "allowed_nodes": ",".join(str(int(x)) for x in (d.get("allowed_nodes") or []) if x in conhecidos),
             "note": _texto(d, "note", 200)}
    if antes is not None:
        dados["id"] = antes["id"]
    c.repo.save_identity(dados)
    _nos_mudaram(c)
    _registrar(c, s, "config", _fez(antes, "a identidade ", nome) + " (" + dados["ae_title"] + ")", host)
    return {"ok": True, "mensagem": f"Identidade {nome} gravada."}


def identidade_excluir(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    i = next((x for x in c.repo.identities(todos=True) if x["id"] == d.get("id")), None)
    if i is None:
        raise LookupError("identidade desconhecida")
    c.repo.delete_identity(i["id"])
    _nos_mudaram(c)
    _registrar(c, s, "config", f"excluiu a identidade {i['name']}", host)
    return {"ok": True, "mensagem": f"Identidade {i['name']} excluída."}


# ====================================================================== impressoras DICOM
def _impressoras(c) -> list[dict]:
    return [dict(p) for p in (_settings(c).get(CHAVE_IMPRESSORAS, []) or []) if isinstance(p, dict)]


def _destinos_que_usam(c, nome: str) -> list[str]:
    from ipe.printing import dispatch as D
    try:
        return [x.name for x in D.all_destinations(_settings(c)) if x.kind == "dicom" and x.dicom_printer == nome]
    except Exception:  # noqa: BLE001
        return []


def impressoras(c, s) -> dict:
    _admin(s)
    from ipe.printing import dicom_print as DP
    net = getattr(c, "net", None)
    lista = []
    for p in _impressoras(c):
        cfg = DP.PrinterConfig.from_dict(p)
        lista.append({"name": cfg.name, "ae_title": cfg.ae_title, "host": cfg.host, "port": int(cfg.port),
                      "calling_ae": cfg.calling_ae, "film_size": cfg.film_size, "medium": cfg.medium,
                      "destination": cfg.destination, "magnification": cfg.magnification, "copies": int(cfg.copies),
                      "dpi": int(cfg.dpi), "color": bool(cfg.color),
                      "compartilhar_clientes": bool(cfg.compartilhar_clientes),
                      "usada_em": _destinos_que_usam(c, cfg.name)})
    return {"impressoras": lista, "tamanhos": list(DP.FILM_SIZES), "midias": list(DP.MEDIUMS),
            "destinos": list(DP.DESTINATIONS), "ampliacoes": list(DP.MAGNIFICATIONS),
            "ae_local": getattr(net, "local_ae", "") if net is not None else ""}


def _impressora_da_tela(d: dict):
    from ipe.printing import dicom_print as DP
    nome = _texto(d, "name", 80)
    if not nome:
        raise ValueError("Preencha o nome.")
    anfitriao = _texto(d, "host", 200)
    if not anfitriao or not str(d.get("ae_title") or "").strip():
        raise ValueError("Preencha o AE e o IP da impressora.")
    origem = _texto(d, "calling_ae", 16)

    def de(lista, k, padrao):
        v = str(d.get(k) or "")
        return v if v in lista else padrao
    return DP.PrinterConfig(
        name=nome, ae_title=_ae(str(d.get("ae_title") or ""), "AE da impressora"), host=anfitriao,
        port=_inteiro(d.get("port"), 104, 1, 65535), calling_ae=_ae(origem, "AE de origem") if origem else "",
        film_size=de(DP.FILM_SIZES, "film_size", ""), medium=de(DP.MEDIUMS, "medium", "BLUE FILM"),
        destination=de(DP.DESTINATIONS, "destination", "MAGAZINE"),
        magnification=de(DP.MAGNIFICATIONS, "magnification", "CUBIC"), copies=_inteiro(d.get("copies"), 1, 1, 20),
        dpi=_inteiro(d.get("dpi"), 150, 72, 600), color=bool(d.get("color")),
        compartilhar_clientes=bool(d.get("compartilhar_clientes")))


def impressora_gravar(c, s, d: dict, host: str = "") -> dict:
    """`original` = o nome que ela tinha (vazio = nova). Trocar o nome acompanha os destinos de impressão."""
    _admin(s)
    st = _settings(c)
    cfg = _impressora_da_tela(d)
    lista = _impressoras(c)
    original = str(d.get("original") or "")
    k = next((i for i, p in enumerate(lista) if p.get("name") == original), -1) if original else -1
    if original and k < 0:
        raise LookupError("impressora desconhecida")
    if any(p.get("name", "").strip().lower() == cfg.name.lower() for i, p in enumerate(lista) if i != k):
        raise ValueError(f"Já existe a impressora {cfg.name}.")
    novo = cfg.__dict__.copy()
    if k >= 0:
        novo = {**lista[k], **{x: v for x, v in novo.items() if x not in ("min_density", "max_density")}}  # as densidades (a tela não mostra) ficam
        lista[k] = novo
    else:
        lista.append(novo)
    st.set(CHAVE_IMPRESSORAS, lista)
    if original and original != cfg.name:
        from ipe.printing import dispatch as D
        dests = D.all_destinations(st)
        mudou = False
        for x in dests:
            if x.kind == "dicom" and x.dicom_printer == original:
                x.dicom_printer, mudou = cfg.name, True
        if mudou:
            D.save_destinations(st, dests)
    st.save()
    _registrar(c, s, "config", _fez(None if k < 0 else cfg, "a impressora DICOM ", cfg.name), host)
    return {"ok": True, "mensagem": f"Impressora {cfg.name} gravada."}


def impressora_excluir(c, s, d: dict, host: str = "") -> dict:
    _admin(s)
    st = _settings(c)
    nome = str(d.get("name") or "")
    lista = _impressoras(c)
    if not any(p.get("name") == nome for p in lista):
        raise LookupError("impressora desconhecida")
    usam = _destinos_que_usam(c, nome)
    if usam and not d.get("confirmar"):
        return {"ok": False, "usada_em": usam,
                "mensagem": f"A impressora {nome} é usada nos destinos de impressão: {', '.join(usam)}."}
    st.set(CHAVE_IMPRESSORAS, [p for p in lista if p.get("name") != nome])
    st.save()
    _registrar(c, s, "config", f"excluiu a impressora DICOM {nome}", host)
    return {"ok": True, "mensagem": f"Impressora {nome} excluída."}


def impressora_testar(c, s, d: dict) -> dict:
    _admin(s)
    from ipe.printing import dicom_print as DP
    try:
        cfg = _impressora_da_tela({**d, "name": d.get("name") or "teste"})
    except ValueError as e:
        return {"ok": False, "mensagem": str(e)}
    net = getattr(c, "net", None)
    try:
        return {"ok": True, "mensagem": DP.printer_status(cfg, getattr(net, "local_ae", "") if net is not None else "",
                                                          timeout=10)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mensagem": f"Sem resposta: {e}"}


# ====================================================================== automações de IA
_DICA_EXAME = ("Pedaços da descrição do exame, separados por |, sem diferença de acento ou maiúscula. Vale para o "
               "automático.")
_DICA_SERIE = ("Séries em ordem de preferência, separadas por |: vale a primeira que aparecer na descrição da série; "
               "entre iguais, a de mais cortes.")


def _campo(k, tipo, rotulo, valor, dica="", **mais) -> dict:
    return {"k": k, "tipo": tipo, "rotulo": rotulo, "valor": valor, "dica": dica, **mais}


def _perfil(mod, cfg, auto_rotulo: str, mods: tuple = (), mr: bool = False, vazio: str = "", minimo: int = 0) -> list[dict]:
    """Os campos que todas as ferramentas de TC/RM têm: automático, exame, modalidades, séries, filtros."""
    campos = [_campo(mod.CHAVE_AUTO, "bool", auto_rotulo, bool(cfg(mod.CHAVE_AUTO))),
              _campo(mod.CHAVE_EXAME_CONTEM, "texto", "Descrição do exame contém:", str(cfg(mod.CHAVE_EXAME_CONTEM) or ""),
                     _DICA_EXAME, vazio=vazio)]
    if mods:
        campos.append(_campo(mod.CHAVE_MODALIDADES, "lista", "Modalidades:",
                             [m.upper() for m in (cfg(mod.CHAVE_MODALIDADES) or [])],
                             opcoes=[{"k": m, "nome": {"CT": "TC", "MR": "RM"}[m]} for m in mods]))
    ct = _campo(mod.CHAVE_PRIOR_CT, "texto", "Série preferida na TC:", str(cfg(mod.CHAVE_PRIOR_CT) or ""), _DICA_SERIE)
    if mr:
        rm = _campo(mod.CHAVE_PRIOR_MR, "texto", "Série preferida na RM:", str(cfg(mod.CHAVE_PRIOR_MR) or ""), _DICA_SERIE)
        campos += [rm, ct] if mods and mods[0] == "MR" else [ct, rm]
    else:
        campos.append(ct)
    minimo = minimo or int(getattr(mod, "MIN_CORTES", 20))
    campos += [_campo(mod.CHAVE_ESPESSURA, "numero", "Espessura da série até (mm; 0 = sem limite):",
                      float(cfg(mod.CHAVE_ESPESSURA) or 0), min=0, max=20, passo=0.25),
               _campo(mod.CHAVE_MIN_CORTES, "inteiro", "Mínimo de cortes da série:",
                      int(cfg(mod.CHAVE_MIN_CORTES) or minimo), min=minimo, max=2000)]
    return campos


def _destinos(chave, valor, dica="A série de resultado vai para os nós marcados depois de feita.") -> dict:
    return _campo(chave, "nos", "Depois de fazer, enviar para:",
                  [int(i) for i in (valor or []) if str(i).lstrip("-").isdigit()], dica)


def _ferramentas(c) -> list[dict]:
    """Cada ferramenta de Preferências ▸ CAD/IA, com os campos na ordem da janela do Ipê de mesa."""
    from ipe.ai import cefalometria as CF
    from ipe.ai import coluna as COL
    from ipe.ai import ferramentas as FE
    from ipe.ai import linfonodos as LN
    from ipe.ai import neuro as NE
    from ipe.ai import totalseg as TS
    from ipe.automation import implante as IMP
    from ipe.automation import mama_auto as MA
    st = _settings(c)
    out = []

    def cfg_de(mod):
        return lambda k: mod.config(st, k)

    g = cfg_de(TS)
    escolhidas = set(g(TS.CHAVE_ESTRUTURAS) or TS.PADRAO)
    out.append({"id": "seg", "nome": "Segmentação abdominal", "titulo": "Segmentação abdominal (TotalSegmentator)",
                "auto": TS.CHAVE_AUTO, "campos": [
                    *_perfil(TS, g, "Segmentar automaticamente quando o exame chegar", ("CT", "MR"), True,
                             "vazio = qualquer TC/RM; ex.: ABDOME|FIGADO|RENAL", minimo=20),
                    _campo(TS.CHAVE_ESTRUTURAS, "lista", "Estruturas:", [n for n, *_r in TS.ESTRUTURAS if n in escolhidas],
                           opcoes=[{"k": n, "nome": pt} for n, pt, *_r in TS.ESTRUTURAS], naovazio=True),
                    _campo(TS.CHAVE_RAPIDO, "bool", "Modo rápido na TC (3 mm; bem mais rápido em CPU)", bool(g(TS.CHAVE_RAPIDO))),
                    _campo(TS.CHAVE_COUINAUD, "bool", "Segmentos do fígado (Couinaud) — outro modelo, menos robusto",
                           bool(g(TS.CHAVE_COUINAUD))),
                    _destinos(TS.CHAVE_DESTINOS, g(TS.CHAVE_DESTINOS),
                              "A SEG e a tabela de volumes vão para os nós marcados depois de feitas.")]})
    g = cfg_de(COL)
    campos = _perfil(COL, g, "Identificar automaticamente quando o exame chegar", ("CT", "MR"), True,
                     "vazio = qualquer TC/RM; ex.: COLUNA|LOMBAR|CERVICAL")
    if COL.MEDIR_DISPONIVEL:
        campos += [_campo(COL.CHAVE_MEDIR, "bool", "Medir os discos (altura e volume) e os corpos vertebrais (altura e "
                          "perda de altura) — tabelas no exame", bool(g(COL.CHAVE_MEDIR))),
                   _campo(COL.CHAVE_SEQUENCIAS, "escolha", "Medir na RM em:", 2 if int(g(COL.CHAVE_SEQUENCIAS) or 1) >= 2 else 1,
                          opcoes=[{"k": 1, "nome": "Uma sagital (mais rápido)"},
                                  {"k": 2, "nome": "Duas sagitais, conferindo uma com a outra"}])]
    campos.append(_destinos(COL.CHAVE_DESTINOS, g(COL.CHAVE_DESTINOS)))
    out.append({"id": "coluna", "nome": "Níveis da coluna", "auto": COL.CHAVE_AUTO,
                "titulo": "Níveis da coluna — vértebras e discos (TotalSegmentator)", "campos": campos})
    g = cfg_de(IMP)
    out.append({"id": "implante", "nome": "Implante de silicone", "titulo": "Implante de silicone (mamografia)",
                "auto": IMP.CHAVE, "campos": [
                    _campo(IMP.CHAVE, "bool", "Corrigir automaticamente quando a mamografia chegar", bool(g(IMP.CHAVE))),
                    _campo(IMP.CHAVE_ANTERIORES, "bool", "Também nos exames anteriores baixados para comparação",
                           bool(g(IMP.CHAVE_ANTERIORES))),
                    _campo(IMP.CHAVE_SO_COM_MARCA, "escolha", "Procurar o implante:", bool(g(IMP.CHAVE_SO_COM_MARCA)),
                           opcoes=[{"k": False, "nome": "quando o aparelho marca implante ou não diz nada (procura pela imagem)"},
                                   {"k": True, "nome": "só quando o aparelho marca implante (BreastImplantPresent = YES)"}]),
                    _destinos(IMP.CHAVE_DESTINOS, g(IMP.CHAVE_DESTINOS))]})
    out.append({"id": "mama", "nome": "Densidade e calcificações (mama)", "auto": MA.CHAVE,
                "titulo": "Densidade mamária e calcificações vasculares (mamografia)",
                "explicacao": "A densidade (rede da NYU) e as calcificações vasculares (SCU-Net) são medidas em segundo "
                              "plano, um exame por vez, e ficam esperando a confirmação de quem lê o exame.",
                "campos": [
                    _campo(MA.CHAVE, "bool", "Medir automaticamente quando a mamografia chegar (rede, PACS, importação)",
                           bool(MA._cfg(st, MA.CHAVE, True))),
                    _campo(MA.CHAVE_ABRIR, "bool", "Ao abrir a mamografia, pedir a confirmação do que foi medido",
                           MA.confirmar_ao_abrir(st)),
                    _campo(MA.CHAVE_SEM_CONFERIR, "bool", "Aceitar a medida sem conferência: gravar o SR logo depois "
                           "de medir", MA.sem_conferir(st), "Vale para a mamografia que chega. Ao abrir o exame ainda "
                           "dá para confirmar ou corrigir: o SR é refeito (e reenviado)."),
                    _campo(MA.CHAVE_DESTINOS, "nos", "Depois de gravar o SR, enviar para:",
                           [int(i) for i in MA.destinos(st) if str(i).lstrip("-").isdigit()],
                           "O SR, as imagens com as calcificações marcadas e o resumo vão para os nós marcados.")]})
    g = cfg_de(CF)
    out.append({"id": "cefalo", "nome": "Cefalometria do cavum", "auto": CF.CHAVE_AUTO,
                "titulo": "Cefalometria do cavum — via aérea, palato, língua e hioide (TotalSegmentator)",
                "campos": [*_perfil(CF, g, "Fazer automaticamente quando o exame chegar (só TC)",
                                    vazio="vazio = qualquer TC; ex.: CAVUM|RINOFARINGE|APNEIA"),
                           _destinos(CF.CHAVE_DESTINOS, g(CF.CHAVE_DESTINOS))]})
    g = cfg_de(NE)
    out.append({"id": "neuro", "nome": "Índices do crânio", "auto": NE.CHAVE_AUTO,
                "titulo": "Índices do crânio — Evans, 3º ventrículo, ângulo calosal e volumes (SynthSeg)",
                "campos": [*_perfil(NE, g, "Fazer automaticamente quando o exame chegar", ("MR", "CT"), True,
                                    "vazio = qualquer RM/TC; ex.: CRANIO|ENCEFALO|PARKINSON"),
                           _destinos(NE.CHAVE_DESTINOS, g(NE.CHAVE_DESTINOS))]})
    g = cfg_de(LN)
    out.append({"id": "linfonodos", "nome": "Níveis linfonodais", "auto": LN.CHAVE_AUTO,
                "titulo": "Níveis linfonodais cervicais — mapa I a VII na TC (TotalSegmentator)",
                "campos": [*_perfil(LN, g, "Fazer automaticamente quando o exame chegar (só TC)",
                                    vazio="vazio = qualquer TC; ex.: PESCOCO|CERVICAL|LARINGE"),
                           _destinos(LN.CHAVE_DESTINOS, g(LN.CHAVE_DESTINOS))]})
    for tipo in FE.tipos():
        try:
            mod = FE.modulo(tipo)
            g = cfg_de(mod)
            campos = _perfil(mod, g, "Fazer automaticamente quando o exame chegar (só TC)", vazio="vazio = qualquer TC")
            for chave, rotulo, lo, hi, sufixo, dica in getattr(mod, "OPCOES", ()):
                campos.append(_campo(chave, "numero", rotulo, float(g(chave) or 0), dica, min=lo, max=hi, passo=0.1,
                                     sufixo=sufixo.strip()))
            for chave, rotulo, dica in getattr(mod, "CAIXAS", ()):
                campos.append(_campo(chave, "bool", rotulo, bool(g(chave)), dica))
            campos.append(_destinos(mod.CHAVE_DESTINOS, g(mod.CHAVE_DESTINOS)))
            out.append({"id": tipo, "nome": mod.NOME_CADIA, "titulo": mod.TITULO_CADIA, "auto": mod.CHAVE_AUTO,
                        "explicacao": mod.EXPLICACAO_CADIA, "campos": campos})
        except Exception:  # noqa: BLE001 - uma ferramenta com defeito não esconde as outras
            log.exception("CAD/IA: %s", tipo)
    return out


def _nos_de_envio(c) -> list[dict]:
    return [{"id": n["id"], "nome": f"{n.get('name', '')}  ({n.get('ae_title', '')})" if n.get("ae_title") else n.get("name", "")}
            for n in c.repo.nodes(only_active=True, todos=True) if n.get("kind") != "servidor"]


def ia(c, s) -> dict:
    _admin(s)
    st = _settings(c)
    fs = _ferramentas(c)
    for f in fs:
        f["ligada"] = bool(next((x["valor"] for x in f["campos"] if x["k"] == f["auto"]), False))
    return {"ler_antes": bool(st.get("cad.ler_antes", False)), "ferramentas": fs, "nos": _nos_de_envio(c),
            "nota": "Cada ferramenta de CAD/IA com as suas configurações: se roda sozinha quando o exame chega (pela "
                    "rede ou importado), como roda e para onde vai o resultado. Quem roda é o servidor. Não destinado "
                    "a uso diagnóstico."}


def _valor(campo: dict, v, nos_ok: set):
    tipo = campo["tipo"]
    if tipo == "bool":
        return bool(v)
    if tipo == "texto":
        return str(v or "").strip()[:500]
    if tipo in ("numero", "inteiro"):
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"Valor inválido em “{campo['rotulo'].rstrip(':')}”.") from None
        n = max(float(campo.get("min", n)), min(float(campo.get("max", n)), n))
        return int(round(n)) if tipo == "inteiro" else round(n, 2)
    if tipo == "nos":
        return [int(i) for i in (v or []) if isinstance(i, int) and i in nos_ok]
    opcoes = [o["k"] for o in campo.get("opcoes", [])]
    if tipo == "lista":
        marcados = set(v or [])
        lista = [k for k in opcoes if k in marcados]
        if campo.get("naovazio") and not lista:
            raise ValueError(f"Marque pelo menos uma opção em “{campo['rotulo'].rstrip(':')}”.")
        return lista
    if tipo == "escolha":
        if v not in opcoes:
            raise ValueError(f"Valor inválido em “{campo['rotulo'].rstrip(':')}”.")
        return v
    raise ValueError("campo desconhecido")


def ia_gravar(c, s, d: dict, host: str = "") -> dict:
    """Grava só as chaves que a tela conhece (as das ferramentas); o resto do pedido é ignorado."""
    _admin(s)
    st = _settings(c)
    valores = d.get("valores")
    if not isinstance(valores, dict):
        raise ValueError("Faltaram os valores.")
    nos_ok = {n["id"] for n in _nos_de_envio(c)}
    mudou, ligou = [], []
    for f in _ferramentas(c):
        for campo in f["campos"]:
            k = campo["k"]
            if k not in valores:
                continue
            novo = _valor(campo, valores[k], nos_ok)
            if novo != campo["valor"]:
                st.set(k, novo)
                if f["nome"] not in mudou:
                    mudou.append(f["nome"])
                if k == f["auto"]:
                    ligou.append(f"{f['nome']}: {'automático' if novo else 'só à mão'}")
    if "cad.ler_antes" in valores and bool(valores["cad.ler_antes"]) != bool(st.get("cad.ler_antes", False)):
        st.set("cad.ler_antes", bool(valores["cad.ler_antes"]))
        mudou.append("ler antes")
    if mudou:
        st.save()
        _registrar(c, s, "config", "alterou o CAD/IA: " + (", ".join(ligou) if ligou else ", ".join(mudou)), host)
    return {"ok": True, "mudou": len(mudou), "mensagem": "Automações de IA gravadas." if mudou else "Nada mudou."}


# ====================================================================== registro de acesso
def registro(c, s, q: dict) -> dict:
    _admin(s)

    def um(k):
        return str((q.get(k) or [""])[0]).strip()
    dias = _inteiro(um("dias") or "7", 7, 0, 3650)
    desde = None if dias == 0 else (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                                    - timedelta(days=dias - 1))
    linhas = c.repo.access_log(limit=1000, user=um("usuario"), action=um("acao"), text=um("texto"), since=desde)
    return {
        "linhas": [{"quando": a["at"].strftime("%d/%m/%Y %H:%M:%S") if isinstance(a["at"], datetime) else "",
                    "usuario": a["user"] or "", "acao": a["action"] or "", "detalhe": a["detail"] or "",
                    "study_uid": a["study_uid"], "maquina": a["host"]} for a in linhas],
        "cheio": len(linhas) >= 1000,
        "usuarios": sorted({u["username"] for u in c.repo.users()}),
        "acoes": sorted({a["action"] for a in linhas if a["action"]}),
        "periodos": [{"k": k, "nome": v} for k, v in PERIODOS_REGISTRO],
    }


# ====================================================================== no idioma do navegador
#: os campos que são texto do programa (nunca nomes de usuários, nós, impressoras ou o que a pessoa escreveu)
_TRADUZ = {"mensagem", "papel", "rotulo", "dica", "titulo", "explicacao", "vazio", "nota"}
_NOMES_EM = {"papeis", "permissoes", "auths", "opcoes", "periodos", "ferramentas"}


def traduzir(r, lang: str, dentro: str = ""):
    from ipe.central.gestao_web import _t
    from ipe.core import i18n as I
    lang = I.normalize(lang or "")
    if not lang or lang == I.BASE_LANG:
        return r
    if isinstance(r, list):
        return [traduzir(x, lang, dentro) for x in r]
    if not isinstance(r, dict):
        return r
    out = {}
    for k, v in r.items():
        if isinstance(v, str) and (k in _TRADUZ or (k == "nome" and dentro in _NOMES_EM)):
            out[k] = _t(v, lang)
        elif isinstance(v, (dict, list)) and k not in ("nos", "identidades", "impressoras", "linhas", "perfis"):
            out[k] = traduzir(v, lang, k)
        else:
            out[k] = v
    return out


def _mensagem(e: Exception, lang: str) -> str:
    from ipe.central.gestao_web import _t
    from ipe.core import i18n as I
    lang = I.normalize(lang or "")
    texto = str(e).strip("'") if isinstance(e, LookupError) else str(e)
    return texto if not lang or lang == I.BASE_LANG else _t(texto, lang)


GET = {"usuarios": usuarios, "nos": nos, "impressoras": impressoras, "ia": ia}
POST = {"usuario": usuario_gravar, "usuario_senha": usuario_senha, "usuario_excluir": usuario_excluir,
        "perfis": perfis_gravar, "minha_senha": minha_senha, "no": no_gravar, "no_excluir": no_excluir,
        "identidade": identidade_gravar, "identidade_excluir": identidade_excluir,
        "impressora": impressora_gravar, "impressora_excluir": impressora_excluir, "ia": ia_gravar}
POST_SEM_REGISTRO = {"no_testar": no_testar, "impressora_testar": impressora_testar}


def rota(c, s, method: str, acao: str, query: dict, corpo: dict, host: str = "") -> dict:
    """A resposta (e o erro) vai no idioma do navegador (`?lang=en|es`); sem ele, em português."""
    lang = (query.get("lang") or [""])[0]
    try:
        if method == "GET" and acao == "registro":
            r = registro(c, s, query)
        elif method == "GET" and acao in GET:
            r = GET[acao](c, s)
        elif method == "POST" and acao in POST:
            r = POST[acao](c, s, corpo, host)
        elif method == "POST" and acao in POST_SEM_REGISTRO:
            r = POST_SEM_REGISTRO[acao](c, s, corpo)
        else:
            raise LookupError("rota")
    except (PermissionError, LookupError, ValueError, RuntimeError) as e:
        raise type(e)(_mensagem(e, lang)) from None
    return traduzir(r, lang)
