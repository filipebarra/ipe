r"""Gera o guia do usuário em PDF a partir de `tools/guia/guia.md`.

O texto mora em `guia.md`, num Markdown simples; este script só monta o PDF (ReportLab). Assim o
guia se atualiza editando o texto e rodando de novo — o gerador da 0.65 se perdeu porque ficava
fora do projeto; este fica dentro.

Uso:  python tools/guia/gerar_guia.py            (grava em docs/ e em src/ipe/ajuda/)
      python tools/guia/gerar_guia.py saida.pdf  (grava só onde mandar)

Sintaxe aceita em `guia.md`:
    # Título do capítulo              (começa página nova, com "CAPÍTULO N")
    ## Seção   /   ### Subseção
    parágrafo (linhas seguidas viram um parágrafo; linha em branco separa)
    - item de lista   /   1. item numerado     (linha que começa com dois espaços continua o item)
    | a | b |  (tabela; a primeira linha é o cabeçalho, a linha |---| é ignorada; \| = barra no texto)
    > **Título.** texto do quadro de aviso   (linhas seguidas com > continuam o quadro)
    ```  bloco de comando/código  ```
    **negrito**, *itálico*, `código`
    {versao} no texto vira a versão do programa
    ![Legenda](arquivo.png)                (figura de tools/guia/capturas/, largura da página, legenda embaixo;
                                            ![Legenda](arquivo.png){60} = 60% da largura)
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, KeepTogether, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Preformatted, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

RAIZ = Path(__file__).resolve().parents[2]
FONTE = Path(__file__).with_name("guia.md")
SAIDAS = [RAIZ / "docs" / "Ipe-guia-do-usuario.pdf",
          RAIZ / "src" / "ipe" / "ajuda" / "Ipe-guia-do-usuario.pdf"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]

AZUL = colors.HexColor("#1f4e79")
CINZA = colors.HexColor("#5f6368")
LINHA = colors.HexColor("#d0d4da")
FUNDO_TAB = colors.HexColor("#eef2f7")
FUNDO_AVISO = colors.HexColor("#fff6e0")
BARRA_AVISO = colors.HexColor("#e0a020")
FUNDO_COD = colors.HexColor("#f3f4f6")


CAPTURAS = Path(__file__).with_name("capturas")


def _figura(arquivo: str, legenda: str, largura: float, versao: str, fracao: float = 1.0) -> list:
    """0.99.87: captura de tela do programa, com borda fina e legenda. Sem o arquivo, um aviso no lugar
    (o guia continua saindo; o roteiro `capturas.py` refaz as imagens)."""
    from reportlab.platypus import Image
    p = (CAPTURAS / arquivo) if not Path(arquivo).is_absolute() else Path(arquivo)
    if not p.exists():
        return [Paragraph(f"<i>[figura em falta: {arquivo}]</i>", ST["corpo"])]
    from PIL import Image as PILImage
    with PILImage.open(p) as im:
        w, h = im.size
    larg = largura * max(0.2, min(1.0, fracao))
    alt = larg * h / w
    maximo = 150 * mm                                   # figura alta demais: reduz para caber na página
    if alt > maximo:
        larg, alt = larg * maximo / alt, maximo
    fonte = p
    if p.stat().st_size > 150_000:          # tela cheia: JPEG de boa qualidade deixa o PDF ~3× menor
        import tempfile
        fonte = Path(tempfile.gettempdir()) / f"ipe_guia_{p.stem}.jpg"
        with PILImage.open(p) as im:
            im.convert("RGB").save(fonte, "JPEG", quality=86, optimize=True)
    img = Image(str(fonte), width=larg, height=alt)
    moldura = Table([[img]], colWidths=[larg + 2], style=TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINHA), ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    moldura.hAlign = "CENTER"
    partes = [Spacer(1, 3), moldura]
    if legenda:
        partes.append(Paragraph(_inline(legenda, versao), ST["legenda"]))
    partes.append(Spacer(1, 6))
    return [KeepTogether(partes)]


# ------------------------------------------------------------------ fontes
def _registrar_fontes() -> tuple[str, str, str, str]:
    """DejaVu (tem as setas, ▸, ⠿, ✕, ↻); no Windows sem DejaVu, Segoe UI / Arial."""
    candidatos = [
        ("/usr/share/fonts/truetype/dejavu/", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf",
         "DejaVuSans-Oblique.ttf", "DejaVuSansMono.ttf"),
        ("C:/Windows/Fonts/", "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "consola.ttf"),
        ("C:/Windows/Fonts/", "arial.ttf", "arialbd.ttf", "ariali.ttf", "cour.ttf"),
    ]
    for pasta, r, b, i, m in candidatos:
        p = Path(pasta)
        if all((p / f).exists() for f in (r, b, i, m)):
            pdfmetrics.registerFont(TTFont("Guia", str(p / r)))
            pdfmetrics.registerFont(TTFont("Guia-B", str(p / b)))
            pdfmetrics.registerFont(TTFont("Guia-I", str(p / i)))
            pdfmetrics.registerFont(TTFont("Guia-M", str(p / m)))
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            registerFontFamily("Guia", normal="Guia", bold="Guia-B", italic="Guia-I", boldItalic="Guia-B")
            return "Guia", "Guia-B", "Guia-I", "Guia-M"
    raise SystemExit("Não achei uma fonte com acentos e setas (DejaVu Sans, Segoe UI ou Arial).")


F, FB, FI, FM = _registrar_fontes()

ST = {
    "legenda": ParagraphStyle("legenda", fontName=FI, fontSize=8.2, leading=10.5, textColor=CINZA,
                              alignment=1, spaceBefore=2, spaceAfter=2),
    "corpo": ParagraphStyle("corpo", fontName=F, fontSize=9.6, leading=13.6, spaceAfter=5,
                            alignment=TA_LEFT),
    "item": ParagraphStyle("item", fontName=F, fontSize=9.6, leading=13.4, leftIndent=13,
                           bulletIndent=3, spaceAfter=2.5),
    "rotulo": ParagraphStyle("rotulo", fontName=FB, fontSize=8.5, textColor=CINZA, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=21, leading=25, textColor=AZUL, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=FB, fontSize=13.2, leading=17, textColor=AZUL,
                         spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName=FB, fontSize=10.6, leading=14, spaceBefore=6, spaceAfter=2),
    "cel": ParagraphStyle("cel", fontName=F, fontSize=8.6, leading=11.2),
    "cel_cab": ParagraphStyle("cel_cab", fontName=FB, fontSize=8.6, leading=11.2),
    "aviso": ParagraphStyle("aviso", fontName=F, fontSize=9.1, leading=12.8),
    "cod": ParagraphStyle("cod", fontName=FM, fontSize=8.4, leading=11.2),
    "toc0": ParagraphStyle("toc0", fontName=FB, fontSize=10.4, leading=14, spaceBefore=6),
    "toc1": ParagraphStyle("toc1", fontName=F, fontSize=9.2, leading=12, leftIndent=14),
}


# ------------------------------------------------------------------ texto em linha
def _inline(t: str, versao: str) -> str:
    t = t.replace("{versao}", versao)
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"`([^`]+)`", lambda m: f'<font name="{FM}" size="8.6">{m.group(1)}</font>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    return t


# ------------------------------------------------------------------ documento
class Guia(BaseDocTemplate):
    def __init__(self, caminho: str, versao: str, **kw):
        super().__init__(caminho, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                         topMargin=18 * mm, bottomMargin=18 * mm,
                         title="Ipê — guia do usuário", author="Ipê",
                         subject=f"Manual de uso, versão {versao}", **kw)
        self.versao = versao
        quadro = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="q")
        self.addPageTemplates([PageTemplate("capa", [quadro], onPage=self._capa),
                               PageTemplate("texto", [quadro], onPage=self._rodape)])

    def _capa(self, c, doc):
        c.saveState()
        c.setFillColor(AZUL)
        c.rect(0, A4[1] - 95 * mm, A4[0], 95 * mm, fill=1, stroke=0)
        c.restoreState()

    def _rodape(self, c, doc):
        c.saveState()
        c.setFont(F, 8)
        c.setFillColor(CINZA)
        c.drawString(self.leftMargin, 10 * mm, f"Ipê {self.versao} — guia do usuário")
        c.drawRightString(A4[0] - self.rightMargin, 10 * mm, str(doc.page))
        c.setStrokeColor(LINHA)
        c.line(self.leftMargin, 13.5 * mm, A4[0] - self.rightMargin, 13.5 * mm)
        c.restoreState()

    def afterFlowable(self, f):
        nivel = getattr(f, "_nivel_sumario", None)
        if nivel is not None:
            self.notify("TOCEntry", (nivel, f._texto_sumario, self.page, f._chave))
            self.canv.bookmarkPage(f._chave)
            self.canv.addOutlineEntry(f._texto_sumario, f._chave, level=nivel, closed=nivel > 0)


def _titulo(texto: str, estilo: str, nivel: int, n: list) -> Paragraph:
    n[0] += 1
    p = Paragraph(texto, ST[estilo])
    p._nivel_sumario, p._texto_sumario, p._chave = nivel, re.sub(r"<[^>]+>", "", texto), f"s{n[0]}"
    p.keepWithNext = True
    return p


def _larguras(linhas: list[list[str]], total: float) -> list[float]:
    ncol = max(len(l) for l in linhas)
    peso = []
    for j in range(ncol):
        tam = [len(re.sub(r"[*`]", "", l[j])) if j < len(l) else 0 for l in linhas]
        peso.append(max(6, min(60, sum(tam) / len(tam) + max(tam) * 0.25)))
    if ncol == 2:
        peso[0] = min(peso[0], peso[1] * 0.7)
    s = sum(peso)
    return [total * p / s for p in peso]


def _tabela(linhas: list[list[str]], largura: float, versao: str) -> Table:
    dados = []
    for i, l in enumerate(linhas):
        est = ST["cel_cab"] if i == 0 else ST["cel"]
        dados.append([Paragraph(_inline(c, versao), est) for c in l])
    t = Table(dados, colWidths=_larguras(linhas, largura), repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FUNDO_TAB),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, AZUL),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _aviso(texto: str, largura: float, versao: str) -> Table:
    t = Table([[Paragraph(_inline(texto, versao), ST["aviso"])]], colWidths=[largura])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FUNDO_AVISO),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BARRA_AVISO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _codigo(linhas: list[str], largura: float) -> Table:
    p = Preformatted("\n".join(linhas), ST["cod"])
    t = Table([[p]], colWidths=[largura])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FUNDO_COD),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def montar(texto: str, versao: str, largura: float) -> list:
    hoje = date.today()
    hist: list = []
    # capa
    hist += [Spacer(1, 30 * mm),
             Paragraph('<font color="white" size="34">Ipê</font>',
                       ParagraphStyle("c1", fontName=FB, fontSize=34, leading=40)),
             Spacer(1, 4 * mm),
             Paragraph('<font color="white">Guia do usuário</font>',
                       ParagraphStyle("c2", fontName=F, fontSize=18, leading=22)),
             Spacer(1, 3 * mm),
             Paragraph(f'<font color="#cfe0f2">Versão {versao} · {MESES[hoje.month - 1]} de {hoje.year}</font>',
                       ParagraphStyle("c3", fontName=F, fontSize=11.5, leading=15)),
             Spacer(1, 70 * mm)]
    capa_extra: list[str] = []
    corpo: list[str] = []
    linhas = texto.splitlines()
    i = 0
    while i < len(linhas) and not linhas[i].startswith("# "):
        capa_extra.append(linhas[i])
        i += 1
    corpo = linhas[i:]
    capa_sem_coment = re.sub(r"<!--.*?-->", "", "\n".join(capa_extra), flags=re.S)
    capa_txt = " ".join(l.strip() for l in capa_sem_coment.splitlines() if l.strip())
    if capa_txt.startswith(">"):
        hist.append(_aviso(capa_txt.lstrip("> "), largura, versao))
    hist += [NextPageTemplate("texto"), PageBreak()]
    sumario = TableOfContents()
    sumario.levelStyles = [ST["toc0"], ST["toc1"]]
    sumario.dotsMinLevel = 1
    hist += [Paragraph("Sumário", ST["h1"]), sumario, PageBreak()]

    n = [0]
    cap = 0
    par: list[str] = []
    item: list[str] | None = None
    tipo_item = ""
    num_item = 0

    def fecha_par():
        nonlocal par
        if par:
            hist.append(Paragraph(_inline(" ".join(par), versao), ST["corpo"]))
            par = []

    def fecha_item():
        nonlocal item
        if item is not None:
            bullet = "•" if tipo_item == "-" else f"{num_item}."
            hist.append(Paragraph(_inline(" ".join(item), versao), ST["item"], bulletText=bullet))
            item = None

    k = 0
    while k < len(corpo):
        l = corpo[k]
        s = l.strip()
        if s.startswith("<!--"):
            while k < len(corpo) and "-->" not in corpo[k]:
                k += 1
            k += 1
            continue
        if s.startswith("```"):
            fecha_par(); fecha_item()
            bloco = []
            k += 1
            while k < len(corpo) and not corpo[k].strip().startswith("```"):
                bloco.append(corpo[k].rstrip())
                k += 1
            hist += [_codigo(bloco, largura), Spacer(1, 5)]
            k += 1
            continue
        m_fig = re.fullmatch(r"!\[(.*)\]\(([^)]+)\)(?:\{(\d+)\})?", s)
        if m_fig:
            fecha_par(); fecha_item()
            hist += _figura(m_fig.group(2), m_fig.group(1), largura, versao,
                            int(m_fig.group(3)) / 100 if m_fig.group(3) else 1.0)
            k += 1
            continue
        if s.startswith("# "):
            fecha_par(); fecha_item()
            cap += 1
            if cap > 1:
                hist.append(PageBreak())
            hist.append(Paragraph(f"CAPÍTULO {cap}", ST["rotulo"]))
            hist.append(_titulo(f"{cap}. {_inline(s[2:], versao)}", "h1", 0, n))
        elif s.startswith("## "):
            fecha_par(); fecha_item()
            hist.append(CondPageBreak(30 * mm))
            hist.append(_titulo(_inline(s[3:], versao), "h2", 1, n))
        elif s.startswith("### "):
            fecha_par(); fecha_item()
            hist.append(CondPageBreak(20 * mm))
            p = Paragraph(_inline(s[4:], versao), ST["h3"])
            p.keepWithNext = True
            hist.append(p)
        elif s.startswith("|"):
            fecha_par(); fecha_item()
            tab = []
            while k < len(corpo) and corpo[k].strip().startswith("|"):
                bruta = corpo[k].strip().strip("|").replace("\\|", "\x00")
                cel = [c.strip().replace("\x00", "|") for c in bruta.split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cel):
                    tab.append(cel)
                k += 1
            hist += [_tabela(tab, largura, versao), Spacer(1, 6)]
            continue
        elif s.startswith(">"):
            fecha_par(); fecha_item()
            bloco = []
            while k < len(corpo) and corpo[k].strip().startswith(">"):
                bloco.append(corpo[k].strip()[1:].strip())
                k += 1
            hist += [Spacer(1, 2), KeepTogether(_aviso(" ".join(bloco), largura, versao)), Spacer(1, 6)]
            continue
        elif re.match(r"^(- |\d+\. )", s) and not l.startswith("  "):
            fecha_par(); fecha_item()
            m = re.match(r"^(- |(\d+)\. )(.*)$", s)
            tipo_item = "-" if m.group(1) == "- " else "1"
            num_item = int(m.group(2)) if m.group(2) else 0
            item = [m.group(3)]
        elif l.startswith("  ") and item is not None and s:
            item.append(s)
        elif not s:
            fecha_par(); fecha_item()
        else:
            fecha_item()
            par.append(s)
        k += 1
    fecha_par(); fecha_item()
    return hist


def versao_do_codigo() -> str:
    t = (RAIZ / "src" / "ipe" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', t).group(1)


def simbolos_sem_fonte(texto: str) -> list[str]:
    """Caracteres que a fonte do corpo não desenha (sairiam como um quadrado no PDF)."""
    from reportlab.pdfbase.pdfmetrics import getFont
    face = getFont(F).face
    tem = set(getattr(face, "charToGlyph", {}) or {})
    if not tem:
        return []
    return sorted({c for c in texto if ord(c) > 127 and ord(c) not in tem})


def gerar(saidas: list[Path]) -> list[Path]:
    versao = versao_do_codigo()
    texto = FONTE.read_text(encoding="utf-8")
    faltam = simbolos_sem_fonte(texto)
    if faltam:
        raise SystemExit(f"Símbolos que a fonte não desenha (sairiam como quadrado): {' '.join(faltam)}")
    feitos = []
    for destino in saidas:
        destino.parent.mkdir(parents=True, exist_ok=True)
        doc = Guia(str(destino), versao)
        doc.multiBuild(montar(texto, versao, doc.width))
        feitos.append(destino)
    return feitos


if __name__ == "__main__":
    alvo = [Path(sys.argv[1])] if len(sys.argv) > 1 else SAIDAS
    for p in gerar(alvo):
        print(f"gravado: {p}")
