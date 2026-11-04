"""Caminhos e configurações do programa, iguais em Windows e Linux.

Tudo que é por usuário fica em pastas padrão do sistema (platformdirs):
- Windows: C:\\Users\\<usuario>\\AppData\\Local\\DicomViewer\\...
- Linux:   ~/.local/share/DicomViewer e ~/.config/DicomViewer

A variável de ambiente IPE_HOME (ou a antiga DICOMVIEWER_HOME) permite usar outra pasta (útil em
testes, em pendrive ou para separar bancos de pesquisa).
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir, user_log_dir

log = logging.getLogger(__name__)

from ipe import DATA_NAME


@dataclass(frozen=True)
class AppPaths:
    data: Path          # banco de dados e armazenamento
    config: Path        # settings.json
    logs: Path

    @property
    def database(self) -> Path:
        return self.data / "dicomviewer.sqlite"

    @property
    def storage(self) -> Path:
        return self.data / "Storage"

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    def ensure(self) -> "AppPaths":
        for p in (self.data, self.config, self.logs, self.storage):
            p.mkdir(parents=True, exist_ok=True)
        return self


def default_data_dir() -> Path:
    """Onde ficam banco e arquivos quando o usuário não escolheu outra pasta."""
    home = os.environ.get("IPE_HOME") or os.environ.get("DICOMVIEWER_HOME")
    if home:
        return Path(home).expanduser().resolve() / "data"
    return Path(user_data_dir(DATA_NAME, appauthor=False))


def chosen_data_dir(config_dir: Path) -> Path | None:
    """Pasta escolhida pelo usuário para o banco deste computador (Configurações → "data_dir").

    Fica em settings.json, que mora na pasta de configurações — ela não se move junto, então a escolha
    sobrevive à mudança e o programa sabe onde procurar ao abrir."""
    try:
        data = json.loads((Path(config_dir) / "settings.json").read_text(encoding="utf-8"))
        d = (data or {}).get("data_dir") or ""
    except (OSError, ValueError):
        return None
    if not d:
        return None
    p = Path(d).expanduser()
    return p if p.is_dir() or not p.exists() else None


def get_paths() -> AppPaths:
    home = os.environ.get("IPE_HOME") or os.environ.get("DICOMVIEWER_HOME")
    if home:
        base = Path(home).expanduser().resolve()
        cfg = base / "config"
        return AppPaths(chosen_data_dir(cfg) or (base / "data"), cfg, base / "logs").ensure()
    cfg = Path(user_config_dir(DATA_NAME, appauthor=False))
    return AppPaths(
        chosen_data_dir(cfg) or Path(user_data_dir(DATA_NAME, appauthor=False)),
        cfg,
        Path(user_log_dir(DATA_NAME, appauthor=False)),
    ).ensure()


# ---------------------------------------------------------------------------
# Preferências do usuário (fase 1: arquivo JSON; no modo multiusuário vão para
# a tabela user_setting do banco).
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict[str, Any] = {
    # pasta do banco deste computador ("" = a padrão do sistema); ver chosen_data_dir()
    "data_dir": "",
    # marca da faxina dos atalhos de teclado (ver Settings.migrar_atalhos)
    "shortcuts_versao": 0,
    "import": {
        # True = copia os arquivos para a pasta Storage; False = só referencia
        "copy_to_storage": True,
    },
    "viewer": {
        "default_layout": [1, 1],
        "invert_wheel": False,
        # Presets de janela: tecla -> (nome, largura, nível)
        "wl_presets": {
            "1": ["Pulmão", 1500, -600],
            "2": ["Mediastino", 400, 40],
            "3": ["Osso", 2000, 400],
            "4": ["Cérebro", 80, 40],
            "5": ["Abdome", 350, 50],
            "6": ["Fígado", 160, 60],
        },
        # Mapeamento do mouse. Ações possíveis:
        # wl, zoom, pan, scroll, measure, none
        "mouse": {
            "left": "wl",
            "middle": "pan",
            "right": "zoom",        # segurar e arrastar
            "right_click": "menu",   # clicar e soltar
            "middle_click": "fit",
            "wheel": "scroll",
            "ctrl_wheel": "zoom",
            "shift_wheel": "scroll5",
            # botões laterais (4 = voltar, 5 = avançar)
            "back": "series_prev",
            "forward": "series_next",
        },
        # Tempo (ms) e distância (px) que separam "clique" de "segurar"
        "click_max_ms": 220,
        "click_max_px": 4,
        # Áreas clicáveis do overlay
        "overlay_hotspots": True,
        # Fechar a janela deixa o programa na bandeja (nó DICOM e buscas agendadas continuam)
        "close_to_tray": False,
        "autostart": False,
        # Ao abrir pelo banco, perguntar as séries se o estudo tiver mais que isto (0 = nunca)
        "ask_series_above": 0,
        # Exames anteriores abrem no monitor de comparação (se houver um configurado)
        "priors_on_compare": True,
    },
    # Memória: 0 = automático (1/4 da RAM para imagens; 1/4 para cada volume de MPR)
    "performance": {
        "cache_mb": 0,
        "max_volume_mb": 0,
    },
    # Nó DICOM local e API de chamada externa
    "dicom": {
        "enabled": True,
        "ae_title": "DICOMVIEWER",
        "port": 11112,
        "accept": "known",          # known = só nós cadastrados; known_ip = e no IP cadastrado; any = qualquer AE
        "extra_ae_titles": [],      # outros AE Titles em que o programa também responde
        "timeout": 30,
        "max_parallel": 2,          # transferências simultâneas
        "http_enabled": True,
        "http_port": 8042,
        "http_token": "",           # gerado na primeira execução
        "http_allow_remote": False,
        "external_viewer_only": False,   # a chamada externa abre só o visualizador
        "http_allowed_ips": [],
        # link ipe:// sem o token: qualquer página da internet pode montar um (0.99.24)
        "link_sem_token": "perguntar",   # perguntar | aceitar | recusar
    },
    # impressora DICOM: recebe filmes das modalidades (TC, RM, MG, US) e guarda
    "print_scp": {
        "enabled": False,
        "ae_title": "DICOMPRINT",
        "port": 11113,
        "accept": "rede",           # rede = qualquer AE da rede local; any = de qualquer lugar; known = só nós
        "timeout": 60,
        "to_database": True,        # a folha recebida também vira exame no banco
        "auto_destination": "",     # "" = segurar tudo e esperar você decidir
        "keep_days": 0,             # 0 = guardar para sempre
    },
    # Papel e layout de cada monitor: {"<id do monitor>": {"role": "viewer", "layout": [1, 2]}}
    "monitors": {},
}


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


# preferências que são de cada usuário (com login, ficam no banco — ou no servidor central);
# o resto é do computador (rede, desempenho, monitores, servidor/cliente…)
USER_KEYS = ("viewer", "shortcuts", "hanging_protocols", "mg_protocols", "browser", "export", "meeting", "priors")
MACHINE_EXCEPTIONS = ("viewer.close_to_tray", "viewer.autostart")


#: 0.99.36: chaves de fora dos grupos de USER_KEYS que também são de cada usuário (com a do computador
#: por baixo): as Referências que vão entre parênteses no texto da cefalometria e dos índices do crânio
USER_DOTTED = ("cefalo.referencias", "neuro.referencias")


def is_user_key(dotted: str) -> bool:
    if dotted in USER_DOTTED:
        return True
    if dotted.split(".")[0] not in USER_KEYS:
        return False
    return not any(dotted == m or dotted.startswith(m + ".") for m in MACHINE_EXCEPTIONS)


def _get(node: Any, dotted: str) -> tuple[bool, Any]:
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


_CHAVES_ITENS = ("hanging_protocols", "mg_protocols", "dyn.layouts", "printing.templates")   # core/itens.py


def _del(node: dict, dotted: str) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.get(part) if isinstance(node, dict) else None
        if not isinstance(node, dict):
            return
    if isinstance(node, dict):
        node.pop(parts[-1], None)


def _set(node: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = node[part] = {}
        node = nxt
    node[parts[-1]] = value


# Teclas de fábrica que entraram depois da faxina da 0.65, por versão da marca `shortcuts_versao`.
# A janela de Preferências grava **todas** as ações (inclusive as vazias), então mudar o padrão
# não chega a quem já salvou: a tecla nova é posta uma vez, se a ação estiver vazia e a tecla
# não estiver em uso por outra ação.
NOVOS_ATALHOS: dict[int, dict[str, str]] = {
    3: {"film.add": "F1", "film.series": "F2"},       # pedido dele (13/10/2026)
    4: {"view.copy": "Ctrl+C"},                       # pedido dele (29/10/2026)
}


def _acrescentar_padroes(atalhos: dict, desde: int) -> bool:
    mexeu = False
    for versao, novos in sorted(NOVOS_ATALHOS.items()):
        if versao <= desde:
            continue
        for aid, tecla in novos.items():
            if atalhos.get(aid):
                continue                     # ele já escolheu uma tecla para esta ação
            if any(v == tecla for k, v in atalhos.items() if k != aid):
                atalhos[aid] = ""            # a tecla é de outra ação dele: esta fica sem
            elif aid in atalhos:
                del atalhos[aid]             # vazio gravado sai: passa a valer o de fábrica
                mexeu = True
    return mexeu


class Settings:
    """Preferências lidas/gravadas em settings.json, com valores padrão.
    Com um usuário logado (attach_user), as chaves de USER_KEYS vêm das preferências dele."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = deepcopy(DEFAULT_SETTINGS)
        self.user: dict[str, Any] | None = None
        self._user_saver = None
        self.load()

    def attach_user(self, prefs: dict | None, saver=None) -> None:
        """Camada de preferências do usuário; `saver(prefs)` grava (banco local ou servidor)."""
        self.user = dict(prefs or {})
        self._user_saver = saver
        versao = int(self.user.get("shortcuts_versao") or 0)
        if versao < 2:
            self.user["shortcuts"] = {}          # a mesma faxina de migrar_atalhos, nesta camada
        elif versao < self.ATALHOS_VERSAO:
            _acrescentar_padroes(self.user.setdefault("shortcuts", {}), versao)
        self.user["shortcuts_versao"] = self.ATALHOS_VERSAO

    def detach_user(self) -> None:
        self.user, self._user_saver = None, None
        self.itens = None
        self.perfil = None

    # 0.99.56 (onda B2): perfil do grupo ou do computador mandado pelo servidor (core/perfis.py) — uma camada
    # entre o computador e a pessoa; as chaves "forçadas" ninguém troca
    perfil = None

    def attach_perfil(self, perfil: dict | None) -> None:
        p = perfil or {}
        self.perfil = p if (p.get("valores") or p.get("forcados")) else None

    def forcado(self, dotted: str) -> bool:
        if not self.perfil:
            return False
        return any(dotted == f or dotted.startswith(f + ".") for f in self.perfil.get("forcados") or [])

    def _get_com_perfil(self, dotted: str, default: Any = None) -> Any:
        camadas = []
        ok, v = _get(self.data, dotted)
        if ok:
            camadas.append(v)
        valores = self.perfil.get("valores") or {}
        ok, v = _get(valores, dotted)
        if ok:
            camadas.append(v)
        if self.user is not None and is_user_key(dotted) and not self.forcado(dotted):
            ok, v = _get(self.user, dotted)
            if ok:
                camadas.append(v)
        if self.forcado(dotted):
            ok, v = _get(valores, dotted)
            if ok:
                camadas.append(v)
        if not camadas:
            return default
        out = camadas[0]
        for c in camadas[1:]:
            out = _merge(out, c) if isinstance(out, dict) and isinstance(c, dict) else c
        # chave forçada mais funda do que a pedida (pede "viewer", forçado "viewer.mouse")
        for f in self.perfil.get("forcados") or []:
            if f.startswith(dotted + ".") and isinstance(out, dict):
                ok, v = _get(valores, f)
                if ok:
                    out = deepcopy(out)
                    _set(out, f[len(dotted) + 1:], v)
        return out

    # 0.99.30: as listas de configuração com dono (protocolos, modelos…) — ver core/itens.py
    itens = None

    def attach_itens(self, armazem) -> dict[str, int]:
        """Liga as CHAVES_SETTINGS ao armazém (modos com usuários). Migra, uma vez, a lista pessoal
        que o usuário tinha nas preferências dele: vira itens pessoais. Devolve {chave: itens migrados}."""
        from ipe.core import itens as IT
        self.itens = armazem
        migrados: dict[str, int] = {}
        if armazem is None or self.user is None:
            return migrados
        mexeu = False
        for chave in IT.CHAVES_SETTINGS:
            ok, v = _get(self.user, chave)
            if not ok:
                continue
            try:
                if isinstance(v, list):
                    migrados[chave] = armazem.adotar(chave, v)
                _del(self.user, chave)
                mexeu = True
            except Exception:  # noqa: BLE001
                log.exception("migrar %s", chave)
        if mexeu and self._user_saver is not None:
            try:
                self._user_saver(self.user)
            except Exception:  # noqa: BLE001
                log.exception("gravar as preferências depois da migração")
        return migrados

    ATALHOS_VERSAO = 4          # 2 = a lista de fábrica foi zerada (0.65); 3 = F1/F2 do filme (0.76);
    #                             4 = Ctrl+C copia o quadro (0.99.9)

    def migrar_atalhos(self) -> bool:
        """Zera, **uma** vez, os atalhos de teclado que já estavam gravados. Devolve se mexeu.

        A lista de fábrica virou quase vazia na 0.65 (pedido dele). Só mudar o padrão não
        bastava: quem já abriu Preferências tem `shortcuts` no settings.json com as ~70 teclas
        antigas, e o gravado manda sobre o padrão — ele continuaria com tudo ligado. A marca de
        versão é o que faz isto acontecer uma vez só: atalho que ele configurar depois não é
        apagado na abertura seguinte.
        """
        versao = int(self.get("shortcuts_versao") or 0)
        if versao >= self.ATALHOS_VERSAO:
            return False
        if versao < 2:
            mexeu = bool(self.data.get("shortcuts")) or bool((self.user or {}).get("shortcuts"))
            self.data["shortcuts"] = {}
            if self.user is not None:
                self.user["shortcuts"] = {}
        else:
            # Versão nova de fábrica: só acrescenta tecla nova, nunca apaga o que ele escolheu.
            mexeu = _acrescentar_padroes(self.data.setdefault("shortcuts", {}), versao)
            if self.user is not None:
                mexeu = _acrescentar_padroes(self.user.setdefault("shortcuts", {}), versao) or mexeu
        if self.user is not None:
            self.user["shortcuts_versao"] = self.ATALHOS_VERSAO
        self.data["shortcuts_versao"] = self.ATALHOS_VERSAO
        return mexeu

    def reset_defaults(self) -> None:
        self.data = deepcopy(DEFAULT_SETTINGS)
        self.data["shortcuts_versao"] = self.ATALHOS_VERSAO
        if self.user is not None:
            self.user = {"shortcuts_versao": self.ATALHOS_VERSAO}

    def load(self) -> None:
        if self.path.exists():
            try:
                user = json.loads(self.path.read_text(encoding="utf-8"))
                self.data = _merge(DEFAULT_SETTINGS, user)
                self.migrar_atalhos()
            except (OSError, json.JSONDecodeError):
                # arquivo corrompido: mantém os padrões, não derruba o programa
                self.data = deepcopy(DEFAULT_SETTINGS)

    def save(self) -> None:
        if self.user is not None and self._user_saver is not None:
            try:
                self._user_saver(self.user)
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception("preferências do usuário")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, dotted: str, default: Any = None) -> Any:
        if self.itens is not None and dotted in _CHAVES_ITENS:
            v = self.itens.efetivo(dotted)
            return v if v is not None else default
        if self.perfil:
            return self._get_com_perfil(dotted, default)
        if self.user is not None and is_user_key(dotted):
            found, v = _get(self.user, dotted)
            if found:
                if isinstance(v, dict):              # completa com os padrões da máquina
                    ok, base = _get(self.data, dotted)
                    if ok and isinstance(base, dict):
                        return _merge(base, v)
                return v
        found, v = _get(self.data, dotted)
        return v if found else default

    def do_computador(self, dotted: str, default: Any = None) -> Any:
        """O valor deste computador (o padrão de quem não tem o seu), sem a camada do usuário."""
        found, v = _get(self.data, dotted)
        return v if found else default

    def set_do_computador(self, dotted: str, value: Any) -> None:
        """Grava para todos deste computador (0.99.36): o valor da máquina, sem passar pela camada do
        usuário — e tira a versão pessoal de quem gravou, para ele passar a ver a de todos."""
        _set(self.data, dotted, value)
        if self.user is not None and is_user_key(dotted):
            _del(self.user, dotted)

    def tem_pessoal(self, dotted: str) -> bool:
        return self.user is not None and is_user_key(dotted) and _get(self.user, dotted)[0]

    def tirar_pessoal(self, dotted: str) -> None:
        if self.user is not None:
            _del(self.user, dotted)

    def set(self, dotted: str, value: Any) -> None:
        if self.itens is not None and dotted in _CHAVES_ITENS:
            self.itens.salvar(dotted, value)
            return
        if self.user is not None and is_user_key(dotted):
            _set(self.user, dotted, value)
            return
        _set(self.data, dotted, value)
