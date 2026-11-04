"""As IAs que seguem o contrato comum (0.99.46): um módulo por ferramenta, sem um ramo novo em cada
lugar do programa para cada IA nova.

O módulo de uma ferramenta tem:
`FERRAMENTA`, `TITULO`, `MIN_CORTES`, `MODALIDADES`, `MOTIVO_MODALIDADE`, `CHAVE_SAIDA`, `CHAVE_AUTO`,
`CHAVE_DESTINOS`, `config(settings, chave)`, `exame_serve(info, settings)`,
`escolher_serie(repo, study_uid, settings)`, `ja_feita(repo, study_uid)`, `tarefas(modalidade, settings)`,
`calcular(trabalho, rotulos, settings)`, `gravar(trabalho, res, versao, db, storage, repo=, settings=)`,
`resumo(res)`, `n_itens(res)`, `mensagem(res, minutos)`.

O automático da chegada (`automation/engine.py`), a segmentação pedida à mão (`ui/segmentacao.py`) e a
aba de CAD/IA usam só isto.
"""
from __future__ import annotations

import importlib

#: tipo -> módulo
GENERICAS = {
    "nodulos": "ipe.ai.nodulos",
    "composicao": "ipe.ai.composicao",          # 0.99.47
}


def modulo(tipo: str):
    nome = GENERICAS.get(tipo)
    return importlib.import_module(nome) if nome else None


def tipos() -> list[str]:
    return list(GENERICAS)


def preparar_trabalho(t, mod) -> None:
    """Configura um `totalseg.Trabalho` para a ferramenta."""
    t.tarefas_proprias = mod.tarefas
    t.min_cortes = mod.MIN_CORTES
    t.modalidades = tuple(mod.MODALIDADES)
    t.motivo_modalidade = mod.MOTIVO_MODALIDADE


def rodar_conta(t, mod, settings):
    """Depois do trabalhador: lê os rótulos e faz a conta. Devolve (resultado, versão)."""
    rotulos, versao, _s = t.ler_rotulos()
    res = mod.calcular(t, rotulos, settings)
    if getattr(res, "versao", None) == "" and versao:
        res.versao = versao
    return res, versao


def gravar(t, mod, res, versao, db, storage, repo, settings) -> dict:
    saida = mod.gravar(t, res, versao, db, storage, repo=repo, settings=settings)
    saida[mod.CHAVE_SAIDA] = res
    saida["ferramenta"] = mod.FERRAMENTA
    saida["series_uid"] = t.series_uid
    return saida
