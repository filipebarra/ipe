"""Perfis por grupo ou computador, mandados pelo servidor (0.99.56, onda B2 do plano ViewerHub/Eden).

Um **perfil** é um conjunto de preferências (as mesmas chaves do settings.json: ``viewer.…``, ``shortcuts``,
``browser.columns``, ``monitors``…) que vale para os computadores e as pessoas que ele escolhe:

- **computadores**: nomes, com coringa (``SALA-MAMO*``, ``TC-0?``); vazio = qualquer um;
- **usuários** e **perfis de acesso** (médico, técnico…): vazio = qualquer um;
- **canal de atualização** (onda B1): ``estavel`` ou ``teste`` — quem cai num perfil "teste" recebe primeiro
  a versão nova que o administrador publicou no servidor.

Ao entrar, o programa junta os perfis que casam (na ordem da lista: o de baixo ganha) e põe o resultado como
uma camada entre o computador e a pessoa: o perfil manda sobre o que vem do computador, e a pessoa ainda pode
ter o seu — a não ser nas chaves **forçadas**, que ninguém troca.

Os perfis moram nas configurações centrais (``AppSetting``, chave ``perfis_estacao``): no modo cliente, no
servidor central; num computador com várias pessoas, no banco dele.
"""
from __future__ import annotations

import fnmatch
import json
import socket

CHAVE = "perfis_estacao"
CANAIS = {"estavel": "Estável", "teste": "Teste (recebe primeiro)"}
#: grupos que dá para capturar do computador (as listas com dono — protocolos, modelos — já são do serviço
#: pelas configurações em três níveis, e ficam de fora)
GRUPOS = {
    "viewer": "Visualizador (mouse, texto sobre a imagem, sincronia, janelas…)",
    "shortcuts": "Atalhos de teclado",
    "browser": "Banco de dados (colunas, painéis)",
    "worklist": "Lista de trabalho (minhas subespecialidades)",
    "monitors": "Monitores (papel e layout de cada um)",
    "dyn": "Dinâmica da mama",
    "nm": "Medicina nuclear",
    "cad": "CAD/IA (o que roda sozinho)",
    "export": "Exportação",
    "meeting": "Modo reunião",
    "performance": "Desempenho",
    "language": "Idioma",
}


def nome_do_computador() -> str:
    try:
        return socket.gethostname().split(".")[0].upper()
    except Exception:  # noqa: BLE001
        return ""


def _lista(txt) -> list[str]:
    if isinstance(txt, (list, tuple, set)):
        return [str(x).strip() for x in txt if str(x).strip()]
    return [x.strip() for x in str(txt or "").replace(";", ",").split(",") if x.strip()]


def casa(perfil: dict, computador: str, usuario: str, papel: str) -> bool:
    comps = _lista(perfil.get("computadores"))
    if comps and not any(fnmatch.fnmatch((computador or "").upper(), c.upper()) for c in comps):
        return False
    users = [u.lower() for u in _lista(perfil.get("usuarios"))]
    if users and (usuario or "").lower() not in users:
        return False
    papeis = [p.lower() for p in _lista(perfil.get("papeis"))]
    if papeis and (papel or "").lower() not in papeis:
        return False
    return bool(perfil.get("ativo", True))


def _set(node: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    for p in parts[:-1]:
        nxt = node.get(p)
        if not isinstance(nxt, dict):
            nxt = node[p] = {}
        node = nxt
    node[parts[-1]] = value


def juntar(perfis: list[dict], computador: str, usuario: str, papel: str) -> dict:
    """{"nomes", "valores" (aninhado), "forcados" (chaves com ponto), "canal"} dos perfis que casam."""
    out = {"nomes": [], "valores": {}, "forcados": [], "canal": "estavel"}
    for p in perfis or []:
        if not isinstance(p, dict) or not casa(p, computador, usuario, papel):
            continue
        out["nomes"].append(str(p.get("nome") or "?"))
        for chave, valor in (p.get("valores") or {}).items():
            _set(out["valores"], chave, valor)
        for f in p.get("forcados") or []:
            if f not in out["forcados"]:
                out["forcados"].append(f)
        if p.get("canal") in CANAIS:
            out["canal"] = p["canal"]
    return out


def capturar(settings, grupos: list[str]) -> dict[str, object]:
    """Os valores deste computador (e de quem está logado) dos grupos escolhidos: {chave: valor}."""
    out = {}
    for g in grupos:
        v = settings.get(g, None)
        if v is not None:
            out[g] = json.loads(json.dumps(v))
    return out


def texto_do_valor(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def valor_do_texto(t: str):
    t = (t or "").strip()
    try:
        return json.loads(t)
    except ValueError:
        return t
