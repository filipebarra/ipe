"""0.100.120: Configurações ▸ Banco de dados ▸ Limpar o cache do Ipê… — a parte que não depende de tela.

O que o Ipê guarda "de passagem" e pode ser refeito sem perder nada:
- a **memória de imagens** do visualizador (quadros já decodificados);
- os **exames baixados do servidor** (modo cliente): o servidor continua com tudo e baixa de novo ao abrir;
- as **pastas temporárias esquecidas** (dv_*, ipe_*) que as IAs e os laudos deixam quando o programa fecha no meio;
- as **atualizações já baixadas** (o instalador de cada versão).
Nunca: o banco, o Storage deste computador, a lixeira, as configurações, os modelos de IA.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

PREFIXOS_TEMP = ("dv_", "ipe_", "dicomviewer-corrigido-")
#: só as pastas paradas há mais que isto: uma IA pode estar rodando agora com a pasta dela
IDADE_MINIMA_S = 6 * 3600


def tamanho(pasta: Path) -> int:
    """Bytes de uma pasta ou arquivo (sem seguir atalhos)."""
    try:
        if pasta.is_symlink():
            return 0
        if pasta.is_file():
            return pasta.stat().st_size
        return sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file() and not f.is_symlink())
    except OSError:
        return 0


def pastas_temporarias(idade_min_s: float = IDADE_MINIMA_S, base: Path | None = None) -> list[Path]:
    base = Path(base) if base is not None else Path(tempfile.gettempdir())
    agora = time.time()
    out = []
    try:
        for p in base.iterdir():
            if not p.name.startswith(PREFIXOS_TEMP) or p.is_symlink() or not p.is_dir():
                continue
            try:
                if agora - p.stat().st_mtime >= idade_min_s:
                    out.append(p)
            except OSError:
                continue
    except OSError:
        pass
    return sorted(out)


def atualizacoes_baixadas(paths) -> list[Path]:
    pasta = Path(paths.data) / "Atualizacoes"
    try:
        return sorted(p for p in pasta.iterdir() if not p.is_symlink()) if pasta.is_dir() else []
    except OSError:
        return []


def apagar(itens: list[Path]) -> tuple[int, int, int]:
    """(apagados, bytes liberados, falhas). Cada item é uma pasta ou arquivo."""
    n = falhas = livres = 0
    for p in itens:
        tam = tamanho(p)
        try:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
            n += 1
            livres += tam
        except OSError:
            log.warning("limpar cache: não apaguei %s", p, exc_info=True)
            falhas += 1
    return n, livres, falhas


def exames_do_cache(repo) -> list:
    """Exames baixados do servidor que estão neste computador (só no modo cliente)."""
    if not getattr(repo, "remote", False) or not hasattr(repo, "cache_usage"):
        return []
    return list(repo.cache_usage()[1])


def apagar_exame_do_cache(repo, study_uid: str) -> str:
    """Tira um exame do cache **só se o servidor tiver tudo o que há aqui**. Devolve "ok", "so_aqui" (o servidor não
    tem tudo: fica), "protegido" (cadeado) ou "erro"."""
    try:
        remoto = {s.series_uid: s.num_images for s in repo.client.rpc("series_for_study", study_uid)}
        local = {s.series_uid: s.num_images for s in repo.local.series_for_study(study_uid)}
    except Exception:  # noqa: BLE001
        log.warning("limpar cache: não consegui conferir %s no servidor", study_uid, exc_info=True)
        return "erro"
    if not remoto or any(remoto.get(u, 0) < n for u, n in local.items()):
        return "so_aqui"
    try:
        repo.remove_cached(study_uid)
    except PermissionError:
        return "protegido"
    except Exception:  # noqa: BLE001
        log.warning("limpar cache: erro ao apagar %s", study_uid, exc_info=True)
        return "erro"
    return "ok"


def humano(n: float) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} GB"
