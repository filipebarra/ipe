"""Estado do exame na lista de trabalho (0.99.63, PV 32 = AW gestão): não lido, em leitura, revisado, urgente.

Sai sozinho do que o banco já sabe — e se troca à mão (botão direito ▸ Estado do exame; "Automático" volta):

- **Revisado**: tem laudo assinado (ou retificado).
- **Urgente**: sem laudo assinado e com prioridade urgente ou emergência (a da regra ou a trocada à mão, 0.99.52).
- **Em leitura**: alguém abriu o exame, ou há um rascunho de laudo.
- **Não lido**: nunca aberto e sem laudo.

O estado à mão serve para o que o automático não sabe: o exame revisado sem laudo (segunda leitura, reunião), o que
voltou para leitura, o urgente que a regra não pegou.
"""
from __future__ import annotations

ESTADOS = {"nao_lido": "Não lido", "em_leitura": "Em leitura", "revisado": "Revisado", "urgente": "Urgente"}
ORDEM = {"urgente": 0, "nao_lido": 1, "em_leitura": 2, "revisado": 3}
CORES = {"urgente": (210, 60, 40), "nao_lido": (60, 120, 220), "em_leitura": (200, 140, 0), "revisado": (60, 150, 70)}
ASSINADOS = ("assinado", "retificado")
URGENTES = ("urgente", "emergencia")


def automatico(report: str = "", prioridade: str = "", unread: bool = True) -> str:
    if (report or "") in ASSINADOS:
        return "revisado"
    if (prioridade or "") in URGENTES:
        return "urgente"
    if not unread or (report or "") == "rascunho":
        return "em_leitura"
    return "nao_lido"


def estado(manual: str = "", report: str = "", prioridade: str = "", unread: bool = True) -> str:
    return manual if manual in ESTADOS else automatico(report, prioridade, unread)


def rotulo(codigo: str) -> str:
    return ESTADOS.get(codigo, codigo or "")
