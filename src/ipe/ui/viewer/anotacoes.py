"""Anotações da tela do visualizador em quatro níveis (0.99.9).

Pedido dele: *"anotações que aparecem na tela do viewer: quero poder editar (selecionar o que
colocar) no menu de configurações. E no viewer quero poder escolher (completa, parcial 1, parcial 2,
ausente). Tudo isso eu configuro no menu de configurações."*

- O catálogo (`ITENS`) é tudo o que o quadro escreve ou desenha por cima da imagem, item a item.
- Completa, Parcial 1 e Parcial 2 são **listas de itens** que ele escolhe em Preferências ▸
  Anotações. Ausente não mostra nada — é a imagem limpa (as medidas também saem: quem quer a
  imagem limpa quer a imagem limpa; elas voltam ao trocar de nível).
- O nível em uso vale para todos os quadros e fica guardado: trocar a cada exame seria trabalho à
  toa. Ele troca pelo botão "Anotações" da barra, pelo botão direito do quadro ou pela ação
  "Anotações: próximo nível" (sem tecla de fábrica; a tecla é escolha dele).
- Os selos **graves** (mamografia comprimida com perdas, Modality LUT não aplicada) aparecem em
  qualquer nível menos o Ausente, mesmo que a lista dele não tenha o item: são segurança (0.99.22).
- Ctrl+C copia o quadro **como está na tela**, então o nível também decide o que vai na cópia.
"""
from __future__ import annotations

#: (chave, nome nas preferências, onde fica)
ITENS: list[tuple[str, str, str]] = [
    ("nome", "Nome do paciente", "Canto superior esquerdo"),
    ("id", "ID do paciente", "Canto superior esquerdo"),
    ("sexo_idade", "Sexo, idade e nascimento", "Canto superior esquerdo"),
    ("instituicao", "Instituição", "Canto superior esquerdo"),
    ("exame", "Descrição do exame", "Canto superior direito"),
    ("serie", "Série (clicável: trocar de série)", "Canto superior direito"),
    ("fase_nome", "Nome da fase da dinâmica", "Canto superior direito"),
    ("data", "Data do exame", "Canto superior direito"),
    ("imagem", "Número da imagem / corte da tomo", "Canto inferior esquerdo"),
    ("fase_cardiaca", "Fase cardíaca (4D)", "Canto inferior esquerdo"),
    ("orientacao", "Giro e espelhamento aplicados", "Canto inferior esquerdo"),
    ("posicao", "Posição do corte (mm)", "Canto inferior esquerdo"),
    ("espessura", "Espessura do corte", "Canto inferior esquerdo"),
    ("escala", "De onde vem a escala (calibração)", "Canto inferior esquerdo"),
    ("processamento", "Processamento aplicado (DSA, filtro, fusão)", "Canto inferior esquerdo"),
    ("plano", "Plano (axial, coronal, sagital…)", "Canto inferior direito"),
    ("fase", "Fase da dinâmica (clicável)", "Canto inferior direito"),
    ("janela", "Janela e nível (W/L)", "Canto inferior direito"),
    ("fov", "FOV e zoom", "Canto inferior direito"),
    ("selos", "Selos de integridade (compressão com perdas, LUT…)", "Alto do quadro"),
    ("letras", "Letras de orientação nas bordas", "Sobre a imagem"),
    ("medidas", "Medidas, setas e textos desenhados", "Sobre a imagem"),
    ("medidas_aviso", "Aviso de imagens com medida", "Sobre a imagem"),
    ("chave", "Estrela da imagem-chave", "Sobre a imagem"),
    ("barra_cores", "Barra da escala de cores", "Sobre a imagem"),
    ("calibrada", "Aviso \"Medidas calibradas\"", "Sobre a imagem"),
    ("tomo", "Indicador de profundidade da tomossíntese", "Sobre a imagem"),
    ("sincronia", "Corrente da sincronia (grupo)", "Sobre a imagem"),
    ("barra_posicao", "Barra de posição na pilha", "Sobre a imagem"),
    ("mouse", "Ícone do mouse (o que cada botão faz)", "Sobre a imagem"),
]
CHAVES = [k for k, _n, _g in ITENS]

NIVEIS: list[tuple[str, str]] = [("completa", "Completa"), ("parcial1", "Parcial 1"),
                                 ("parcial2", "Parcial 2"), ("ausente", "Ausente")]
NOME_DO_NIVEL = dict(NIVEIS)
EDITAVEIS = ("completa", "parcial1", "parcial2")

_DADOS_DO_PACIENTE = {"nome", "id", "sexo_idade", "instituicao", "data"}
#: de fábrica: completa = tudo; parcial 1 = tudo menos os dados do paciente (aula, reunião);
#: parcial 2 = o mínimo para ler (imagem, série, janela, orientação e as medidas)
FABRICA: dict[str, list[str]] = {
    "completa": list(CHAVES),
    "parcial1": [k for k in CHAVES if k not in _DADOS_DO_PACIENTE],
    "parcial2": ["serie", "fase_nome", "imagem", "fase", "janela", "selos", "letras", "medidas", "chave",
                 "barra_cores", "tomo"],
}


def nivel_atual(settings) -> str:
    n = str((settings.get("viewer.anotacoes_nivel", "completa") if settings is not None else "")
            or "completa")
    return n if n in NOME_DO_NIVEL else "completa"


def itens_do_nivel(settings, nivel: str | None = None) -> set[str]:
    nivel = nivel or nivel_atual(settings)
    if nivel == "ausente":
        return set()
    gravado = settings.get("viewer.anotacoes_itens", None) if settings is not None else None
    if isinstance(gravado, dict) and isinstance(gravado.get(nivel), list):
        return {k for k in gravado[nivel] if k in CHAVES}
    return set(FABRICA.get(nivel, CHAVES))


def todos_os_niveis(settings) -> dict[str, list[str]]:
    """Os itens de cada nível editável, na ordem do catálogo (para as preferências)."""
    return {n: [k for k in CHAVES if k in itens_do_nivel(settings, n)] for n in EDITAVEIS}


def proximo(nivel: str) -> str:
    chaves = [k for k, _ in NIVEIS]
    return chaves[(chaves.index(nivel) + 1) % len(chaves)] if nivel in chaves else "completa"
