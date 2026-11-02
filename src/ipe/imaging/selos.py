"""Selos de integridade na imagem (0.99.22, plano AW, item F5 barato).

A AW mostra no próprio quadro o que pode tornar a imagem imprópria para ler: compressão com perdas
(crítica na mamografia), Modality LUT, pixel não quadrado, imagem derivada. Aqui é o mesmo: uma
faixa curta no alto do quadro, em vermelho quando compromete o laudo e em âmbar quando é só para
saber. Clicar nela explica cada selo.

Regras do projeto que isto segue: *retorno silencioso é defeito* e *a tela diz por quê*. O selo não
bloqueia nada — avisa.

Por que a mamografia é grave: a compressão com perdas apaga justamente o que se procura nela
(microcalcificações finas). O ACR-AAPM-SIIM (2014) e a FDA (MQSA) não aceitam mamografia comprimida
com perdas para a leitura final; no Brasil a CFM 2.107/2014 deixa a decisão ao radiologista.
"""
from __future__ import annotations

from dataclasses import dataclass

#: o que a reconstrução (MPR, MIP) herda das imagens de origem. ImageType não: a reconstrução é
#: outra imagem, e o selo de "derivada" seria da origem, não dela.
CHAVES_HERDADAS = ("Modality", "LossyImageCompression", "LossyImageCompressionRatio",
                   "LossyImageCompressionMethod", "_ts", "_modality_lut")

MAMO = ("MG",)

#: LossyImageCompressionMethod (e sintaxe) -> nome curto
METODOS = {"ISO_10918_1": "JPEG", "ISO_14495_1": "JPEG-LS", "ISO_15444_1": "JPEG 2000",
           "ISO_15444_15": "HTJ2K", "ISO_13818_2": "MPEG2", "ISO_14496_10": "H.264",
           "ISO_23008_2": "H.265"}
METODO_DA_SINTAXE = {"1.2.840.10008.1.2.4.50": "JPEG", "1.2.840.10008.1.2.4.51": "JPEG",
                     "1.2.840.10008.1.2.4.81": "JPEG-LS", "1.2.840.10008.1.2.4.91": "JPEG 2000",
                     "1.2.840.10008.1.2.4.93": "JPEG 2000", "1.2.840.10008.1.2.4.203": "HTJ2K",
                     "1.2.840.10008.1.2.4.100": "MPEG2", "1.2.840.10008.1.2.4.101": "MPEG2",
                     "1.2.840.10008.1.2.4.102": "H.264", "1.2.840.10008.1.2.4.103": "H.264"}


def _metodo(h: dict) -> str:
    bruto = str(h.get("LossyImageCompressionMethod", "") or "").strip("[] ")
    nomes = []
    for parte in bruto.replace("\\", ",").split(","):
        p = parte.strip().strip("'\"")
        if p and METODOS.get(p, p) not in nomes:
            nomes.append(METODOS.get(p, p))
    if not nomes:
        m = METODO_DA_SINTAXE.get(str(h.get("_ts", "") or ""), "")
        nomes = [m] if m else []
    return " + ".join(nomes)


@dataclass(frozen=True)
class Selo:
    chave: str
    texto: str          # o que vai na faixa (curto)
    grave: bool         # vermelho: compromete a leitura; âmbar: informativo
    explicacao: str     # o que aparece ao clicar


def com_perdas(h: dict) -> bool:
    """A imagem passou por compressão com perdas — pelo atributo ou pela sintaxe do arquivo."""
    if str(h.get("LossyImageCompression", "")).strip() == "01":
        return True
    ts = str(h.get("_ts", "") or "")
    if ts:
        from ipe.core.acervo import LOSSY, sintaxe
        return sintaxe(ts).tipo == LOSSY
    return False


def _taxa(h: dict) -> str:
    """'15:1' a partir de LossyImageCompressionRatio (pode ter vários valores, um por etapa)."""
    bruto = str(h.get("LossyImageCompressionRatio", "") or "").strip("[] ")
    vals = []
    for parte in bruto.replace("\\", ",").split(","):
        try:
            v = float(parte.strip().strip("'\""))
        except ValueError:
            continue
        if v > 0:
            vals.append(v)
    if not vals:
        return ""
    total = 1.0
    for v in vals:                # compressões em série se multiplicam
        total *= v
    return f"{total:.0f}:1" if total >= 10 else f"{total:.1f}:1"


def selos(header: dict, pixel_spacing=None, modalidade: str = "") -> list[Selo]:
    """Os selos desta imagem, os graves primeiro."""
    h = header or {}
    mod = (modalidade or h.get("Modality", "") or "").upper()
    out: list[Selo] = []
    if com_perdas(h):
        taxa = _taxa(h)
        det = ", ".join(x for x in (_metodo(h), taxa) if x)
        if mod in MAMO:
            out.append(Selo("perdas", "COMPRESSÃO COM PERDAS" + (f" ({det})" if det else "")
                            + " — imprópria para o laudo", True,
                            "Esta mamografia foi comprimida com perdas. Detalhes finos, como "
                            "microcalcificações, podem ter sido apagados ou alterados. O ACR e a FDA "
                            "não aceitam mamografia comprimida com perdas para a leitura final: "
                            "peça as imagens originais."))
        else:
            out.append(Selo("perdas", "Compressão com perdas" + (f" ({det})" if det else ""), False,
                            "A imagem foi comprimida com perdas. Em taxas moderadas a leitura costuma "
                            "ser preservada, mas detalhes finos e medidas de densidade podem mudar."))
    if h.get("_modality_lut") == "1":
        out.append(Selo("lut", "Modality LUT em tabela", True,
                        "O arquivo traz uma tabela (Modality LUT) para converter os valores dos "
                        "pixels. O programa aplica só a reta (slope e intercept): valores em HU e "
                        "medidas de densidade podem não ser os reais."))
    if pixel_spacing:
        try:
            rs, cs = float(pixel_spacing[0]), float(pixel_spacing[1])
        except (TypeError, ValueError, IndexError):
            rs = cs = 0.0
        if rs > 0 and cs > 0 and abs(rs / cs - 1.0) > 0.01:
            out.append(Selo("pixel", f"Pixel não quadrado ({rs:.2f} × {cs:.2f} mm)", False,
                            "Os pixels não são quadrados. A imagem já é mostrada na proporção certa e "
                            "as medidas usam os dois espaçamentos; o aviso é para quem exporta ou "
                            "compara com outro programa."))
    partes = [x.strip() for x in str(h.get("ImageType", "") or "").upper().strip("[]").replace(",", "\\").split("\\")]
    partes = [x.strip("'\" ") for x in partes]
    # DERIVED\PRIMARY é comum na mamografia "para apresentação" e não é aviso; DERIVED\SECONDARY é
    # reconstrução, captura ou mapa feito depois
    if len(partes) >= 2 and partes[0] == "DERIVED" and partes[1] == "SECONDARY":
        out.append(Selo("derivada", "Imagem derivada", False,
                        "A imagem não é a aquisição original (ImageType DERIVED\\SECONDARY): é uma "
                        "reconstrução, subtração, mapa ou captura feita depois."))
    return sorted(out, key=lambda s: not s.grave)


def selo_de_mistura(nome_deste: str) -> Selo:
    """Quadros de pacientes diferentes no mesmo layout (0.99.22, plano AW item 2)."""
    return Selo("paciente", "PACIENTES DIFERENTES NO LAYOUT — este quadro: " + (nome_deste or "?"), True,
                "Os quadros desta tela mostram exames de pacientes diferentes (nome ou ID não batem). "
                "Confira de quem é cada imagem antes de laudar ou comparar.")
