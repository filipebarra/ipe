"""Planilhas para o lote (0.100.97): ler CSV/TSV, XLSX e ODS e gravar XLSX — sem biblioteca de fora.

Saiu de `lote_mama.py` (0.100.69), que deu lugar ao lote genérico (`automation/lote.py`). O .xlsx e o .ods são zips de
XML; o CSV tem o separador adivinhado (; , ou tabulação) e a codificação (UTF-8 ou Windows-1252).
"""
from __future__ import annotations

import csv
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# ====================================================================== planilha: ler
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
_DATAS_PADRAO = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))


def _coluna(ref: str) -> int:
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def de_serial(v: float) -> datetime:
    """Número de série do Excel → data (o sistema de 1900, com o 29/2/1900 que não existiu)."""
    return datetime(1899, 12, 30) + timedelta(days=float(v))


def _estilos_de_data(z: zipfile.ZipFile) -> set[int]:
    """Os índices de estilo (atributo `s` da célula) que são data."""
    if "xl/styles.xml" not in z.namelist():
        return set()
    raiz = ET.fromstring(z.read("xl/styles.xml"))
    proprios = {}
    for f in raiz.findall("m:numFmts/m:numFmt", _NS):
        codigo = re.sub(r'"[^"]*"|\[[^\]]*\]', "", f.get("formatCode") or "").lower()
        proprios[int(f.get("numFmtId"))] = bool(re.search(r"[dy]|mm", codigo)) and "0" not in codigo
    out = set()
    for i, xf in enumerate(raiz.findall("m:cellXfs/m:xf", _NS)):
        nid = int(xf.get("numFmtId") or 0)
        if nid in _DATAS_PADRAO or proprios.get(nid):
            out.add(i)
    return out


def abas_do_xlsx(caminho) -> list[str]:
    with zipfile.ZipFile(caminho) as z:
        raiz = ET.fromstring(z.read("xl/workbook.xml"))
        return [s.get("name") or "" for s in raiz.findall("m:sheets/m:sheet", _NS)]


def ler_xlsx(caminho, aba: str | None = None) -> list[list]:
    """As linhas de uma aba (a primeira, sem `aba`): texto, número, data (datetime) ou None."""
    with zipfile.ZipFile(caminho) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        alvo = {r.get("Id"): r.get("Target") for r in rels.findall("p:Relationship", _NS)}
        folhas = [(s.get("name") or "", alvo.get(s.get(f"{{{_NS['r']}}}id"), ""))
                  for s in wb.findall("m:sheets/m:sheet", _NS)]
        if not folhas:
            return []
        nome, destino = next(((n, t) for n, t in folhas if n == aba), folhas[0]) if aba else folhas[0]
        destino = destino.lstrip("/")
        if not destino.startswith("xl/"):
            destino = "xl/" + destino
        textos: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                textos.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        datas = _estilos_de_data(z)
        linhas: list[list] = []
        with z.open(destino) as f:
            for _ev, el in ET.iterparse(f):
                if el.tag != f"{{{_NS['m']}}}row":
                    continue
                linha: list = []
                for c in el.findall("m:c", _NS):
                    i = _coluna(c.get("r") or "") if c.get("r") else len(linha)
                    while len(linha) <= i:
                        linha.append(None)
                    tipo = c.get("t") or "n"
                    v = c.find("m:v", _NS)
                    if tipo == "inlineStr":
                        valor = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                    elif v is None or v.text is None:
                        valor = None
                    elif tipo == "s":
                        valor = textos[int(v.text)]
                    elif tipo in ("str", "e"):
                        valor = v.text
                    elif tipo == "b":
                        valor = v.text == "1"
                    else:
                        try:
                            num = float(v.text)
                            if int(c.get("s") or 0) in datas:
                                valor = de_serial(num)
                            else:
                                valor = int(num) if num.is_integer() else num
                        except ValueError:
                            valor = v.text
                    linha[i] = valor
                n = int(el.get("r") or len(linhas) + 1)
                while len(linhas) < n - 1:
                    linhas.append([])
                linhas.append(linha)
                el.clear()
        return linhas


def ler_csv(caminho) -> list[list]:
    bruto = Path(caminho).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            txt = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        txt = bruto.decode("latin-1")
    amostra = txt[:4000]
    # o separador mais frequente na amostra (empate: ; antes de tabulação antes de vírgula)
    sep = max((";", "\t", ","), key=lambda s: (amostra.count(s), {";": 2, "\t": 1, ",": 0}[s]))
    return [list(l) for l in csv.reader(txt.splitlines(), delimiter=sep)]


# ---------------------------------------------------------------------- ODS (LibreOffice / OpenOffice)
_ODS = {"office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
_MAX_REPETIDAS = 2000          # o LibreOffice grava "1 048 576 linhas vazias repetidas" no fim da aba


def _q(ns: str, nome: str) -> str:
    return f"{{{_ODS[ns]}}}{nome}"


def abas_do_ods(caminho) -> list[str]:
    with zipfile.ZipFile(caminho) as z, z.open("content.xml") as f:
        return [el.get(_q("table", "name")) or "" for _ev, el in ET.iterparse(f) if el.tag == _q("table", "table")]


def _valor_ods(c):
    tipo = c.get(_q("office", "value-type")) or ""
    if tipo in ("float", "percentage", "currency"):
        try:
            num = float(c.get(_q("office", "value")) or "")
            return int(num) if num.is_integer() else num
        except ValueError:
            return None
    if tipo == "date":
        v = c.get(_q("office", "date-value")) or ""
        try:
            return datetime.fromisoformat(v[:19])
        except ValueError:
            return v or None
    if tipo == "boolean":
        return (c.get(_q("office", "boolean-value")) or "") == "true"
    partes = []
    for p in c.iter(_q("text", "p")):
        partes.append("".join(p.itertext()))
    txt = "\n".join(partes)
    return txt if txt != "" else None


def ler_ods(caminho, aba: str | None = None) -> list[list]:
    with zipfile.ZipFile(caminho) as z:
        raiz = ET.fromstring(z.read("content.xml"))
    tabelas = list(raiz.iter(_q("table", "table")))
    if not tabelas:
        return []
    t = next((x for x in tabelas if x.get(_q("table", "name")) == aba), tabelas[0]) if aba else tabelas[0]
    linhas: list[list] = []
    for row in t.iter(_q("table", "table-row")):
        linha: list = []
        for c in row:
            if c.tag not in (_q("table", "table-cell"), _q("table", "covered-table-cell")):
                continue
            n = min(int(c.get(_q("table", "number-columns-repeated")) or 1), _MAX_REPETIDAS)
            v = _valor_ods(c)
            linha.extend([v] * n)
        while linha and linha[-1] in (None, ""):
            linha.pop()
        rep = min(int(row.get(_q("table", "number-rows-repeated")) or 1), _MAX_REPETIDAS)
        linhas.extend([list(linha) for _ in range(rep)] if linha else [[] for _ in range(rep)])
    while linhas and not linhas[-1]:
        linhas.pop()
    return linhas


# ---------------------------------------------------------------------- qualquer uma
FORMATOS = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".ods")


def _ext(caminho) -> str:
    return Path(str(caminho)).suffix.lower()


def ler_planilha(caminho, aba: str | None = None) -> list[list]:
    ext = _ext(caminho)
    if ext in (".csv", ".tsv", ".txt"):
        return ler_csv(caminho)
    if ext == ".ods":
        return ler_ods(caminho, aba)
    if ext in (".xlsx", ".xlsm"):
        return ler_xlsx(caminho, aba)
    if ext == ".xls":
        raise ValueError("planilha .xls (Excel 97–2003): abra no Excel e salve como .xlsx")
    raise ValueError(f"formato de planilha não reconhecido: {ext or caminho}")


def abas(caminho) -> list[str]:
    ext = _ext(caminho)
    if ext == ".ods":
        return abas_do_ods(caminho)
    if ext in (".xlsx", ".xlsm"):
        return abas_do_xlsx(caminho)
    return []


# ====================================================================== planilha: gravar
def _letra(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


_INVALIDO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _celula(ref: str, v, cabecalho: bool = False) -> str:
    if v is None or v == "":
        return ""
    s = ' s="1"' if cabecalho else ""
    if isinstance(v, bool):
        v = "sim" if v else "não"
    if isinstance(v, (int, float)) and not cabecalho:
        return f'<c r="{ref}"><v>{v!r}</v></c>'
    if isinstance(v, datetime):
        v = v.strftime("%d/%m/%Y") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.strftime("%d/%m/%Y %H:%M")
    elif isinstance(v, date):
        v = v.strftime("%d/%m/%Y")
    txt = escape(_INVALIDO.sub(" ", str(v)))
    return f'<c r="{ref}" t="inlineStr"{s}><is><t xml:space="preserve">{txt}</t></is></c>'


def _folha(linhas: list[list], larguras: list[float] | None = None, congelar: bool = True) -> str:
    partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
              '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if congelar and linhas:
        partes.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
                      'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    if larguras:
        partes.append("<cols>" + "".join(f'<col min="{i + 1}" max="{i + 1}" width="{w:.1f}" customWidth="1"/>'
                                         for i, w in enumerate(larguras)) + "</cols>")
    partes.append("<sheetData>")
    for r, linha in enumerate(linhas, start=1):
        cels = "".join(_celula(f"{_letra(c)}{r}", v, cabecalho=(r == 1 and congelar)) for c, v in enumerate(linha))
        partes.append(f'<row r="{r}">{cels}</row>')
    partes.append("</sheetData></worksheet>")
    return "".join(partes)


def gravar_xlsx(caminho, folhas: list[tuple[str, list[list]]]) -> None:
    """Grava um .xlsx simples: uma lista de (nome da aba, linhas). A primeira linha de cada aba de dados fica em
    negrito e congelada. Grava num arquivo ao lado e troca no fim (a planilha anterior não se perde no meio)."""
    caminho = Path(caminho)
    tmp = caminho.with_name(caminho.name + ".gravando")
    tipos = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
             '<Default Extension="xml" ContentType="application/xml"/>',
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.'
             'spreadsheetml.sheet.main+xml"/>',
             '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
             'spreadsheetml.styles+xml"/>']
    wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    estilos = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
               '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
               '<fills count="2"><fill><patternFill patternType="none"/></fill>'
               '<fill><patternFill patternType="gray125"/></fill></fills>'
               '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
               '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
               '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
               '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
               '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
               '</styleSheet>')
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for i, (nome, linhas) in enumerate(folhas, start=1):
            nome = re.sub(r"[\[\]:*?/\\]", " ", nome)[:31].strip() or f"Aba {i}"
            tipos.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.'
                         'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
            wb.append(f'<sheet name="{escape(nome, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                        f'relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
            dados = bool(linhas) and len(linhas[0]) > 1
            larg = None
            if dados:
                larg = [min(48.0, max(9.0, len(str(t or "")) * 0.9 + 2)) for t in linhas[0]]
            z.writestr(f"xl/worksheets/sheet{i}.xml", _folha(linhas, larg, congelar=dados))
        rels.append(f'<Relationship Id="rId{len(folhas) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/'
                    '2006/relationships/styles" Target="styles.xml"/>')
        z.writestr("[Content_Types].xml", "".join(tipos) + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", "".join(wb) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels) + "</Relationships>")
        z.writestr("xl/styles.xml", estilos)
    tmp.replace(caminho)


# ====================================================================== valores
def para_data(v) -> str:
    """Qualquer jeito de escrever a data → "AAAAMMDD" ("" se não deu)."""
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y%m%d")
    if isinstance(v, date):
        return v.strftime("%Y%m%d")
    if isinstance(v, (int, float)):
        if 19000101 <= v <= 21001231 and float(v).is_integer():
            return str(int(v))
        if 15000 < v < 80000:                       # número de série do Excel
            return de_serial(v).strftime("%Y%m%d")
        return ""
    s = str(v).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        return f"{a:04d}{b:02d}{c:02d}"
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        d, mes, a = (int(x) for x in m.groups())
        return f"{a:04d}{mes:02d}{d:02d}"
    if re.fullmatch(r"\d{8}", s):
        return s
    return ""


def para_id(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")
