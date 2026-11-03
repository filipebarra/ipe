"""As listas de casos acompanham o exame entre este computador e o servidor central (0.99.36).

Fecha o plano do modo de uso. Até aqui, "Enviar ao servidor central" e "Copiar/Mover para este
computador" levavam as imagens e os dados do exame (laudo, medidas, anotações…), mas não as listas:
um caso da lista "Aula de mama" chegava ao servidor solto, sem a lista.

Agora quem leva exames leva também **as listas em que eles estão** (as que quem leva enxerga), com a
pasta, a descrição e os campos do caso (nome amigável, história, resposta, notas, tags, séries a
mostrar). No destino:

- a pasta e a lista são procuradas **pelo caminho de nomes** ("Ensino / Aula de mama"); se não
  existem, são criadas, com o mesmo dono e o mesmo "visível para" da origem quando quem leva pode
  (o servidor confere); senão, ficam pessoais de quem levou;
- o caso entra na lista se ainda não está; se já está, os campos vazios do destino são completados
  (nada que alguém escreveu lá é apagado);
- listas inteligentes não viajam com o exame: são um filtro, e o filtro roda sozinho no destino.

Sem Qt. Funciona com o `Repository` (banco deste computador), com o `ClientRepository` (servidor,
pelo cache) e com o `RemoteClient` puro (via `PeloServidor`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import partial

log = logging.getLogger(__name__)

CAMPOS = ("friendly_name", "clinical_summary", "hidden_diagnosis", "note", "tags", "show_series")


class PeloServidor:
    """Faz um RemoteClient parecer um repositório: `x.metodo(...)` vira `client.rpc("metodo", ...)`."""

    def __init__(self, client):
        self.client = client

    def __getattr__(self, nome: str):
        if nome.startswith("_"):
            raise AttributeError(nome)
        return partial(self.client.rpc, nome)


@dataclass
class Levadas:
    listas_novas: int = 0
    casos: int = 0
    avisos: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        if not self.casos and not self.listas_novas:
            return ""
        partes = [f"{self.casos} caso(s) nas listas"]
        if self.listas_novas:
            partes.append(f"{self.listas_novas} lista(s) ou pasta(s) criada(s)")
        return "; ".join(partes)


def _caminho(arvore: dict[int, dict], d: dict) -> list[str]:
    nomes, vistos, p = [d["name"]], {d["id"]}, d.get("parent")
    while p is not None and p in arvore and p not in vistos:
        vistos.add(p)
        nomes.insert(0, arvore[p]["name"])
        p = arvore[p].get("parent")
    return nomes


def pertencimentos(repo, uids) -> list[dict]:
    """As listas (que a sessão enxerga) em que estão os exames `uids`, com os casos desses exames."""
    uids = set(uids or [])
    if not uids:
        return []
    try:
        arvore = {d["id"]: d for d in repo.case_list_tree()}
    except Exception:  # noqa: BLE001
        log.exception("listas da origem")
        return []
    out = []
    for d in arvore.values():
        if d["kind"] in ("folder", "smart") or not d.get("count"):
            continue
        try:
            itens = [i for i in repo.list_items(d["id"]) if i.get("study_uid") in uids]
        except Exception:  # noqa: BLE001
            log.exception("casos da lista %s", d.get("name"))
            continue
        if not itens:
            continue
        pastas = []
        p = d.get("parent")
        while p is not None and p in arvore:
            pastas.insert(0, {k: arvore[p].get(k, "") for k in ("name", "description", "dono", "visivel_para")})
            p = arvore[p].get("parent")
        out.append({"caminho": _caminho(arvore, d), "pastas": pastas, "kind": d["kind"],
                    "description": d.get("description", ""), "dono": d.get("dono", ""),
                    "visivel_para": d.get("visivel_para", ""),
                    "itens": [{"study_uid": i["study_uid"], **{k: i.get(k) for k in CAMPOS}} for i in itens]})
    return out


def _achar_ou_criar(repo, arvore: list[dict], nome: str, kind: str, pai, origem: dict, res: Levadas):
    """Uma pasta/lista de nome `nome` debaixo de `pai` (preferindo a do mesmo dono); cria se não houver."""
    mesmos = [d for d in arvore if d["name"].strip().lower() == nome.strip().lower()
              and (d["kind"] == "folder") == (kind == "folder") and d.get("parent") == pai]
    dono = (origem.get("dono") or "").lower()
    mesmos.sort(key=lambda d: (d.get("dono") or "").lower() != dono)
    if mesmos:
        return mesmos[0]["id"]
    novo = repo.create_case_list(nome, kind=kind, parent=pai, description=origem.get("description", "") or "")
    res.listas_novas += 1
    try:                                           # o mesmo nível da origem, se quem leva pode
        repo.escopo_da_lista(novo, origem.get("dono", "") or "", origem.get("visivel_para", "") or "")
    except Exception as e:  # noqa: BLE001
        res.avisos.append(f"“{nome}” ficou com o nível padrão de quem levou ({e})")
    arvore.append({"id": novo, "name": nome, "kind": kind, "parent": pai, "dono": origem.get("dono", "")})
    return novo


def levar(repo, pacote: list[dict], so_exames=None) -> Levadas:
    """Põe no destino `repo` as listas de `pacote` (de `pertencimentos`). `so_exames`: só os casos
    destes exames (os que de fato chegaram)."""
    res = Levadas()
    if not pacote:
        return res
    try:
        arvore = list(repo.case_list_tree())
    except Exception as e:  # noqa: BLE001
        res.avisos.append(f"listas do destino: {e}")
        return res
    filtro = set(so_exames) if so_exames is not None else None
    for lista in pacote:
        itens = [i for i in lista.get("itens", []) if filtro is None or i["study_uid"] in filtro]
        if not itens:
            continue
        try:
            pai = None
            for pasta in lista.get("pastas", []):
                pai = _achar_ou_criar(repo, arvore, pasta["name"], "folder", pai, pasta, res)
            lid = _achar_ou_criar(repo, arvore, lista["caminho"][-1], lista.get("kind") or "normal", pai,
                                  lista, res)
            ja = {i["study_uid"]: i for i in repo.list_items(lid)}
            for i in itens:
                campos = {k: i.get(k) for k in CAMPOS if i.get(k)}
                if i["study_uid"] not in ja:
                    if repo.add_to_case_list(lid, i["study_uid"], **campos):
                        res.casos += 1
                    continue
                faltam = {k: v for k, v in campos.items() if not ja[i["study_uid"]].get(k)}
                if faltam:
                    repo.update_list_item(lid, i["study_uid"], **faltam)
        except Exception as e:  # noqa: BLE001
            log.exception("levar a lista %s", lista.get("caminho"))
            res.avisos.append(f"lista “{' / '.join(lista.get('caminho', []))}”: {e}")
    return res
