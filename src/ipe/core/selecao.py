"""Onde uma análise roda: escolher as imagens por aquilo que o DICOM diz.

Cada serviço tem aparelho e protocolo diferentes. "Mamografia 2D" num lugar é
`ViewPosition = CC`; em outro é uma descrição de série escrita à mão; em outro a incidência só
aparece no texto. Em vez de adivinhar no código, o usuário monta a regra — e monta escolhendo
entre **os valores que existem no acervo dele**, não digitando de memória.

Uma `Selecao` é um conjunto de critérios ligados por **E**. Várias seleções para a mesma análise
são ligadas por **OU**: é como se diz "as CC e as MLO", ou "o protocolo do aparelho antigo também".

O motor é burro de propósito: recebe um dicionário de atributos e responde sim ou não. Quem sabe
de onde vem cada atributo é quem chama — o banco, para filtrar barato, ou o arquivo aberto, para
decidir o que só está lá dentro. Atributo que o chamador não tem **não combina**, e `faltando()`
diz qual seria preciso: é a diferença entre "não serve" e "não sei ainda".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: campos que uma regra pode olhar, com o rótulo que aparece na tela
CAMPOS = {
    "modalidade": "Modalidade",
    "descricao": "Descrição da série",
    "vista": "Incidência",
    "lado": "Lado",
    "parte": "Parte do corpo",
    "aparelho": "Aparelho",
    "estacao": "Estação",
    "classe": "Tipo de imagem (SOP Class)",
    "quadros": "Quadros na imagem",
    "apresentacao": "Processamento",
}

#: os que o banco já sabe responder, sem abrir arquivo
DO_BANCO = ("modalidade", "descricao", "lado", "parte", "aparelho", "estacao")

OPERADORES = {
    "contem": "contém",
    "nao_contem": "não contém",
    "igual": "é igual a",
    "diferente": "é diferente de",
    "comeca": "começa com",
    "um_de": "é um de (lista separada por vírgula)",
    "contem_um_de": "contém um de (lista separada por vírgula)",
    "regex": "casa com a expressão",
}

#: como cada critério se liga ao anterior. O **E** amarra mais forte que o **OU**, como em
#: praticamente toda linguagem: "A e B ou C" é "(A e B) ou C". Sem essa regra fixa, uma lista de
#: critérios misturados seria ambígua — e regra ambígua em cima de imagem de paciente não serve.
LIGACOES = {"e": "E também", "ou": "OU então"}


def _texto(v) -> str:
    return " ".join(str(v or "").split()).strip().lower()


@dataclass
class Criterio:
    campo: str = "descricao"
    operador: str = "contem"
    valor: str = ""
    ligacao: str = "e"          # como se liga ao critério anterior; ignorado no primeiro

    def combina(self, atributos: dict) -> bool:
        if self.campo not in atributos:
            return False
        alvo, valor = _texto(atributos.get(self.campo)), _texto(self.valor)
        if self.operador == "contem":
            return valor in alvo
        if self.operador == "nao_contem":
            return valor not in alvo
        if self.operador == "igual":
            return alvo == valor
        if self.operador == "diferente":
            return alvo != valor
        if self.operador == "comeca":
            return alvo.startswith(valor)
        if self.operador == "um_de":
            return alvo in {_texto(x) for x in str(self.valor).split(",") if x.strip()}
        if self.operador == "contem_um_de":
            return any(_texto(x) in alvo for x in str(self.valor).split(",") if x.strip())
        if self.operador == "regex":
            try:
                return re.search(self.valor, str(atributos.get(self.campo) or ""),
                                 re.IGNORECASE) is not None
            except re.error:
                return False                      # expressão inválida não derruba a análise
        return False

    def texto(self, tr=None) -> str:
        """Frase legível. `tr` é o tradutor: o motor guarda o texto em português e quem mostra
        traduz — mesma divisão do resto do programa (o motor não importa `i18n`).

        Montado por junção, não por f-string: "{} {} “{}”" seria um padrão genérico demais para o
        catálogo de idiomas e sequestraria outros textos.
        """
        t = tr or (lambda s: s)
        return " ".join([t(CAMPOS.get(self.campo, self.campo)),
                         t(OPERADORES.get(self.operador, self.operador)),
                         "\u201c" + str(self.valor) + "\u201d"])

    def to_dict(self) -> dict:
        return {"campo": self.campo, "operador": self.operador, "valor": self.valor,
                "ligacao": self.ligacao}

    @staticmethod
    def from_dict(d: dict) -> Criterio:
        campos = Criterio.__dataclass_fields__
        return Criterio(**{k: v for k, v in (d or {}).items() if k in campos})


def grupos(criterios: list) -> list:
    """Quebra a lista em grupos de **E**, separados pelos critérios marcados como **OU**.

    "A e B ou C e D" vira [[A, B], [C, D]]: o E amarra mais forte, e o resultado é o OU dos grupos.
    """
    saida: list[list] = []
    for c in criterios:
        if not saida or c.ligacao == "ou":
            saida.append([c])
        else:
            saida[-1].append(c)
    return saida


@dataclass
class Selecao:
    nome: str = "Nova seleção"
    ativa: bool = True
    criterios: list = field(default_factory=list)

    def combina(self, atributos: dict) -> bool:
        if not self.ativa or not self.criterios:
            return False
        return any(all(c.combina(atributos) for c in g) for g in grupos(self.criterios))

    def parcial(self, atributos: dict) -> bool:
        """Combina **pelo que dá para saber agora**, ignorando os critérios sem resposta.

        Serve para a prévia e para filtrar barato no banco: devolve o *limite de cima* — todo item
        que passa aqui ainda vai ser conferido inteiro quando o arquivo abrir. Nunca é usado para
        decidir se a análise roda: para isso vale `combina`, que exige tudo.
        """
        if not self.ativa or not self.criterios:
            return False
        return any(all(c.combina(atributos) for c in g if c.campo in atributos)
                   for g in grupos(self.criterios))

    def faltando(self, atributos: dict) -> list:
        """Campos que esta regra olha e o chamador não trouxe."""
        return sorted({c.campo for c in self.criterios if c.campo not in atributos})

    def texto(self, tr=None) -> str:
        """A frase da regra, na ordem da tabela, usando os próprios rótulos de ligação.

        Nada de juntar com `" e "` ou `", ou "`: texto que começa com espaço e minúscula não é
        extraído para o catálogo, e sairia em português num programa em inglês. Os rótulos de
        `LIGACOES` são extraídos e traduzidos — então a frase se monta com eles.
        """
        t = tr or (lambda s: s)
        if not self.criterios:
            return t("(sem critério: não pega nada)")
        partes = []
        for i, c in enumerate(self.criterios):
            if i:
                partes.append(t(LIGACOES.get(c.ligacao, LIGACOES["e"])).lower())
            partes.append(c.texto(tr))
        return " ".join(partes)

    def to_dict(self) -> dict:
        return {"nome": self.nome, "ativa": self.ativa,
                "criterios": [c.to_dict() for c in self.criterios]}

    @staticmethod
    def from_dict(d: dict) -> Selecao:
        d = d or {}
        return Selecao(nome=d.get("nome", "Nova seleção"), ativa=bool(d.get("ativa", True)),
                       criterios=[Criterio.from_dict(c) for c in d.get("criterios", [])])


# --------------------------------------------------------------------- guardar
def chave(analise: str) -> str:
    return f"analise.{analise}.selecoes"


def carregar(settings, analise: str) -> list:
    bruto = settings.get(chave(analise), None)
    if bruto is None:
        return [Selecao.from_dict(d) for d in PADROES.get(analise, [])]
    return [Selecao.from_dict(d) for d in bruto]


def salvar(settings, analise: str, selecoes: list) -> None:
    settings.set(chave(analise), [s.to_dict() for s in selecoes])
    settings.save()


def restaurar_padrao(settings, analise: str) -> list:
    settings.set(chave(analise), None)
    settings.save()
    return carregar(settings, analise)


# --------------------------------------------------------------------- usar
def escolhe(selecoes: list, atributos: dict) -> Selecao | None:
    """A primeira seleção que combina — ou None. Várias seleções são um OU."""
    for s in selecoes:
        if s.combina(atributos):
            return s
    return None


def filtrar(selecoes: list, itens, atributos_de, parcial: bool = False) -> list:
    """Os itens que alguma seleção pega. Com `parcial`, o limite de cima (ver `Selecao.parcial`)."""
    def pega(i):
        a = atributos_de(i)
        return any(s.parcial(a) for s in selecoes) if parcial else escolhe(selecoes, a) is not None
    return [i for i in itens if pega(i)]


def campos_usados(selecoes: list) -> list:
    return sorted({c.campo for s in selecoes for c in s.criterios})


def precisa_do_arquivo(selecoes: list) -> bool:
    """Se alguma regra olha campo que só existe dentro do arquivo, não dá para filtrar só no banco."""
    return any(c not in DO_BANCO for c in campos_usados(selecoes))


# --------------------------------------------------------------------- padrões
#: o que já vem pronto, por análise. O usuário edita; `restaurar_padrao` volta para cá.
#:
#: Está **vazio de propósito**. A densidade mamária usou este mecanismo na 0.37 e saiu dele na
#: 0.39: na tela, quem escolhe as imagens é o médico, pondo-as no quadro. O motor continua aqui,
#: com os testes, para a próxima análise que precisar escolher imagem no acervo inteiro — que é
#: onde a regra faz falta de verdade (varrer o banco sem filtro é caro).
PADROES: dict = {}
