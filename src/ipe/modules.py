"""Módulos que se ligam e desligam (0.84) — primeira etapa do plano de módulos.

Pedido dele (0.36): separar o programa em módulos (MN, RM, MG, impressão…) e escolher o que usar.
Esta etapa é o "caminho 1" do plano (`docs/projeto/plano-modulos.md`): **um pacote só**, módulos ligados
ou desligados em Preferências ▸ Módulos. Não economiza disco; tira da tela e para os serviços do que
não se usa.

Regra que vale para todos: **o dado fica, a ferramenta some**. Desligar a medicina nuclear não apaga
exame de MN — ele continua abrindo como imagem comum; só os botões de MN somem. Religar devolve tudo.
"""
from __future__ import annotations

CHAVE = "modules.disabled"        # lista dos desligados (vazia = tudo ligado, que é o padrão)

#: id -> (nome na tela, o que some quando desliga)
MODULOS: dict[str, tuple[str, str]] = {
    "mn": ("Medicina nuclear",
           "Botões de MN (análises, renograma, tireoide, ossos…) e da fusão PET/CT no visualizador."),
    "mamografia": ("Mamografia",
                   "Protocolos de mamografia ao abrir o exame (hanging, etapas, quadrantes, tomossíntese) "
                   "e a densidade mamária. O exame abre como imagem comum."),
    "3d": ("3D", "Botão 3D (volume, superfície, escultura) no visualizador. O MPR continua."),
    "rm_tc": ("RM/TC avançado", "Botão da dinâmica (curvas, mapas cinéticos, lesão de mama) no visualizador."),
    "impressao": ("Impressão recebida",
                  "Servidores de impressão DICOM (as portas param de receber), lista de impressões, "
                  "configurações de impressão, filme automático do ultrassom e limpeza da lista. "
                  "O compositor de filmes e o painel continuam."),
}


def desligados(settings) -> set[str]:
    if settings is None:
        return set()
    return {m for m in (settings.get(CHAVE, []) or []) if m in MODULOS}


def ligado(settings, modulo: str) -> bool:
    return modulo not in desligados(settings)


def definir(settings, ligados: dict[str, bool]) -> None:
    settings.set(CHAVE, sorted(m for m, on in ligados.items() if m in MODULOS and not on))
