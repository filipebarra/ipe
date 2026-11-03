"""Idiomas do programa.

O texto original (em português) é a chave: cada idioma é um arquivo JSON simples
{"Abrir": "Open", ...}, fácil de editar à mão ou pelo editor de traduções do programa.

Dois tipos de entrada:
- "strings": texto igual, palavra por palavra;
- "patterns": frases montadas na hora (ex.: "3 medidas exportadas para C:\\x"), guardadas com {}
  no lugar das partes que mudam: "{} medida(s) exportadas para {}".

Os arquivos de fábrica ficam em ipe/locale/<código>.json; os do usuário em
<dados>/locale/<código>.json (esses valem mais e podem criar idiomas novos).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

log = logging.getLogger(__name__)

BASE_LANG = "pt-BR"            # a língua do código-fonte (as chaves dos arquivos de tradução)
#: 0.99.33: o idioma que o programa usa quando ninguém escolheu (o instalador pergunta, com ele marcado)
DEFAULT_LANG = "en"
SUPPORTED = ("en", "pt-BR", "es")
LANGUAGE_NAMES = {"pt-BR": "Português (Brasil)", "en": "English", "es": "Español", "fr": "Français",
                  "de": "Deutsch", "it": "Italiano"}
_lock = threading.RLock()
_state: dict = {"lang": BASE_LANG, "strings": {}, "patterns": [], "cache": {}, "user_dir": None,
                "missing": set()}


def bundled_dir() -> Path:
    from ipe.core.runtime import resource_dir
    return resource_dir() / "locale"


def user_dir() -> Path | None:
    return _state["user_dir"]


def set_user_dir(path) -> None:
    _state["user_dir"] = Path(path) if path else None


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def normalize(code: str) -> str:
    """"pt", "pt_BR", "PT-br", "português" → "pt-BR"; "en-US" → "en"; desconhecido → ""."""
    c = (code or "").strip().replace("_", "-").lower()
    if not c:
        return ""
    for k, nome in LANGUAGE_NAMES.items():
        if c in (k.lower(), nome.lower()):
            return k
    curto = c.split("-")[0].split(" ")[0]
    if curto in ("pt", "portugues", "português", "portuguese"):
        return "pt-BR"
    if curto in ("en", "english", "ingles", "inglês"):
        return "en"
    if curto in ("es", "espanol", "español", "spanish", "espanhol"):
        return "es"
    return curto if curto in LANGUAGE_NAMES else ""


def available() -> list[tuple[str, str]]:
    """(código, nome) dos idiomas com arquivo (de fábrica ou do usuário): inglês, português, espanhol e
    depois os outros."""
    codes = {BASE_LANG}
    for d in (bundled_dir(), user_dir()):
        if d and Path(d).is_dir():
            for f in Path(d).glob("*.json"):
                if f.stem not in ("pt-BR", "template"):
                    codes.add(f.stem)
    primeiro = [c for c in SUPPORTED if c in codes or c == BASE_LANG]
    ordered = primeiro + sorted(c for c in codes if c not in primeiro)
    return [(c, language_name(c)) for c in ordered]


def _load_file(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        log.warning("tradução %s inválida: %s", path, e)
        return {}
    return data if isinstance(data, dict) else {}


def _pattern_regex(src: str) -> re.Pattern:
    # a parte variável não atravessa o "·" que o programa usa para juntar pedaços independentes
    parts = [re.escape(p) for p in src.split("{}")]
    return re.compile("^" + "([^·]*?)".join(parts) + "$", re.S)


_SPLIT = re.compile(r"(\s*·\s*)")                 # "a   ·   b": cada pedaço é uma frase inteira
_TAG = re.compile(r"^(<[a-z]{1,6}>)(.+)(</[a-z]{1,6}>)$", re.S | re.I)


def load(lang: str) -> None:
    """Carrega o idioma (arquivo de fábrica + o do usuário por cima)."""
    with _lock:
        _state["lang"] = lang or BASE_LANG
        _state["cache"] = {}
        _state["missing"] = set()
        _state["strings"] = {}
        _state["patterns"] = []
        if not lang or lang == BASE_LANG:
            return
        data: dict = {}
        for d in (bundled_dir(), user_dir()):
            if d:
                data.update(_load_file(Path(d) / f"{lang}.json"))
        strings, patterns = {}, []
        for src, dst in data.items():
            if not isinstance(dst, str) or not dst:
                continue
            if "{}" in src:
                patterns.append((src, _pattern_regex(src), dst))
            else:
                strings[src] = dst
        patterns.sort(key=lambda p: -len(p[0]))        # o mais específico primeiro
        _state["strings"], _state["patterns"] = strings, patterns


def current() -> str:
    return _state["lang"]


def is_base() -> bool:
    return _state["lang"] == BASE_LANG


def tr(text):
    """Traduz o texto para o idioma atual (devolve igual se não houver tradução)."""
    if not isinstance(text, str) or not text or _state["lang"] == BASE_LANG:
        return text
    cache = _state["cache"]
    hit = cache.get(text)
    if hit is not None:
        return hit
    out = _state["strings"].get(text)
    if out is None:
        out = _match_pattern(text)
    if out is None:
        stripped = text.strip()
        if stripped != text:
            inner = _state["strings"].get(stripped) or _match_pattern(stripped)
            if inner:
                out = text.replace(stripped, inner)
    if out is None:
        out = _match_tag(text) or _match_parts(text)
    if out is None:
        _state["missing"].add(text)
        out = text
    if len(cache) > 20000:
        cache.clear()
    cache[text] = out
    return out


def _match_pattern(text: str) -> str | None:
    for _src, rx, dst in _state["patterns"]:
        m = rx.match(text)
        if m is None:
            continue
        out, groups = dst, list(m.groups())
        for g in groups:
            out = out.replace("{}", g, 1)
        return out
    return None


def _match_tag(text: str) -> str | None:
    """<i>texto</i>: traduz o que está dentro da marcação."""
    m = _TAG.match(text)
    if m is None:
        return None
    inner = _state["strings"].get(m.group(2)) or _match_pattern(m.group(2))
    return None if inner is None else m.group(1) + inner + m.group(3)


def _match_parts(text: str) -> str | None:
    """Texto montado juntando frases com "·" (barra de status, rodapés): traduz cada pedaço."""
    if "·" not in text:
        return None
    pieces = _SPLIT.split(text)
    out, hit = [], False
    for i, piece in enumerate(pieces):
        if i % 2:                       # separador
            out.append(piece)
            continue
        t = _state["strings"].get(piece) or _match_pattern(piece)
        hit = hit or t is not None
        out.append(t if t is not None else piece)
    return "".join(out) if hit else None


def missing() -> list[str]:
    """Textos que apareceram na tela e ainda não têm tradução (ajuda a completar o idioma)."""
    return sorted(_state["missing"])


# ------------------------------------------------------------------ catálogo e arquivos do usuário
def catalog() -> dict:
    """Catálogo de fábrica: {"strings": [...], "patterns": [...]} com os textos em português."""
    data = _load_file(bundled_dir() / f"{BASE_LANG}.json")
    if isinstance(data.get("strings"), list):
        return {"strings": list(data.get("strings") or []), "patterns": list(data.get("patterns") or [])}
    return {"strings": sorted(data), "patterns": []}


def all_sources() -> list[str]:
    c = catalog()
    return list(c["strings"]) + list(c["patterns"])


def translations_for(lang: str) -> dict:
    """O que já existe para o idioma (fábrica + usuário)."""
    out: dict = {}
    for d in (bundled_dir(), user_dir()):
        if d:
            out.update(_load_file(Path(d) / f"{lang}.json"))
    return out


def user_file(lang: str) -> Path | None:
    d = user_dir()
    return Path(d) / f"{lang}.json" if d else None


def save_user(lang: str, mapping: dict) -> Path | None:
    """Grava as traduções do usuário (só o que é diferente do arquivo de fábrica)."""
    path = user_file(lang)
    if path is None:
        return None
    base = _load_file(bundled_dir() / f"{lang}.json")
    keep = {k: v for k, v in mapping.items() if v and base.get(k) != v}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keep, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    if lang == current():
        load(lang)
    return path


def system_language() -> str:
    """Idioma do sistema, se houver tradução para ele."""
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name()          # ex.: pt_BR, en_US, es_ES
    except Exception:  # noqa: BLE001
        import locale as _loc
        name = (_loc.getdefaultlocale()[0] or "pt_BR")
    name = name.replace("_", "-")
    codes = {c for c, _n in available()}
    if name in codes:
        return name
    short = name.split("-")[0]
    if short in codes:
        return short
    if short == "pt":
        return BASE_LANG
    return ""
