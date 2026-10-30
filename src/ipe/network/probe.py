"""Teste de rede e estimativa do tempo de download, para decidir entre esperar o exame baixar
ou abrir enquanto baixa (streaming).

O programa aprende com os downloads já feitos: guarda, por nó, a velocidade média (MB/s) e o
tamanho médio de cada imagem, e usa isso para estimar o próximo exame. O teste rápido (C-ECHO)
mede só a latência — serve para saber se o nó responde e se a rede está lenta.
"""

from __future__ import annotations

import time

# tamanho típico de uma imagem por modalidade (MB), quando ainda não há histórico do nó
MB_PER_IMAGE = {"MG": 12.0, "DBT": 20.0, "CR": 8.0, "DX": 8.0, "XA": 2.0, "US": 0.6, "MR": 0.25,
                "CT": 0.52, "PT": 0.14, "NM": 0.5, "OT": 0.5}
DEFAULT_MB_PER_IMAGE = 0.6
SLOW_MS = 150.0                 # latência acima disto = rede lenta
DEFAULT_SUGGEST_SECONDS = 20


def _stats(settings) -> dict:
    return dict(settings.get("network.stats", {}) or {}) if settings is not None else {}


def node_stats(settings, node_id) -> dict:
    return dict(_stats(settings).get(str(node_id), {}))


def learn(settings, node_id, mb: float, seconds: float, images: int) -> dict:
    """Guarda o que este download mostrou sobre o nó (média móvel)."""
    if settings is None or not node_id or seconds <= 0 or mb <= 0:
        return {}
    all_stats = _stats(settings)
    cur = dict(all_stats.get(str(node_id), {}))
    mbps = mb / seconds
    per_img = mb / images if images else cur.get("mb_per_image", 0)
    cur["mbps"] = round(mbps if not cur.get("mbps") else 0.6 * cur["mbps"] + 0.4 * mbps, 3)
    if per_img:
        cur["mb_per_image"] = round(per_img if not cur.get("mb_per_image")
                                    else 0.6 * cur["mb_per_image"] + 0.4 * per_img, 4)
    cur["at"] = time.strftime("%Y-%m-%d %H:%M")
    all_stats[str(node_id)] = cur
    settings.set("network.stats", all_stats)
    return cur


def learn_latency(settings, node_id, ms: float) -> dict:
    if settings is None or not node_id:
        return {}
    all_stats = _stats(settings)
    cur = dict(all_stats.get(str(node_id), {}))
    cur["ms"] = round(ms, 1)
    cur["at"] = time.strftime("%Y-%m-%d %H:%M")
    all_stats[str(node_id)] = cur
    settings.set("network.stats", all_stats)
    return cur


def size_estimate(settings, node_id, images: int, modalities: str = "") -> float:
    """Tamanho provável do exame em MB."""
    per = node_stats(settings, node_id).get("mb_per_image")
    if not per:
        mods = [m.strip().upper() for m in (modalities or "").replace("/", "\\").split("\\") if m.strip()]
        per = max([MB_PER_IMAGE.get(m, DEFAULT_MB_PER_IMAGE) for m in mods] or [DEFAULT_MB_PER_IMAGE])
    return max(0.0, images * per)


def estimate(settings, node_id, images: int, modalities: str = "") -> dict:
    """Estimativa do download: {mb, mbps, seconds, known}. `known` = já houve download deste nó."""
    st = node_stats(settings, node_id)
    mb = size_estimate(settings, node_id, images, modalities)
    mbps = float(st.get("mbps") or 0)
    known = bool(st.get("mbps"))
    if not mbps:
        mbps = 2.0 if float(st.get("ms") or 0) <= SLOW_MS else 0.7    # chute pela latência
    seconds = mb / mbps if mbps else 0.0
    return {"mb": mb, "mbps": mbps, "seconds": seconds, "known": known, "ms": st.get("ms")}


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def fmt_size(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def stream_enabled(node: dict | None, settings) -> bool:
    """O nó abre enquanto baixa? (None no nó = usa o padrão das preferências)"""
    if node is not None and node.get("stream_open") is not None:
        return bool(node["stream_open"])
    return bool(settings.get("network.stream_default", False)) if settings is not None else False


def stream_externo(node: dict | None, settings) -> bool:
    """Chamada externa (RIS, link, API): abre enquanto baixa, sem perguntar a ninguém.

    Quem chama de fora não está na frente da tela para responder caixa de diálogo, e o
    exame pedido pelo RIS costuma ser o que o médico quer ver agora. Por isso o padrão
    aqui é o contrário do padrão da busca manual. A opção do nó, quando o usuário marcou
    uma, continua mandando.
    """
    if node is not None and node.get("stream_open") is not None:
        return bool(node["stream_open"])
    if settings is None:
        return True
    return bool(settings.get("network.stream_external", True))


def should_ask(settings, seconds: float) -> bool:
    if settings is None or not settings.get("network.stream_ask", True):
        return False
    limit = float(settings.get("network.stream_suggest_seconds", DEFAULT_SUGGEST_SECONDS) or 0)
    return limit > 0 and seconds >= limit


def summary(settings, node_id) -> str:
    st = node_stats(settings, node_id)
    if not st:
        return "Ainda sem medidas deste nó."
    parts = []
    if st.get("ms"):
        parts.append(f"resposta {st['ms']:.0f} ms" + ("  (lenta)" if st["ms"] > SLOW_MS else ""))
    if st.get("mbps"):
        parts.append(f"{st['mbps']:.1f} MB/s")
    if st.get("mb_per_image"):
        parts.append(f"{st['mb_per_image']:.2f} MB por imagem")
    return "; ".join(parts) + (f"  (medido em {st['at']})" if st.get("at") else "")
