"""Roteiros de medida guiada (0.99.14): o programa pede as medidas numa ordem, cada uma no plano
certo, e faz a conta no fim. Sem Qt — a janela é `ui/viewer/roteiro_painel.py`.

Primeiro uso (etapa 1 da neuro): MRPI, MRPI 2.0, índice de Evans e ângulo calosal. O mesmo motor
vai servir à cefalometria do cavum (etapa 1b).

Um **passo** é uma medida: a ferramenta que se usa (régua, área, ângulo), o plano em que ela deve
ser feita e quantas vezes (o 3º ventrículo é a média de três). Um **roteiro** é a lista de passos
e a conta que sai deles. Os valores de referência entram como **texto ao lado do número**, com a
fonte — o programa não classifica ninguém.

Medidas:
- MRPI = (área da ponte ÷ área do mesencéfalo) × (largura do pedúnculo cerebelar médio ÷ largura do
  pedúnculo cerebelar superior); as duas áreas no sagital mediano, o médio no sagital e o superior no
  coronal. Com os dois lados medidos, vale a média.
- MRPI 2.0 = MRPI × (largura do 3º ventrículo ÷ largura dos cornos frontais), no axial (plano AC-PC);
  o 3º ventrículo é a média de três medidas.
- Índice de Evans = maior largura dos cornos frontais ÷ maior diâmetro interno do crânio, no mesmo
  corte axial.
- Ângulo calosal: no coronal perpendicular ao plano AC-PC, na altura da comissura posterior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

#: ferramenta do visualizador -> tipo de anotação que ela cria
FERRAMENTA_PARA_TIPO = {"measure": ("line",), "polygon": ("polygon",), "angle": ("angle",),
                        "ellipse": ("ellipse",)}
UNIDADE = {"measure": "mm", "polygon": "mm²", "ellipse": "mm²", "angle": "°"}
NOME_DA_FERRAMENTA = {"measure": "régua", "polygon": "ROI poligonal (contorno)",
                      "ellipse": "ROI elíptica", "angle": "ângulo"}


@dataclass(frozen=True)
class Passo:
    id: str
    nome: str
    ferramenta: str                  # "measure" | "polygon" | "angle"
    plano: str                       # "Sagital" | "Coronal" | "Axial" | "" (qualquer)
    instrucao: str
    vezes: int = 1                   # quantas medidas (média) — ex.: o 3º ventrículo
    opcional: bool = False
    max_vezes: int = 0               # aceita até N (média): 2 = lado direito e esquerdo
    aceita_obliquo: bool = False     # o oblíquo próximo do plano pedido é o certo (pedúnculo superior)

    @property
    def limite(self) -> int:
        return max(self.vezes, self.max_vezes)


@dataclass(frozen=True)
class Resultado:
    nome: str
    valor: float | None
    unidade: str = ""
    referencia: str = ""
    casas: int = 2

    def texto_valor(self) -> str:
        if self.valor is None:
            return "—"
        v = f"{self.valor:.{self.casas}f}".replace(".", ",")
        return f"{v} {self.unidade}".strip()


@dataclass(frozen=True)
class Roteiro:
    id: str
    nome: str
    passos: tuple
    calcular: Callable[[dict], list]
    modalidades: frozenset = frozenset({"MR"})
    descricao: str = ""
    fonte: str = ""


def media(valores) -> float | None:
    v = [float(x) for x in (valores or []) if x is not None]
    return sum(v) / len(v) if v else None


def _razao(a, b) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ------------------------------------------------------------------ MRPI e MRPI 2.0
def _mrpi(valores: dict) -> list:
    p, m = media(valores.get("ponte")), media(valores.get("mesencefalo"))
    mcp, scp = media(valores.get("pcm")), media(valores.get("pcs"))
    v3, fh = media(valores.get("v3")), media(valores.get("cornos"))
    pm = _razao(p, m)
    ms = _razao(mcp, scp)
    mrpi = pm * ms if pm is not None and ms is not None else None
    out = [
        Resultado("Área da ponte", p, "mm²", casas=0),
        Resultado("Área do mesencéfalo", m, "mm²", casas=0),
        Resultado("Ponte / mesencéfalo", pm),
        Resultado("Pedúnculo cerebelar médio", mcp, "mm", casas=1),
        Resultado("Pedúnculo cerebelar superior", scp, "mm", casas=1),
        Resultado("PCM / PCS", ms),
        Resultado("MRPI", mrpi, referencia="acima de 13,55 associado a PSP (Quattrone et al., 2008)"),
    ]
    if v3 is not None or fh is not None:
        v3fh = _razao(v3, fh)
        mrpi2 = mrpi * v3fh if mrpi is not None and v3fh is not None else None
        out += [
            Resultado("3º ventrículo (média)", v3, "mm", casas=1),
            Resultado("Cornos frontais", fh, "mm", casas=1),
            Resultado("3º ventrículo / cornos frontais", v3fh),
            Resultado("MRPI 2.0", mrpi2,
                      referencia="≥ 2,18 PSP-P × doença de Parkinson; ≥ 2,50 PSP-RS × doença de Parkinson "
                                 "(Quattrone et al.)"),
        ]
    return out


MRPI = Roteiro(
    "mrpi", "MRPI e MRPI 2.0",
    (
        Passo("ponte", "Área da ponte", "polygon", "Sagital",
              "No sagital mediano, contorne a ponte, entre a linha que vai da incisura pontina superior "
              "à borda inferior da placa quadrigeminal e a paralela que passa pela incisura pontina "
              "inferior (método de Oba, usado no MRPI)."),
        Passo("mesencefalo", "Área do mesencéfalo", "polygon", "Sagital",
              "No mesmo sagital mediano, contorne o mesencéfalo acima da linha que vai da incisura "
              "pontina superior à borda inferior da placa quadrigeminal (método de Oba)."),
        Passo("pcm", "Pedúnculo cerebelar médio", "measure", "Sagital",
              "Num sagital parassagital, meça a largura do pedúnculo cerebelar médio no ponto mais "
              "largo. Medindo os dois lados, vale a média.", max_vezes=2),
        Passo("pcs", "Pedúnculo cerebelar superior", "measure", "Coronal",
              "No coronal oblíquo (perpendicular ao eixo do pedúnculo, ou o coronal disponível), meça "
              "a largura do pedúnculo cerebelar superior. Medindo os dois lados, vale a média.",
              max_vezes=2, aceita_obliquo=True),
        Passo("v3", "Largura do 3º ventrículo", "measure", "Axial",
              "No axial no plano AC-PC, meça a largura do 3º ventrículo em três pontos (anterior, médio "
              "e posterior). Vale a média. Necessário só para o MRPI 2.0.", vezes=3, opcional=True),
        Passo("cornos", "Largura dos cornos frontais", "measure", "Axial",
              "No axial no plano AC-PC, meça a maior largura entre as paredes laterais dos cornos "
              "frontais. Necessário só para o MRPI 2.0.", opcional=True),
    ),
    _mrpi,
    descricao="Índice de parkinsonismo por RM (Quattrone)",
    fonte="Quattrone et al.; Radiopaedia, 'Magnetic resonance parkinsonism index'",
)


# ------------------------------------------------------------------ Evans
def _evans(valores: dict) -> list:
    fh, cr = media(valores.get("cornos")), media(valores.get("cranio"))
    return [Resultado("Cornos frontais", fh, "mm", casas=1),
            Resultado("Diâmetro interno do crânio", cr, "mm", casas=1),
            Resultado("Índice de Evans", _razao(fh, cr),
                      referencia="acima de 0,30 indica ventriculomegalia")]


EVANS = Roteiro(
    "evans", "Índice de Evans",
    (
        Passo("cornos", "Largura dos cornos frontais", "measure", "Axial",
              "No axial, meça a maior largura entre as paredes laterais dos cornos frontais."),
        Passo("cranio", "Diâmetro interno do crânio", "measure", "Axial",
              "No mesmo corte axial, meça o maior diâmetro interno do crânio (tábua interna a tábua "
              "interna)."),
    ),
    _evans, modalidades=frozenset({"MR", "CT"}),
    descricao="Razão entre a largura dos cornos frontais e o diâmetro interno do crânio",
    fonte="Evans, 1942",
)


# ------------------------------------------------------------------ ângulo calosal
def _calosal(valores: dict) -> list:
    return [Resultado("Ângulo calosal", media(valores.get("angulo")), "°", casas=0,
                      referencia="abaixo de 90° favorece hidrocefalia de pressão normal")]


CALOSAL = Roteiro(
    "calosal", "Ângulo calosal",
    (
        Passo("angulo", "Ângulo calosal", "angle", "Coronal",
              "No coronal perpendicular ao plano AC-PC, na altura da comissura posterior, meça o ângulo "
              "entre as bordas mediais dos ventrículos laterais (vértice no meio, abaixo do corpo "
              "caloso)."),
    ),
    _calosal, modalidades=frozenset({"MR", "CT"}),
    descricao="Ângulo entre os ventrículos laterais no coronal da comissura posterior",
)

ROTEIROS: dict[str, Roteiro] = {r.id: r for r in (MRPI, EVANS, CALOSAL)}


# ------------------------------------------------------------------ andamento de um roteiro
@dataclass
class Andamento:
    """As medidas feitas até agora num roteiro: passo -> lista de valores (e de onde vieram)."""
    roteiro: Roteiro
    valores: dict = field(default_factory=dict)
    avisos: dict = field(default_factory=dict)          # passo -> [texto]

    def feitas(self, passo: Passo) -> int:
        return len(self.valores.get(passo.id, []))

    def completo(self, passo: Passo) -> bool:
        return self.feitas(passo) >= passo.vezes

    def proximo(self) -> Passo | None:
        for p in self.roteiro.passos:
            if not self.completo(p) and not p.opcional:
                return p
        for p in self.roteiro.passos:
            if not self.completo(p):
                return p
        return None

    def registrar(self, passo: Passo, valor: float, avisos: list | None = None) -> None:
        lista = self.valores.setdefault(passo.id, [])
        if len(lista) >= passo.limite:
            lista.pop(0)                              # refazer: a mais antiga sai
        lista.append(float(valor))
        if avisos:
            self.avisos.setdefault(passo.id, [])
            for a in avisos:
                if a not in self.avisos[passo.id]:
                    self.avisos[passo.id].append(a)

    def apagar(self, passo: Passo) -> None:
        self.valores.pop(passo.id, None)
        self.avisos.pop(passo.id, None)

    def pronto(self) -> bool:
        return all(self.completo(p) for p in self.roteiro.passos if not p.opcional)

    def resultados(self) -> list:
        return self.roteiro.calcular(self.valores)


def avisos_da_medida(passo: Passo, plano: str, espessura_mm: float | None) -> list[str]:
    """O que vai junto do número quando a medida não foi feita do jeito que o roteiro pede.
    Não recusa: o médico pode ter razão (ex.: coronal oblíquo é o certo para o pedúnculo superior)."""
    avisos = []
    if passo.plano and plano and plano != passo.plano and not (passo.aceita_obliquo and plano == "Oblíquo"):
        avisos.append(f"medida no plano {plano.lower()}; o roteiro pede {passo.plano.lower()}")
    if passo.plano and not plano:
        avisos.append("não foi possível saber o plano desta imagem")
    if espessura_mm is not None and espessura_mm > 3.0:
        avisos.append(f"corte de {espessura_mm:.1f} mm: o efeito de volume parcial pesa nesta medida")
    return avisos


def texto_do_laudo(andamento: Andamento) -> str:
    """O texto para o laudo: uma linha por resultado, com a referência entre parênteses."""
    r = andamento.roteiro
    linhas = [f"{r.nome}:"]
    for res in andamento.resultados():
        if res.valor is None:
            continue
        ref = f" (referência: {res.referencia})" if res.referencia else ""
        linhas.append(f"- {res.nome}: {res.texto_valor()}{ref}.")
    avisos = [f"{p.nome}: {a}" for p in r.passos for a in andamento.avisos.get(p.id, [])]
    if avisos:
        linhas.append("Observações: " + "; ".join(avisos) + ".")
    return "\n".join(linhas)
