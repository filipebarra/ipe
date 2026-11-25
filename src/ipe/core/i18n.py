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
import sys
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
_LOCAL = threading.local()


class _Estado(dict):
    """O estado do idioma do programa. 0.100.66: numa linha que está dentro de `traduzir_para` (o servidor
    respondendo a um navegador noutro idioma), as leituras e gravações vão para o estado **daquele** idioma — o do
    programa não é tocado, e as outras linhas (a tela) não percebem."""

    def _d(self) -> dict | None:
        return getattr(_LOCAL, "st", None)

    def __getitem__(self, k):
        d = self._d()
        return dict.__getitem__(self, k) if d is None else d[k]

    def __setitem__(self, k, v) -> None:
        d = self._d()
        if d is None:
            dict.__setitem__(self, k, v)
        else:
            d[k] = v

    def get(self, k, padrao=None):
        d = self._d()
        return dict.get(self, k, padrao) if d is None else d.get(k, padrao)

    def setdefault(self, k, padrao=None):
        d = self._d()
        return dict.setdefault(self, k, padrao) if d is None else d.setdefault(k, padrao)


_state: dict = _Estado({"lang": BASE_LANG, "strings": {}, "patterns": [], "cache": {}, "user_dir": None,
                        "missing": set()})
_OUTROS: dict = {}                 # idioma → estado próprio (para `traduzir_para`)


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


def _especifico(p) -> tuple:
    """A ordem dos padrões: primeiro o que tem mais texto fixo (0.100.66 — antes era o mais comprido contando as
    lacunas, e um padrão quase só de lacunas, como "{} {}:{}", passava na frente de "hoje {}")."""
    src = p[0]
    return (-(len(src) - 2 * src.count("{}")), -len(src))


def load(lang: str) -> None:
    """Carrega o idioma (arquivo de fábrica + o do usuário por cima)."""
    with _lock:
        _OUTROS.clear()
        _state["lang"] = lang or BASE_LANG
        _state["cache"] = {}
        _state["missing"] = set()
        _state["strings"] = {}
        _state["patterns"] = []
        _state["reverso"] = None
        _state["valores"] = None
        _state["so_original"] = None
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
                if dst == src and not any(c.isalpha() for c in src.replace("{}", "")):
                    continue                             # "{} {}/{}": casaria com qualquer texto
                patterns.append((src, _pattern_regex(src), dst))
            else:
                strings[src] = dst
        patterns.sort(key=_especifico)                 # o mais específico primeiro
        _state["strings"], _state["patterns"] = strings, patterns


def _estado_de(lang: str) -> dict:
    """O estado de um idioma que não é o do programa (carregado uma vez; some quando o do programa é recarregado)."""
    with _lock:
        st = _OUTROS.get(lang)
        if st is None:
            data: dict = {}
            for d in (bundled_dir(), user_dir()):
                if d:
                    data.update(_load_file(Path(d) / f"{lang}.json"))
            strings, patterns = {}, []
            for src, dst in data.items():
                if not isinstance(dst, str) or not dst:
                    continue
                if "{}" in src:
                    if dst == src and not any(c.isalpha() for c in src.replace("{}", "")):
                        continue                             # "{} {}/{}": casaria com qualquer texto
                    patterns.append((src, _pattern_regex(src), dst))
                else:
                    strings[src] = dst
            patterns.sort(key=_especifico)
            st = _OUTROS[lang] = {"lang": lang, "strings": strings, "patterns": patterns, "cache": {},
                                  "missing": set(), "reverso": None, "valores": None, "so_original": None}
        return st


def traduzir_para(text, lang: str):
    """0.100.66: traduz um texto do programa (em português) para `lang`, sem mexer no idioma do programa — o
    servidor responde a cada navegador no idioma dele. Seguro entre linhas: o estado do outro idioma só vale
    nesta linha, durante a chamada."""
    lang = normalize(lang or "")
    if not isinstance(text, str) or not text or not lang or lang == BASE_LANG:
        return text
    if getattr(_LOCAL, "st", None) is None and dict.get(_state, "lang") == lang:
        return _tr_idioma(text)                            # é o idioma do programa
    antes = getattr(_LOCAL, "st", None)
    _LOCAL.st = _estado_de(lang)
    try:
        return _tr_idioma(text)
    finally:
        _LOCAL.st = antes


def current() -> str:
    return _state["lang"]


def is_base() -> bool:
    return _state["lang"] == BASE_LANG


# 0.100.32: no macOS o Qt já troca o Ctrl pelo Command (⌘) em todo atalho e em todo clique com tecla; faltava o
# texto escrito à mão ("Ctrl+C copia…", "Ctrl+clique seleciona várias"). Ele é trocado aqui, na passagem para a tela.
_MAC = {"ligado": sys.platform == "darwin"}
_RX_CTRL = re.compile(r"(?<![A-Za-z])Ctrl\+")
_RX_CTRL_SO = re.compile(r"(?<![A-Za-z])Ctrl(?![A-Za-z])")
_RX_ALT = re.compile(r"(?<![A-Za-z])Alt\+")


def teclas_do_mac(ligar: bool | None = None) -> bool:
    """Liga/desliga a troca (para os testes) e diz como está."""
    if ligar is not None:
        _MAC["ligado"] = bool(ligar)
    return _MAC["ligado"]


def com_teclas_do_mac(text: str) -> str:
    """"Ctrl+C" -> "⌘C", "Ctrl+clique" -> "⌘clique", "Alt+roda" -> "⌥roda"."""
    if "Ctrl" not in text and "Alt+" not in text:
        return text
    return _RX_ALT.sub("⌥", _RX_CTRL_SO.sub("⌘", _RX_CTRL.sub("⌘", text)))


def tr(text):
    """Traduz o texto para o idioma atual (devolve igual se não houver tradução). No macOS, com as teclas do Mac."""
    out = _tr_idioma(text)
    if _MAC["ligado"] and isinstance(out, str) and out:
        return com_teclas_do_mac(out)
    return out


def _tr_idioma(text):
    if not isinstance(text, str) or not text or _state["lang"] == BASE_LANG:
        return text
    cache = _state["cache"]
    hit = cache.get(text)
    if hit is not None:
        return hit
    out = _state["strings"].get(text)
    if out is None and text.endswith("…") and len(text) > 1:
        base = text[:-1]                        # 0.100.90: "Nódulos pulmonares…" (item de menu) = o nome + "…"
        t = _state["strings"].get(base)
        if t is not None:
            out = t + "…"
    if out is None and ("\n" in text or "<br" in text):
        # 0.100.118: o padrão de várias linhas que casa com o texto inteiro ("Não foi possível salvar:\n{}") vale
        # mais que traduzir linha a linha — a 1ª linha sozinha caía num padrão genérico ("Não {}") e saía "No foi
        # possível salvar:"
        out = _match_pattern(text, so_multilinha=True)
    if out is None and "\n\n" in text:
        out = _match_paragrafos(text)
    if out is None and ("\n" in text or "<br" in text):
        out = _match_lines(text)
    if out is None and _generico(text):
        out = _match_juntos(text)               # "nenhum {}" pegaria só o começo de "nenhum candidato… (mais 1…)"
    if out is None:
        out = _match_pattern(text)
    if out is None:
        out = _match_juntos(text)
    if out is None:
        stripped = text.strip()
        if stripped != text:
            inner = _state["strings"].get(stripped) or _match_pattern(stripped)
            if inner:
                out = text.replace(stripped, inner)
    if out is None:
        m = _NUMERADO.match(text)               # "1. Sem contraste" (etapas, casos): o número fica, o nome traduz
        if m:
            t = _tr_idioma(m.group(2))
            if t != m.group(2):
                out = m.group(1) + t
    if out is None:
        out = _match_tag(text) or _match_parts(text)
    if out is None:
        _state["missing"].add(text)
        out = text
    if len(cache) > 20000:
        cache.clear()
    cache[text] = out
    return out


_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
_NUMERADO = re.compile(r"^(\d{1,3}\. )(\S.*)$", re.S)


def _so_do_original() -> set:
    """As palavras que só existem nos textos originais (português), nunca nas traduções deste idioma — para saber se
    um pedaço que sobrou dentro de uma frase "traduzida" por um padrão genérico ainda é português."""
    v = _state.get("so_original")
    if v is None:
        orig, dest = set(), set()
        pares = list(_state["strings"].items()) + [(k, d) for k, _rx, d in _state["patterns"]]
        for k, d in pares:
            orig.update(_PALAVRA.findall(k.lower()))
            if d != k:                                   # entrada ainda sem tradução não conta como "do idioma"
                dest.update(_PALAVRA.findall(d.lower()))
        v = _state["so_original"] = orig - dest
    return v


def _ficou_em_portugues(g: str) -> bool:
    """O pedaço (não traduzido) tem pelo menos duas palavras só do português, ou uma, se é tudo o que ele tem?"""
    ws = _PALAVRA.findall(g.lower())
    if not ws or not any(c.islower() for c in g):
        return False
    so = _so_do_original()
    n = sum(1 for w in ws if w in so)
    return n >= 2 or (n == 1 and len(ws) <= 2)


def _match_pattern(text: str, so_multilinha: bool = False) -> str | None:
    for src, rx, dst in _state["patterns"]:
        if so_multilinha and not ("\n" in src or "<br" in src):
            continue
        fixo = len(src.replace("{}", "").strip())
        if so_multilinha and fixo < 10:
            continue
        m = rx.match(text)
        if m is None:
            continue
        out, groups = dst, list(m.groups())
        meio = False
        for g in groups:
            t = _parte(g)
            # 0.100.118: padrão genérico ("Não {}", "{} de {}", "IA {}") que deixa português dentro da frase não
            # vale — saía "No foi possível…", "A regra é of fulano". Melhor a frase inteira no original (e na lista
            # do que falta traduzir) do que metade em cada língua.
            if fixo < 10 and t == g and _ficou_em_portugues(g):
                meio = True
                break
            out = out.replace("{}", t, 1)
        if meio:
            continue
        return out
    return None


#: 0.100.86: onde uma frase montada por partes costuma emendar ("nenhum candidato a nódulo" + " (mais 1 abaixo…)")
_EMENDAS = (" (", " — ", "; ", ". ", ", ")


def _inteiro(trecho: str) -> str | None:
    """Tradução do trecho como frase ou padrão inteiro (sem partir), ou None."""
    t = _state["strings"].get(trecho)
    if t is None:
        for src, rx, _dst in _state["patterns"]:
            if len(src.replace("{}", "").strip()) < 10:      # "nenhum {}", "{}: {}" — genéricos demais
                continue
            if rx.match(trecho):
                t = _match_pattern_um(src, rx, _dst, trecho)
                break
        if t == trecho:
            t = None
    return t


def _generico(text: str) -> bool:
    """O primeiro padrão que casa com o texto tem pouca parte fixa ("nenhum {}", "{}: {}")?"""
    for src, rx, _dst in _state["patterns"]:
        if rx.match(text):
            return len(src.replace("{}", "").strip()) < 10
    return False


def _match_pattern_um(_src, rx, dst, text):
    m = rx.match(text)
    out = dst
    for g in m.groups():
        out = out.replace("{}", _parte(g), 1)
    return out


def _match_juntos(text: str) -> str | None:
    """0.100.86: texto que é a soma de dois trechos com tradução própria. Antes, um padrão genérico ("nenhum {}")
    pegava só o começo e o resto ficava em português ("none candidato a nódulo (mais 1 abaixo…)")."""
    if len(text) > 600:
        return None
    for sep in _EMENDAS:
        i = text.find(sep)
        while i > 0:
            a, b = text[:i], text[i:]
            ta = _inteiro(a)
            if ta is not None:
                tb = _inteiro(b) or (sep + _inteiro(b[len(sep):]) if _inteiro(b[len(sep):]) else None)
                if tb is not None:
                    return ta + tb
            i = text.find(sep, i + 1)
    return None


def _um(text: str, padrao: bool = True) -> str | None:
    """Tradução de um trecho inteiro (frase ou, se `padrao`, padrão), sem partir em linhas."""
    nu = text.strip()
    if not nu:
        return text
    t = _state["strings"].get(nu)
    if t is None and padrao:
        t = _match_pattern(nu)
        if t == nu:                     # padrão genérico que só devolve o mesmo texto
            t = None
    return None if t is None else text.replace(nu, t)


def _match_paragrafos(text: str) -> str | None:
    """0.100.13: mensagem montada com pedaços que se traduzem sozinhos, separados por linha em branco
    (`texto + "\n\nAbrir o instalador agora?"`): junta os parágrafos no maior trecho que tenha tradução. Antes,
    a mensagem inteira não batia com nada e saía em português (instalar a segmentação, com o Ipê em inglês)."""
    par = text.split("\n\n")
    out, i, algum = [], 0, False
    while i < len(par):
        for j in range(len(par), i, -1):
            trecho = "\n\n".join(par[i:j])
            # vários parágrafos juntos: só frase inteira (um padrão genérico "{}\n\n{}" engoliria tudo)
            t = _um(trecho, padrao=False) if j > i + 1 else (_um(trecho) or (_match_lines(trecho) if "\n" in trecho else None))
            if t is not None:
                out.append(t)
                algum = algum or t != trecho
                i = j
                break
        else:
            out.append(par[i])
            i += 1
    return "\n\n".join(out) if algum else None


_LINHAS = re.compile(r"(\n|<br>|<br/>|<br />)")


def _match_lines(text: str) -> str | None:
    """Texto de várias linhas (ou separado por <br>) em que cada linha se traduz sozinha ("Segmentação
    abdominal\n   só à mão"): traduz linha a linha. 0.99.35: antes um padrão genérico ("Segmentação {}")
    pegava o texto inteiro e saía "Segmentation abdominal\n   só à mão"."""
    pedacos = _LINHAS.split(text)
    out, algum = [], False
    for i, linha in enumerate(pedacos):
        nu = linha.strip()
        if i % 2 or not nu:
            out.append(linha)
            continue
        t = _state["strings"].get(nu)
        if t is None:
            t = _match_tag(nu) or _match_pattern(nu)
        if t is None:
            if nu in _valores():               # já está no idioma (pedaço traduzido antes)
                t = nu
            elif not any(c.isalpha() for c in nu) or not any(c.islower() for c in nu):
                t = nu                         # números, siglas, nomes de série em maiúsculas
            else:
                _state.setdefault("missing_atoms", set()).add(nu)
                return None
        else:
            algum = True
        out.append(linha.replace(nu, t))
    return "".join(out) if algum else None


def _valores() -> set:
    v = _state.get("valores")
    if v is None:
        v = _state["valores"] = set(_state["strings"].values())
    return v


def _parte(g: str) -> str:
    """Um pedaço que entrou numa frase montada ("Segmentando: " + etapa): traduz se for um texto
    conhecido (0.99.35; antes ia em português no meio da frase traduzida)."""
    if not g or not any(c.isalpha() for c in g):
        return g
    t = _state["strings"].get(g)
    if t is not None:
        return t
    nu = g.strip()
    if nu != g:
        t = _state["strings"].get(nu)
        if t is not None:
            return g.replace(nu, t)
    prof = _state.get("prof", 0)
    if prof >= 3 or len(g) < 3:
        return g
    if g in _valores():
        return g
    _state["prof"] = prof + 1
    try:
        t = tr(g)                               # o pedaço também pode ser uma frase montada
    finally:
        _state["prof"] = prof
    return t


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


def original(texto: str) -> str:
    """O texto em português que, traduzido, deu este (0.99.34). Para o código que decide pelo texto de
    um menu ou botão funcionar com a tela traduzida. Sem tradução conhecida, devolve o próprio texto."""
    if not isinstance(texto, str) or not texto or _state["lang"] == BASE_LANG:
        return texto
    with _lock:
        rev = _state.get("reverso")
        if rev is None:
            rev = {}
            for src, dst in _state["strings"].items():
                rev.setdefault(dst, src)
            for src, dst in _state["cache"].items():
                if isinstance(dst, str):
                    rev.setdefault(dst, src)
            _state["reverso"] = rev
    if texto in rev:
        return rev[texto]
    with _lock:                                  # traduzido depois que o índice foi montado
        for src, dst in _state["cache"].items():
            if dst == texto:
                return src
    return texto


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
