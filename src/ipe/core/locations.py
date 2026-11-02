"""Locais dos exames (bancos de dados), no estilo do OsiriX/Horos.

Cada local é uma **pasta que carrega o banco inteiro**: índice, arquivos copiados, listas de casos,
laudos, medidas e comentários. Dá para levar o HD externo para outro computador e abrir lá com tudo.

    <pasta escolhida>/
        dicomviewer.sqlite          índice (pacientes, exames, medidas, laudos, listas…)
        Storage/                    arquivos copiados para dentro do local
        dicomviewer-local.json      marca que a pasta é um local (nome, data, versão)

Os arquivos que já estavam na pasta continuam onde estão: ao adicionar um local, o programa só
indexa (referencia) — nada é copiado, movido ou alterado.

A lista de locais fica nas **configurações do usuário** (settings.json), nunca dentro de um local:
assim ela sobrevive à troca de local e some junto com o programa, não com o HD.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MARKER = "dicomviewer-local.json"
DB_NAME = "dicomviewer.sqlite"
STORAGE_NAME = "Storage"
DEFAULT_ID = "default"
DEFAULT_NAME = "Banco deste computador"
CENTRAL_ID = "central"            # 0.99.28: no modo cliente, o servidor do grupo aparece como um local
CENTRAL_NAME = "Servidor central"


@dataclass(frozen=True)
class Location:
    """Um local de exames. `kind`: default (a pasta do programa), folder, external, network."""

    id: str
    name: str
    path: Path
    kind: str = "folder"

    # ---------------------------------------------------------------- caminhos
    @property
    def database(self) -> Path:
        return self.path / DB_NAME

    @property
    def storage(self) -> Path:
        return self.path / STORAGE_NAME

    @property
    def marker(self) -> Path:
        return self.path / MARKER

    # ---------------------------------------------------------------- estado
    @property
    def is_default(self) -> bool:
        return self.id == DEFAULT_ID

    def online(self) -> bool:
        """A pasta está acessível agora? (HD externo desconectado, rede fora do ar…)"""
        try:
            return self.path.is_dir()
        except OSError:
            return False

    def ready(self) -> bool:
        """Já é um local montado (tem o índice ou a marca)."""
        try:
            return self.online() and (self.database.exists() or self.marker.exists())
        except OSError:
            return False

    def kind_label(self) -> str:
        return {"default": "Este computador", "external": "Disco externo",
                "network": "Pasta de rede", "central": "Servidor do grupo"}.get(self.kind, "Pasta")

    @property
    def is_central(self) -> bool:
        return self.id == CENTRAL_ID

    def size_mb(self) -> float:
        """Quanto o local ocupa (só o que foi copiado para dentro dele)."""
        total = 0
        try:
            for root, _dirs, files in os.walk(self.storage):
                for f in files:
                    try:
                        total += (Path(root) / f).stat().st_size
                    except OSError:
                        pass
        except OSError:
            return 0.0
        return total / 1024 / 1024


# --------------------------------------------------------------------- pastas

def guess_kind(path) -> str:
    """Disco externo, pasta de rede ou pasta comum — só para o ícone e o texto da tela."""
    p = str(Path(path))
    if p.startswith("\\\\") or p.startswith("//"):
        return "network"
    if os.name == "nt":
        drive = Path(p).drive.upper()
        if drive and drive != Path.home().drive.upper():
            return "external"
        return "folder"
    for mount in ("/media/", "/mnt/", "/run/media/", "/Volumes/"):
        if p.startswith(mount):
            return "external"
    if p.startswith("/net/") or p.startswith("/smb/"):
        return "network"
    return "folder"


def read_marker(path) -> dict:
    try:
        return json.loads((Path(path) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_marker(path, name: str) -> None:
    from ipe import __version__
    data = read_marker(path)
    data.update({"name": name, "version": __version__})
    data.setdefault("created", time.strftime("%Y-%m-%d %H:%M"))
    try:
        (Path(path) / MARKER).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    except OSError as e:  # noqa: BLE001
        log.warning("não deu para gravar a marca do local em %s: %s", path, e)


def prepare(path, name: str) -> Path:
    """Deixa a pasta pronta para ser um local (cria Storage e a marca). Não copia nada."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    (p / STORAGE_NAME).mkdir(exist_ok=True)
    write_marker(p, name)
    return p


def looks_used(path) -> bool:
    """A pasta já tem um local montado? (para avisar que vai abrir em vez de criar)"""
    p = Path(path)
    return (p / DB_NAME).exists() or (p / MARKER).exists()


def suggest_name(path) -> str:
    p = Path(path)
    return read_marker(p).get("name") or p.name or str(p)


# ------------------------------------------------------------------ registro

def _raw(settings) -> list[dict]:
    got = settings.get("locations", []) or []
    return [d for d in got if isinstance(d, dict) and d.get("path")]


def _save(settings, items: list[dict]) -> None:
    settings.set("locations", items)


def _slug(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "local").lower()).strip("-") or "local"
    out, n = base, 2
    while out in taken or out == DEFAULT_ID:
        out, n = f"{base}-{n}", n + 1
    return out


def default_location(paths) -> Location:
    return Location(DEFAULT_ID, DEFAULT_NAME, Path(paths.data), "default")


def central_location(settings, paths) -> Location | None:
    """O servidor do grupo, quando este computador é cliente (os arquivos abertos ficam no cache)."""
    if str(settings.get("central.mode", "local") or "local") != "client":
        return None
    url = str(settings.get("central.url", "") or "")
    return Location(CENTRAL_ID, CENTRAL_NAME + (f" ({url.split('://')[-1]})" if url else ""),
                    Path(paths.data) / "CacheCentral", "central")


def all_locations(settings, paths) -> list[Location]:
    """O banco deste computador primeiro, depois os outros na ordem em que foram adicionados.
    No modo cliente, o servidor do grupo vem antes de todos."""
    out = [default_location(paths)]
    c = central_location(settings, paths)
    if c is not None:
        out.insert(0, c)
    for d in _raw(settings):
        p = Path(d["path"])
        out.append(Location(str(d.get("id") or p.name), str(d.get("name") or p.name), p,
                            str(d.get("kind") or guess_kind(p))))
    return out


def find(settings, paths, loc_id: str) -> Location | None:
    for loc in all_locations(settings, paths):
        if loc.id == loc_id:
            return loc
    return None


def add(settings, path, name: str = "") -> Location:
    """Acrescenta a pasta à lista (e deixa a pasta pronta). Se já estiver na lista, devolve a existente."""
    p = Path(path).expanduser().resolve()
    items = _raw(settings)
    for d in items:
        if Path(d["path"]) == p:
            return Location(str(d["id"]), str(d["name"]), p, str(d.get("kind") or guess_kind(p)))
    name = name or suggest_name(p)
    prepare(p, name)
    loc = Location(_slug(name, {str(d.get("id")) for d in items}), name, p, guess_kind(p))
    items.append({"id": loc.id, "name": loc.name, "path": str(p), "kind": loc.kind})
    _save(settings, items)
    return loc


def remove(settings, loc_id: str) -> None:
    """Tira da lista. Os arquivos e o índice continuam na pasta, intactos."""
    _save(settings, [d for d in _raw(settings) if str(d.get("id")) != loc_id])
    if settings.get("locations_current", "") == loc_id:
        settings.set("locations_current", DEFAULT_ID)


def rename(settings, loc_id: str, name: str) -> None:
    items = _raw(settings)
    for d in items:
        if str(d.get("id")) == loc_id:
            d["name"] = name
            write_marker(Path(d["path"]), name)
    _save(settings, items)


def current_id(settings) -> str:
    return str(settings.get("locations_current", DEFAULT_ID) or DEFAULT_ID)


def set_current(settings, loc_id: str) -> None:
    settings.set("locations_current", loc_id)


def current(settings, paths) -> Location:
    """O local ativo; se ele sumiu (HD desconectado), volta para o banco deste computador."""
    loc = find(settings, paths, current_id(settings))
    if loc is None or not loc.online():
        return default_location(paths)
    return loc
