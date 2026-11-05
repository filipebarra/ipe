"""Exportar e importar as configurações (0.99.68): um arquivo só, para levar a outro computador — do Windows
para o Linux e ao contrário.

O arquivo (``.ipeconfig``) é JSON em UTF-8, com barras normais e sem nada do sistema: abre igual nos dois. Partes:

- **computador**: o settings.json deste computador;
- **pessoal**: as preferências do usuário logado (modos com usuários);
- **listas**: protocolos de exibição e de mamografia, layouts da dinâmica e modelos de folha;
- **servico**: as configurações do banco (modelos de laudo, perfis, SLA, busca ativa, permissões…);
- **nos** e **identidades**: os nós DICOM (PACS, estações) e as identidades AE;
- **regras**: a automação (buscas agendadas, anteriores, roteamento);
- **traducoes**: as traduções próprias da pasta de configuração.

Fica de fora o que é **deste computador** e não deve ir para outro: a pasta do banco e os locais, os monitores,
o login guardado, o título AE e o token deste computador, o papel de servidor/cliente, posições de janela e
estatísticas da rede. **Senhas** (dos nós, da IA do laudo) só vão se a pessoa marcar, e então o arquivo as leva em
texto claro; a cifra de cada computador (DPAPI no Windows, chave em arquivo no Linux) não passa de um para o
outro, então elas são abertas na exportação e cifradas de novo na importação.

Na importação, um caminho de pasta do outro sistema (``C:\\...`` no Linux, ``/home/...`` no Windows) não é
gravado; o que já existe aqui de mesmo nome (nó, regra, protocolo) é atualizado e o resto é acrescentado. Antes
de importar, as configurações de agora são guardadas em ``<configurações>/backups_config``.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

FORMATO = "ipe-config"
VERSAO = 1
EXTENSAO = ".ipeconfig"
SECOES = ("computador", "pessoal", "listas", "servico", "nos", "identidades", "regras", "traducoes")
TITULOS = {
    "computador": "Configurações deste computador (janela, mouse, impressão, exportação, rede…)",
    "pessoal": "Minhas preferências (do usuário logado)",
    "listas": "Protocolos de exibição e de mamografia, layouts da dinâmica, modelos de folha",
    "servico": "Do serviço: modelos de laudo, perfis, SLA, busca ativa, permissões",
    "nos": "Nós DICOM (PACS, estações)",
    "identidades": "Identidades AE",
    "regras": "Automação (buscas agendadas, anteriores, roteamento)",
    "traducoes": "Traduções próprias",
}

#: chaves do settings que são deste computador
DO_COMPUTADOR = ("data_dir", "locations", "locations_current", "monitors", "auth", "central", "network.stats",
                 "dicom.ae_title", "dicom.extra_ae_titles", "dicom.http_token", "print_scp.ae_title",
                 "shortcuts_versao", "pacs.geometry")
#: chaves do banco que não são configuração (estado de cada pessoa) ou que são da instalação
BANCO_FORA = ("report_templates_vistos",)
BANCO_FORA_PARTES = ("token", "segredo", "secret", "senha", "password")
NO_SENHAS = ("password", "client_secret")
_LISTAS = ("hanging_protocols", "mg_protocols", "dyn.layouts", "printing.templates")
_PISTA_CAMINHO = re.compile(r"(dir|path|pasta|folder|caminho|destin|arquivo|file)", re.I)
_SEGREDO = "enc1:"


# ------------------------------------------------------------------ util
def _get(d, dotted):
    from ipe.core.config import _get as g
    return g(d, dotted)


def _sem(d: dict, chaves) -> dict:
    from ipe.core.config import _del
    out = copy.deepcopy(d or {})
    for k in chaves:
        _del(out, k)
    return out


def _sem_geometria(x):
    """Tira posições e tamanhos de janela (valem para a tela de um computador só)."""
    if isinstance(x, dict):
        return {k: _sem_geometria(v) for k, v in x.items()
                if not (k == "geometry" or k.endswith("_geometry") or k.endswith(".geometry") or k == "state")}
    if isinstance(x, list):
        return [_sem_geometria(v) for v in x]
    return x


def _sem_segredos(x, levar: bool):
    """Valores cifrados ("enc1:…") não abrem em outro computador: saem, ou vão abertos se `levar`."""
    if isinstance(x, dict):
        return {k: _sem_segredos(v, levar) for k, v in x.items()}
    if isinstance(x, list):
        return [_sem_segredos(v, levar) for v in x]
    if isinstance(x, str) and x.startswith(_SEGREDO):
        if not levar:
            return ""
        from ipe.core import segredos as SG
        return SG.abrir_ou_vazio(x)
    return x


def caminho_de_outro_sistema(valor, windows: bool | None = None) -> bool:
    """Um caminho absoluto que não vale neste sistema."""
    if not isinstance(valor, str) or not valor:
        return False
    win = sys.platform.startswith("win") if windows is None else windows
    if win:
        return valor.startswith("/") and not valor.startswith("//")
    return bool(re.match(r"^[A-Za-z]:[\\/]", valor)) or valor.startswith("\\\\")


def _limpar_caminhos(x, windows=None, chave: str = "", tirados: list | None = None, onde: str = ""):
    """Tira os caminhos do outro sistema (só em chaves com cara de pasta/arquivo). Devolve a cópia."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            p = f"{onde}.{k}" if onde else k
            if isinstance(v, str) and _PISTA_CAMINHO.search(k) and caminho_de_outro_sistema(v, windows):
                if tirados is not None:
                    tirados.append(p)
                continue
            out[k] = _limpar_caminhos(v, windows, k, tirados, p)
        return out
    if isinstance(x, list):
        return [_limpar_caminhos(v, windows, chave, tirados, onde) for v in x]
    return x


def _juntar(base: dict, novo: dict) -> dict:
    from ipe.core.config import _merge
    return _merge(base or {}, novo or {})


def _por_nome(atual: list, novos: list, nome) -> list:
    """O que veio troca o de mesmo nome; o resto de agora fica; o novo entra no fim."""
    atual = [copy.deepcopy(x) for x in (atual or [])]
    idx = {nome(x).lower(): i for i, x in enumerate(atual) if nome(x)}
    for x in novos or []:
        n = nome(x).lower()
        if n and n in idx:
            atual[idx[n]] = copy.deepcopy(x)
        else:
            atual.append(copy.deepcopy(x))
    return atual


# ------------------------------------------------------------------ exportar
def montar(settings, repo=None, paths=None, secoes=SECOES, senhas: bool = False) -> dict:
    """O pacote (dict) com as partes pedidas."""
    from ipe import __version__
    pac: dict = {"formato": FORMATO, "versao": VERSAO, "programa": __version__,
                 "sistema": "windows" if sys.platform.startswith("win") else sys.platform,
                 "data": time.strftime("%Y-%m-%d %H:%M"), "senhas": bool(senhas)}
    tirar = DO_COMPUTADOR + _LISTAS
    if "computador" in secoes:
        pac["computador"] = _sem_segredos(_sem_geometria(_sem(settings.data, tirar)), senhas)
    if "pessoal" in secoes and getattr(settings, "user", None):
        pac["pessoal"] = _sem_segredos(_sem_geometria(_sem(settings.user, tirar)), senhas)
    if "listas" in secoes:
        pac["listas"] = {k: copy.deepcopy(v) for k in _LISTAS if isinstance(v := settings.get(k), list) and v}
    if repo is not None:
        if "servico" in secoes:
            try:
                srv = {}
                for k in repo.app_setting_keys():
                    if k in BANCO_FORA or k.startswith("itens:") and k[6:] in _LISTAS \
                            or any(p in k.lower() for p in BANCO_FORA_PARTES):
                        continue
                    srv[k] = repo.get_app_setting(k)
                pac["servico"] = _sem_segredos(srv, senhas)
            except Exception:  # noqa: BLE001
                log.exception("exportar as configurações do banco")
        if "nos" in secoes:
            try:
                nos = []
                for n in repo.nodes(todos=True):
                    d = {k: v for k, v in n.items() if k != "id"}
                    if not senhas:
                        for f in NO_SENHAS:
                            d[f] = ""
                    nos.append(d)
                pac["nos"] = nos
            except Exception:  # noqa: BLE001
                log.exception("exportar os nós")
        if "identidades" in secoes:
            try:
                pac["identidades"] = [{k: v for k, v in i.items() if k != "id"} for i in repo.identities(todos=True)]
            except Exception:  # noqa: BLE001
                log.exception("exportar as identidades")
        if "regras" in secoes:
            try:
                pac["regras"] = [{k: v for k, v in r.items() if k not in ("id", "last_run", "next_run")}
                                 for r in repo.rules()]
            except Exception:  # noqa: BLE001
                log.exception("exportar as regras")
    if "traducoes" in secoes and paths is not None:
        d = Path(paths.config) / "locale"
        tr = {}
        if d.is_dir():
            for f in sorted(d.glob("*.json")):
                try:
                    tr[f.name] = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    log.warning("tradução ilegível: %s", f)
        if tr:
            pac["traducoes"] = tr
    return pac


def exportar(caminho, settings, repo=None, paths=None, secoes=SECOES, senhas: bool = False) -> dict:
    pac = montar(settings, repo, paths, secoes, senhas)
    p = Path(caminho)
    if p.suffix.lower() != EXTENSAO:
        p = p.with_name(p.name + EXTENSAO)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(pac, indent=1, ensure_ascii=False, default=str), encoding="utf-8", newline="\n")
    tmp.replace(p)
    pac["_arquivo"] = str(p)
    return pac


# ------------------------------------------------------------------ importar
class PacoteInvalido(ValueError):
    pass


def ler(caminho) -> dict:
    try:
        pac = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise PacoteInvalido(f"Não consegui ler o arquivo: {e}") from e
    if not isinstance(pac, dict) or pac.get("formato") != FORMATO:
        raise PacoteInvalido("Este arquivo não é um pacote de configurações do Ipê (.ipeconfig).")
    if int(pac.get("versao") or 0) > VERSAO:
        raise PacoteInvalido("O pacote foi feito por uma versão mais nova do Ipê: atualize este computador antes.")
    return pac


def resumo(pac: dict) -> dict[str, str]:
    """{parte: o que tem} para a tela de importação."""
    out = {}
    for s in SECOES:
        v = pac.get(s)
        if not v:
            continue
        if isinstance(v, list):
            out[s] = f"itens: {len(v)}"
        elif s == "listas":
            out[s] = "; ".join(str(k) + " " + str(len(x)) for k, x in v.items())
        else:
            out[s] = f"grupos: {len(v)}"
    return out


def aplicar(pac: dict, settings, repo=None, paths=None, secoes=SECOES, windows: bool | None = None) -> dict:
    """Importa as partes pedidas. Devolve {parte: quantos, "_caminhos": [chaves tiradas], "_erros": [...]}."""
    feito: dict = {"_caminhos": [], "_erros": []}
    tirados = feito["_caminhos"]
    tirar = DO_COMPUTADOR + _LISTAS
    if "computador" in secoes and isinstance(pac.get("computador"), dict):
        novo = _limpar_caminhos(_sem(pac["computador"], tirar), windows, tirados=tirados)
        settings.data = _juntar(settings.data, novo)
        feito["computador"] = len(novo)
    if "pessoal" in secoes and isinstance(pac.get("pessoal"), dict):
        novo = _limpar_caminhos(_sem(pac["pessoal"], tirar), windows, tirados=tirados)
        if getattr(settings, "user", None) is not None:
            settings.user = _juntar(settings.user, novo)
        else:                                    # sem login: as preferências pessoais valem para o computador
            settings.data = _juntar(settings.data, novo)
        feito["pessoal"] = len(novo)
    if "listas" in secoes and isinstance(pac.get("listas"), dict):
        from ipe.core import itens as IT
        n = 0
        for k, lista in pac["listas"].items():
            if k not in _LISTAS or not isinstance(lista, list):
                continue
            try:
                settings.set(k, _por_nome(settings.get(k) or [], lista, lambda x, k=k: IT.nome_de(k, x)))
                n += len(lista)
            except Exception as e:  # noqa: BLE001
                feito["_erros"].append(f"{k}: {e}")
        feito["listas"] = n
    if repo is not None:
        if "servico" in secoes and isinstance(pac.get("servico"), dict):
            n = 0
            for k, v in pac["servico"].items():
                if k in BANCO_FORA or any(p in k.lower() for p in BANCO_FORA_PARTES):
                    continue
                try:
                    repo.set_app_setting(k, v)
                    n += 1
                except Exception as e:  # noqa: BLE001
                    feito["_erros"].append(f"{k}: {e}")
            feito["servico"] = n
        if "nos" in secoes and isinstance(pac.get("nos"), list):
            feito["nos"] = _nos(repo, pac["nos"], feito["_erros"])
        if "identidades" in secoes and isinstance(pac.get("identidades"), list):
            feito["identidades"] = _por_nome_no_banco(repo.identities(todos=True), pac["identidades"],
                                                      repo.save_identity, feito["_erros"],
                                                      lambda x: str(x.get("name", "")))
        if "regras" in secoes and isinstance(pac.get("regras"), list):
            feito["regras"] = _por_nome_no_banco(repo.rules(), pac["regras"], repo.save_rule, feito["_erros"],
                                                 lambda x: f"{x.get('kind', '')}|{x.get('name', '')}")
    if "traducoes" in secoes and isinstance(pac.get("traducoes"), dict) and paths is not None:
        d = Path(paths.config) / "locale"
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for nome, conteudo in pac["traducoes"].items():
            nome = Path(str(nome)).name                       # sem subir de pasta
            if not nome.endswith(".json"):
                continue
            atual = {}
            f = d / nome
            if f.exists():
                try:
                    atual = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    atual = {}
            if isinstance(atual, dict) and isinstance(conteudo, dict):
                conteudo = {**atual, **conteudo}
            f.write_text(json.dumps(conteudo, indent=1, ensure_ascii=False), encoding="utf-8")
            n += 1
        feito["traducoes"] = n
    settings.save()
    return feito


def _nos(repo, nos: list, erros: list) -> int:
    atuais = {(str(n.get("name", "")).lower(), str(n.get("kind", ""))): n for n in repo.nodes(todos=True)}
    n_ok = 0
    for d in nos:
        if not isinstance(d, dict):
            continue
        d = {k: v for k, v in d.items() if k != "id"}
        velho = atuais.get((str(d.get("name", "")).lower(), str(d.get("kind", ""))))
        if velho is not None:
            d["id"] = velho["id"]
            for f in NO_SENHAS:                        # pacote sem senha não apaga a senha que já está aqui
                if not d.get(f):
                    d.pop(f, None)
        try:
            repo.save_node(d)
            n_ok += 1
        except Exception as e:  # noqa: BLE001
            erros.append(f"nó {d.get('name', '')}: {e}")
    return n_ok


def _por_nome_no_banco(atuais: list, novos: list, gravar, erros: list, nome) -> int:
    idx = {nome(x).lower(): x for x in atuais}
    n = 0
    for d in novos:
        if not isinstance(d, dict):
            continue
        d = {k: v for k, v in d.items() if k not in ("id", "last_run", "next_run")}
        velho = idx.get(nome(d).lower())
        if velho is not None:
            d["id"] = velho["id"]
        try:
            gravar(d)
            n += 1
        except Exception as e:  # noqa: BLE001
            erros.append(f"{nome(d)}: {e}")
    return n


def guardar_antes(settings, repo, paths) -> Path | None:
    """Cópia das configurações de agora (sem senhas), para desfazer uma importação."""
    try:
        d = Path(paths.config) / "backups_config"
        p = d / f"antes-de-importar-{time.strftime('%Y%m%d-%H%M%S')}{EXTENSAO}"
        exportar(p, settings, repo, paths, SECOES, senhas=False)
        return p
    except Exception:  # noqa: BLE001
        log.exception("cópia das configurações antes de importar")
        return None
