"""0.100.8: retomar a sessão depois de uma queda.

Enquanto o programa está aberto, `sessao.json` (na pasta das configurações) diz quais exames estão abertos — em
qual janela ficou cada um não importa: reabrir põe cada um onde o programa poria —, qual estava na frente e as
séries de cada um. Fechar o programa direito apaga a marca de "aberto". Se o programa abre e acha a marca, a última
vez acabou numa queda (ou o computador desligou): ele oferece reabrir o que estava aberto. O estado de cada análise
(medidas, layout, janela) volta pelo "estado da análise" que o exame já guarda — e que, agora, também é guardado de
tempos em tempos, e não só ao fechar.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

ARQUIVO = "sessao.json"
CHAVE_RETOMAR = "sessao.retomar"        # "perguntar" (padrão), "sempre" ou "nunca"
INTERVALO_ESTADO_S = 120                # de quanto em quanto tempo o estado da análise é guardado


class Sessao:
    def __init__(self, pasta: Path):
        self.arquivo = Path(pasta) / ARQUIVO
        self.anterior = self._ler()        # o que a última vez deixou (antes desta abrir)

    def _ler(self) -> dict:
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:  # noqa: BLE001 - arquivo pela metade (a queda foi no meio da gravação)
            log.warning("sessão anterior ilegível", exc_info=True)
            return {}

    def caiu(self) -> bool:
        """A última vez terminou sem fechar direito, com exame aberto."""
        a = self.anterior
        return bool(a.get("aberta")) and bool(a.get("exames")) and a.get("pid") != os.getpid()

    def exames_da_queda(self) -> list[dict]:
        return list(self.anterior.get("exames") or []) if self.caiu() else []

    def gravar(self, exames: list[dict], ativo: str | None) -> None:
        dados = {"aberta": True, "pid": os.getpid(), "atualizado": time.time(), "exames": exames, "ativo": ativo}
        self._escrever(dados)

    def encerrar(self) -> None:
        """Fechou direito: nada a retomar da próxima vez."""
        self._escrever({"aberta": False, "pid": os.getpid(), "atualizado": time.time(), "exames": []})

    def esquecer_a_queda(self) -> None:
        self.anterior = {}

    def _escrever(self, dados: dict) -> None:
        try:
            self.arquivo.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.arquivo.with_suffix(".tmp")
            tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.arquivo)       # nunca fica um arquivo pela metade
        except Exception:  # noqa: BLE001 - a sessão não pode atrapalhar o trabalho
            log.debug("não consegui gravar a sessão", exc_info=True)


def descrever(exames: list[dict], limite: int = 6) -> str:
    linhas = [f"• {e.get('titulo') or e.get('study')}" for e in exames[:limite]]
    if len(exames) > limite:
        linhas.append(f"• e mais {len(exames) - limite}")
    return "\n".join(linhas)
