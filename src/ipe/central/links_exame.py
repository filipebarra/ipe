"""0.100.108: link de exame do Ipê Web — abre **um** exame direto no visualizador, sem senha.

Pedido dele (23/11/2026): *"Existe um link externo para o Ipê Web para abrir somente o exame direto no viewer, sem
ter que pedir senha? Sem acesso a BD? Com acesso a IA, envio PACS, adicionar PDF/imagem?"* — e escolheu que o link é
criado dentro do Ipê (botão direito no exame ▸ "Criar link do exame…").

- O link é `https://<servidor>/web/#/link/<token>`. O token é aleatório (256 bits), único por link; o servidor guarda
  só o SHA-256 dele. Vai depois do "#": não chega aos registros do servidor; o Ipê Web o tira da barra de endereço.
- Trocado por uma sessão própria (`link-<id>`): só aquele exame, sem lista, busca, banco, laudo, cadastros…
- O que o link libera, escolhido na criação: "ia" (pedir e revisar IA), "enviar" (ao PACS e outros nós), "anexar"
  (PDF/imagem). Ver o exame e as medidas sempre.
- Validade (horas), revogação, contagem de usos e auditoria (criado, usado, revogado, negado).
- `portao()`: lista fechada de rotas permitidas e todo UID que aparecer no pedido (caminho, parâmetros, corpo) tem de
  ser o exame do link ou uma série/imagem dele.

Sem Qt.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from urllib.parse import parse_qs

CHAVE = "web.links_exame"
PERMISSOES = {"ia": ("Rodar e revisar IA", {"ai"}),
              "enviar": ("Enviar ao PACS e a outros nós", {"send"}),
              "anexar": ("Anexar PDF e imagens", {"import"})}
VALIDADES_H = (24, 72, 168, 720)                     # 1, 3, 7 e 30 dias
_trava = threading.Lock()
_UID = re.compile(r"^\d+(?:\.\d+){3,}$")

#: rotas que todo link usa (ver o exame); o resto, por permissão
_VER = ("/api/web/config", "/api/web/abriu", "/api/web/abertura", "/api/logout", "/api/web/medidas",
        "/api/web/medidas/apagar", "/api/web/overlays", "/api/web/seg", "/api/web/series_ia", "/api/web/suv",
        "/api/web/dinamica", "/api/web/dinamica_movimento", "/api/web/mamografia", "/api/web/documentos",
        "/api/web/documento", "/api/web/achados", "/api/web/densidade", "/api/web/calcvasc",
        "/api/web/calcvasc/previa", "/api/web/birads_texto")
_POR_PERMISSAO = {
    "ia": ("/api/web/ia", "/api/web/ia/pedir", "/api/web/ia/tarefas", "/api/web/ia/cancelar",
           "/api/web/achados/revisar", "/api/web/densidade", "/api/web/calcvasc/medir", "/api/web/calcvasc/confirmar"),
    "enviar": ("/api/web/destinos", "/api/web/enviar", "/api/web/envios", "/api/web/envios/cancelar"),
    "anexar": ("/api/web/anexos",),
}
#: só leitura sem o "ia": nestas rotas o POST é revisão/medida da IA
_SO_LEITURA_SEM_IA = ("/api/web/densidade", "/api/web/achados")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _todos(repo) -> dict:
    v = repo.get_app_setting(CHAVE, None)
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            v = None
    return dict(v) if isinstance(v, dict) else {}


def _gravar(repo, d: dict) -> None:
    repo.set_app_setting(CHAVE, d)


def criar(repo, study_uid: str, perms, horas: float, rotulo: str = "", criado_por: str = "",
          ips: list[str] | None = None) -> tuple[str, dict]:
    """(token, link). O token só existe aqui: o servidor guarda o hash."""
    if not study_uid or repo.study_info(study_uid) is None:
        raise ValueError("exame não encontrado neste servidor")
    perms = sorted({p for p in (perms or []) if p in PERMISSOES})
    horas = max(1.0, min(float(horas or 24), 24 * 365))
    token = secrets.token_urlsafe(32)
    lid = secrets.token_hex(4)
    agora = time.time()
    link = {"id": lid, "hash": _hash(token), "study_uid": study_uid, "perms": perms, "rotulo": str(rotulo or "")[:120],
            "criado_por": criado_por, "criado_em": agora, "expira": agora + horas * 3600, "revogado": False,
            "usos": 0, "ultimo_uso": 0, "ips": [str(x).strip() for x in (ips or []) if str(x).strip()]}
    with _trava:
        d = _todos(repo)
        for k in [k for k, x in d.items() if x.get("expira", 0) < agora - 30 * 86400]:   # limpa os vencidos há 30 d
            d.pop(k, None)
        d[lid] = link
        _gravar(repo, d)
    repo.audit("link_exame_criado", f"link {lid} ({', '.join(perms) or 'só ver'}; {horas:g} h) {rotulo}".strip(),
               user=criado_por, study_uid=study_uid)
    return token, publico(link)


def publico(link: dict) -> dict:
    """O link sem o hash, com "ativo"."""
    d = {k: v for k, v in link.items() if k != "hash"}
    d["ativo"] = ativo(link)
    return d


def ativo(link: dict | None) -> bool:
    return bool(link) and not link.get("revogado") and float(link.get("expira", 0)) > time.time()


def listar(repo, study_uid: str = "") -> list[dict]:
    out = [publico(x) for x in _todos(repo).values() if not study_uid or x.get("study_uid") == study_uid]
    return sorted(out, key=lambda x: -float(x.get("criado_em", 0)))


def revogar(repo, lid: str, quem: str = "") -> bool:
    with _trava:
        d = _todos(repo)
        x = d.get(lid)
        if x is None:
            return False
        x["revogado"] = True
        _gravar(repo, d)
    repo.audit("link_exame_revogado", f"link {lid}", user=quem, study_uid=x.get("study_uid", ""))
    return True


def por_id(repo, lid: str) -> dict | None:
    return _todos(repo).get(lid)


def usar(repo, token: str, ip: str = "") -> dict:
    """Confere o token (e o IP, se o link tiver lista) e conta o uso. ValueError se não vale."""
    h = _hash(str(token or ""))
    with _trava:
        d = _todos(repo)
        x = next((v for v in d.values() if secrets.compare_digest(v.get("hash", ""), h)), None)
        if x is None or not ativo(x):
            raise ValueError("link inválido, vencido ou revogado")
        if x.get("ips") and ip not in x["ips"]:
            raise PermissionError("este link não vale neste computador")
        x["usos"] = int(x.get("usos", 0)) + 1
        x["ultimo_uso"] = time.time()
        _gravar(repo, d)
    repo.audit("link_exame_usado", f"link {x['id']} ({x.get('rotulo', '')})", user=f"link-{x['id']}", host=ip,
               study_uid=x["study_uid"])
    return x


def sessao(link: dict):
    """A sessão do link: usuário próprio, só as permissões liberadas, presa ao exame."""
    from ipe.auth.session import UserSession
    perms = {"view"}
    for p in link.get("perms") or []:
        perms |= PERMISSOES.get(p, ("", set()))[1]
    s = UserSession(username=f"link-{link['id']}", full_name=link.get("rotulo") or "Link do exame", role="link",
                    user_id=None, perms=perms)
    s.so_exame = link["study_uid"]
    s.link_id = link["id"]
    s.link_perms = set(link.get("perms") or [])
    return s


# ------------------------------------------------------------------ o portão
_uids_do_exame: dict[str, tuple[float, set]] = {}


def _uids(repo, study_uid: str) -> set:
    """O exame, as séries e as imagens dele (guardado por 30 s: o exame pode estar crescendo)."""
    agora = time.monotonic()
    it = _uids_do_exame.get(study_uid)
    if it is not None and agora - it[0] < 30:
        return it[1]
    out = {study_uid}
    out.update(se.series_uid for se in repo.series_for_study(study_uid))
    try:
        out.update(repo.sop_uids_for_study(study_uid))
    except Exception:  # noqa: BLE001
        pass
    if len(_uids_do_exame) > 200:
        _uids_do_exame.clear()
    _uids_do_exame[study_uid] = (agora, out)
    return out


def _uids_em(obj, acc: list) -> None:
    if isinstance(obj, str):
        if 10 <= len(obj) <= 64 and _UID.match(obj):
            acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _uids_em(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _uids_em(v, acc)


def portao(repo, s, method: str, path: str, query: str, corpo: bytes) -> str | None:
    """None = pode; senão, o motivo do 403."""
    so = getattr(s, "so_exame", "")
    lp = getattr(s, "link_perms", set())
    if path.startswith("/dicomweb"):
        if method != "GET":
            return "o link só lê imagens"
        partes = [p for p in path.split("/") if p]
        if partes[1:2] != ["studies"]:
            return "fora do exame do link"
        if len(partes) == 2:                                    # QIDO de exames: só o do link
            q = parse_qs(query)
            if (q.get("StudyInstanceUID") or [""])[0] != so:
                return "o link não lista exames"
            return None
        uids = [p for p in partes[2:] if _UID.match(p)]
        if not uids or uids[0] != so:
            return "fora do exame do link"
        if any(u not in _uids(repo, so) for u in uids[1:]):
            return "fora do exame do link"
        return None
    permitidas = set(_VER)
    for p in lp:
        permitidas.update(_POR_PERMISSAO.get(p, ()))
    if path not in permitidas:
        return "o link deste exame não dá acesso a isto"
    if method == "POST" and path in _SO_LEITURA_SEM_IA and "ia" not in lp:
        return "o link não libera a revisão da IA"
    achados: list = []
    _uids_em({k: v for k, v in parse_qs(query).items()}, achados)
    if corpo:
        try:
            _uids_em(json.loads(corpo), achados)
        except ValueError:
            pass
    if achados and any(u != so and u not in _uids(repo, so) for u in achados):
        return "fora do exame do link"
    return None
