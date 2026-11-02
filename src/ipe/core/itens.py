"""Configurações em três níveis — do serviço, compartilhadas com escolhidos, pessoais (0.99.29).

Fecha o plano do modo de uso: depois dos nós DICOM e da impressão (0.99.26) e do banco (0.99.27/28),
as **listas de configuração** também ganham dono:

- protocolos de exibição, protocolos de mamografia, layouts da dinâmica da mama, modelos de folha
  (impressão) e modelos de laudo.

Cada item da lista guarda `dono` ("" = do serviço) e `visivel_para`, como nas outras etapas. Cada um
vê os do serviço, os seus e os compartilhados com ele; **um item pessoal com o mesmo nome de um do
serviço toma o lugar dele só para o dono** — é assim que alguém ajusta um protocolo do serviço para si
sem mexer no dos outros.

Quem edita a lista na janela de sempre (protocolos, mamografia…) não precisa pensar nisso:

- item novo: do serviço se for o administrador, pessoal para os outros (como na 0.99.26);
- mudar um item do serviço **sem** a permissão de configurar cria a cópia pessoal; com a permissão,
  muda o do serviço;
- apagar: o seu some; o do serviço só com a permissão de configurar; o compartilhado por outro fica.

Os itens de todo mundo ficam juntos num lugar só: no banco (AppSetting "itens:<chave>") — o do
computador nos modos com usuários, o do servidor no modo cliente. No modo "só eu" nada muda: as
listas ficam no settings.json como sempre. Enquanto ninguém gravou com usuários, vale a lista que já
estava no computador (tudo do serviço).
"""
from __future__ import annotations

import copy
import logging

log = logging.getLogger(__name__)

#: chave -> (campo do nome, título)
CHAVES: dict[str, tuple[str, str]] = {
    "hanging_protocols": ("name", "Protocolos de exibição"),
    "mg_protocols": ("name", "Protocolos de mamografia"),
    "dyn.layouts": ("nome", "Layouts da dinâmica da mama"),
    "printing.templates": ("name", "Modelos de folha (impressão)"),
    "report_templates": ("name", "Modelos de laudo"),
}
#: as que moram no settings.json (o modelo de laudo já morava no banco)
CHAVES_SETTINGS = ("hanging_protocols", "mg_protocols", "dyn.layouts", "printing.templates")
CAMPOS = ("dono", "visivel_para")


def nome_de(chave: str, item) -> str:
    campo = CHAVES.get(chave, ("name", ""))[0]
    return str((item or {}).get(campo, "") or "").strip() if isinstance(item, dict) else ""


def _conteudo(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in CAMPOS}


def _dono(item) -> str:
    return str((item or {}).get("dono", "") or "").strip()


def visiveis(chave: str, guardados, visao=None, gerenciar: bool = False) -> list[dict]:
    """O que esta visão enxerga. Sem `gerenciar`, o pessoal dela toma o lugar do do serviço de mesmo nome."""
    from ipe.auth import visibilidade as V
    lista = [x for x in (guardados or []) if isinstance(x, dict) and V.visivel(x, visao, gerenciar)]
    if visao is None or gerenciar:
        return lista
    eu = visao.usuario.lower()
    meus = {nome_de(chave, x).lower() for x in lista if _dono(x).lower() == eu}
    out, vistos = [], set()
    for x in lista:
        n = nome_de(chave, x).lower()
        if not _dono(x) and n in meus:
            continue                                   # o meu substitui o do serviço
        if n in vistos and _dono(x).lower() != eu:
            continue
        vistos.add(n)
        out.append(x)
    return out


def juntar(chave: str, guardados, editados, visao, pode_servico: bool) -> tuple[list[dict], list[str]]:
    """A lista nova de todo mundo depois que `visao` gravou `editados` (a lista que ela via, editada).
    Devolve (lista, avisos)."""
    from ipe.auth import visibilidade as V
    guardados = [dict(x) for x in (guardados or []) if isinstance(x, dict)]
    editados = [_conteudo(dict(x)) for x in (editados or []) if isinstance(x, dict)]
    if visao is None:                                  # "só eu": a lista é a que veio
        return editados, []
    eu = visao.usuario.lower()
    antes = {nome_de(chave, x).lower(): x for x in visiveis(chave, guardados, visao)}
    vistos_ids = {id(x) for x in antes.values()}
    # o que esta visão não enxergava (ou enxergava por baixo do pessoal dela) fica como estava
    ficam = [x for x in guardados if id(x) not in vistos_ids]
    novos: list[dict] = []
    avisos: list[str] = []
    for e in editados:
        n = nome_de(chave, e).lower()
        prev = antes.pop(n, None)
        if prev is None:
            novos.append({**e, **V.padrao_novo(visao)})
            continue
        if _conteudo(prev) == e:
            novos.append(prev)                         # sem mudança: fica como estava
            continue
        dono = _dono(prev).lower()
        if dono == eu or (not dono and pode_servico) or (dono and visao.admin):
            novos.append({**e, "dono": prev.get("dono", ""), "visivel_para": prev.get("visivel_para", "")})
        else:                                          # do serviço (sem permissão) ou de outro: cópia pessoal
            novos.append({**e, "dono": visao.usuario, "visivel_para": ""})
            if not dono:
                ficam.append(prev)
                avisos.append(f"“{nome_de(chave, e)}” é do serviço: a mudança ficou numa cópia só sua.")
            else:
                ficam.append(prev)
    for n, prev in antes.items():                      # apagados
        dono = _dono(prev).lower()
        if dono == eu or (not dono and pode_servico) or (dono and visao.admin):
            continue
        ficam.append(prev)
        avisos.append(f"“{nome_de(chave, prev)}” não foi apagado: "
                      + ("é do serviço (pede a permissão de configurar)." if not dono else f"é de {prev['dono']}."))
    # devolve na ordem: os desta visão na ordem em que ela pôs, os outros depois
    return novos + [x for x in ficam if x not in novos], avisos


def mudar_escopo(chave: str, guardados, nome: str, dono_atual: str, novo_dono: str, visivel_para: str,
                 visao, pode_servico: bool) -> list[dict]:
    """Muda quem vê um item (Configurações ▸ Usuários ▸ Pessoais e compartilhadas). Levanta
    PermissionError quando a regra não deixa."""
    if visao is None:
        raise PermissionError("no modo “só eu” tudo é de todos")
    alvo = next((x for x in guardados or [] if isinstance(x, dict) and nome_de(chave, x).lower() == nome.lower()
                 and _dono(x).lower() == (dono_atual or "").lower()), None)
    if alvo is None:
        raise PermissionError("item não encontrado")
    eu = visao.usuario.lower()
    dono = _dono(alvo).lower()
    novo = (novo_dono or "").strip()
    if not visao.admin:
        if dono not in ("", eu):
            raise PermissionError("só o dono (ou o administrador) muda quem vê")
        if not dono and not pode_servico:
            raise PermissionError("mexer num item de todos pede a permissão de configurar; use “Copiar para mim”")
        if novo and novo.lower() != eu:
            raise PermissionError("só o administrador passa um item para outro usuário")
        if not novo and not pode_servico:
            raise PermissionError("pôr para todos pede a permissão de configurar")
    if any(isinstance(x, dict) and x is not alvo and nome_de(chave, x).lower() == nome.lower()
           and _dono(x).lower() == novo.lower() for x in guardados):
        raise PermissionError("já existe um item com esse nome nesse nível")
    alvo["dono"], alvo["visivel_para"] = novo, (visivel_para or "").strip() if novo else ""
    return guardados


def copia_pessoal(chave: str, guardados, nome: str, dono_atual: str, visao) -> list[dict]:
    """"Copiar para mim": o item (do serviço ou compartilhado comigo) vira também um pessoal meu."""
    if visao is None:
        raise PermissionError("no modo “só eu” tudo é de todos")
    alvo = next((x for x in guardados or [] if isinstance(x, dict) and nome_de(chave, x).lower() == nome.lower()
                 and _dono(x).lower() == (dono_atual or "").lower()), None)
    if alvo is None:
        raise PermissionError("item não encontrado")
    eu = visao.usuario.lower()
    if any(nome_de(chave, x).lower() == nome.lower() and _dono(x).lower() == eu for x in guardados):
        raise PermissionError("você já tem um pessoal com esse nome")
    return list(guardados) + [{**copy.deepcopy(_conteudo(alvo)), "dono": visao.usuario, "visivel_para": ""}]


# ---------------------------------------------------------------------- ligação com as configurações
class Armazem:
    """O que o Settings consulta para as CHAVES_SETTINGS quando há usuário logado (modos com usuários)."""

    def __init__(self, repo, settings_data: dict | None = None):
        self.repo = repo
        self.base = settings_data or {}             # o settings.json do computador (vale até alguém gravar)
        self._cache: dict[str, list] = {}
        self.avisos: list[str] = []

    def _da_maquina(self, chave: str):
        from ipe.core.config import _get
        ok, v = _get(self.base, chave)
        return copy.deepcopy(v) if ok and isinstance(v, list) else None

    def efetivo(self, chave: str):
        if chave not in self._cache:
            try:
                v = self.repo.itens_de_config(chave)
            except Exception:  # noqa: BLE001
                log.exception("ler %s", chave)
                v = None
            if v is None:
                v = self._da_maquina(chave)
            else:      # quem usa a lista (editores, SheetTemplate.from_dict…) não conhece os campos de dono
                v = [_conteudo(x) for x in visiveis(chave, v, _visao())]
            self._cache[chave] = v
        v = self._cache[chave]
        return copy.deepcopy(v) if v is not None else None

    def salvar(self, chave: str, lista) -> list[str]:
        self._cache.pop(chave, None)
        try:
            avisos = self.repo.salvar_itens_de_config(chave, list(lista or []), self._da_maquina(chave)) or []
        except Exception:  # noqa: BLE001
            log.exception("gravar %s", chave)
            raise
        self.avisos += avisos
        return avisos

    def adotar(self, chave: str, pessoais: list[dict]) -> int:
        """Migração: a lista pessoal que o usuário tinha nas preferências (até a 0.99.28) entra como
        itens pessoais dele. Só os que diferem do que ele já vê do serviço."""
        vistos = {nome_de(chave, x).lower(): _conteudo(x) for x in (self.efetivo(chave) or [])}
        meus = [x for x in pessoais or [] if isinstance(x, dict)
                and vistos.get(nome_de(chave, x).lower()) != _conteudo(x)]
        if not meus:
            return 0
        self._cache.pop(chave, None)
        self.repo.adotar_itens_de_config(chave, meus, self._da_maquina(chave))
        return len(meus)

    def limpar(self) -> None:
        self._cache.clear()


def _visao():
    from ipe.auth import visibilidade as V
    return V.visao_atual()


# ---------------------------------------------------------------------- lado do banco (Repository)
def _chave_banco(chave: str) -> str:
    """Onde a lista mora no banco: o modelo de laudo já morava em "report_templates"."""
    return chave if chave == "report_templates" else "itens:" + chave


def guardados(repo, chave: str):
    return repo.get_app_setting(_chave_banco(chave), None)


def ler(repo, chave: str, gerenciar: bool = False):
    """None = ninguém gravou ainda com usuários. Devolve só o que quem pede pode ver (sem tirar o
    duplicado de nome: isso é com quem consulta)."""
    from ipe.auth import visibilidade as V
    g = guardados(repo, chave)
    if g is None:
        return None
    v = V.visao_atual()
    return [x for x in g if isinstance(x, dict) and V.visivel(x, v, gerenciar)]


def gravar(repo, chave: str, editados, base=None) -> list[str]:
    from ipe.auth import visibilidade as V
    if chave not in CHAVES:
        raise PermissionError(f"configuração desconhecida: {chave}")
    g = guardados(repo, chave)
    if g is None:
        g = [{**_conteudo(x), "dono": "", "visivel_para": ""} for x in (base or []) if isinstance(x, dict)]
    lista, avisos = juntar(chave, g, editados, V.visao_atual(), V.pode("configure"))
    repo.set_app_setting(_chave_banco(chave), lista)
    return avisos


def adotar(repo, chave: str, pessoais, base=None) -> None:
    from ipe.auth import visibilidade as V
    v = V.visao_atual()
    if v is None or chave not in CHAVES:
        return
    g = guardados(repo, chave)
    if g is None:
        g = [{**_conteudo(x), "dono": "", "visivel_para": ""} for x in (base or []) if isinstance(x, dict)]
    eu = v.usuario.lower()
    for x in pessoais or []:
        n = nome_de(chave, x).lower()
        g = [y for y in g if not (nome_de(chave, y).lower() == n and _dono(y).lower() == eu)]
        g.append({**_conteudo(x), "dono": v.usuario, "visivel_para": ""})
    repo.set_app_setting(_chave_banco(chave), g)


def escopo(repo, chave: str, nome: str, dono_atual: str, novo_dono: str = "", visivel_para: str = "",
           copiar: bool = False, base=None) -> None:
    from ipe.auth import visibilidade as V
    g = guardados(repo, chave)
    if g is None:
        g = [{**_conteudo(x), "dono": "", "visivel_para": ""} for x in (base or []) if isinstance(x, dict)]
    v, pode = V.visao_atual(), V.pode("configure")
    g = copia_pessoal(chave, g, nome, dono_atual, v) if copiar else \
        mudar_escopo(chave, g, nome, dono_atual, novo_dono, visivel_para, v, pode)
    repo.set_app_setting(_chave_banco(chave), g)
