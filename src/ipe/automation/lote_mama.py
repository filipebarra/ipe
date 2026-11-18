"""Pesquisa em lote: densidade e calcificações vasculares das mamografias de uma lista (0.100.69).

A partir de uma planilha (uma linha por paciente, com o **ID** e a **data da mamografia**), para cada linha:

1. acha o exame — primeiro no banco do Ipê; se não está, no PACS (C-FIND por ID, data e modalidade MG);
2. baixa o exame (se veio do PACS);
3. mede a densidade (rede da NYU) e as calcificações vasculares (SCU-Net), as mesmas medidas do Ipê, **sem ninguém
   confirmar** — é o número do algoritmo;
4. opcionalmente apaga do banco o que baixou só para medir (2 500 mamografias não cabem em qualquer disco);
5. grava a planilha de saída: as colunas originais e, ao lado, as do Ipê.

Pode parar e continuar: o andamento fica num arquivo ao lado da saída (`<saída>.andamento.json`), e ao recomeçar as
linhas já feitas não são refeitas.

Este módulo não tem Qt nem rede: quem busca, baixa, mede e apaga entra por funções (`Servicos`), para a janela
(`ui/lote_mama_dialogo.py`) ligar no Ipê e os testes ligarem em dublês. A planilha é lida e gravada sem biblioteca de
fora (o .xlsx é um zip de XML).
"""
from __future__ import annotations

import csv
import json
import logging
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

# situações de uma linha
MEDIDO = "medido"
SEM_ID = "linha sem ID ou sem data"
NAO_ACHADO = "não encontrado no PACS"
OUTRA_PESSOA = "nascimento não confere"
SEM_DOWNLOAD = "erro ao baixar"
SEM_IMAGENS = "sem mamografia 2D para medir"
ERRO = "erro"
PRONTAS = (MEDIDO, SEM_IMAGENS, OUTRA_PESSOA, SEM_ID)     # ao retomar, estas não são refeitas

GRAUS_BAC = {"ausente": "Ausente", "leve": "Leve", "moderada": "Moderada", "acentuada": "Acentuada"}
VISTAS = ("R-CC", "L-CC", "R-MLO", "L-MLO")

#: as colunas que o Ipê acrescenta, na ordem: (chave, título)
COLUNAS = [
    ("situacao", "Ipê: situação"), ("observacao", "Ipê: observação"), ("study_uid", "Ipê: Study UID"),
    ("accession", "Ipê: accession"), ("data_exame", "Ipê: data do exame"), ("descricao", "Ipê: descrição do exame"),
    ("exames_no_dia", "Ipê: exames MG no dia"), ("aparelho", "Ipê: aparelho"), ("de_onde", "Ipê: de onde veio"),
    ("densidade", "Ipê: densidade (rede NYU)"), ("prob_a", "Ipê: prob. A"), ("prob_b", "Ipê: prob. B"),
    ("prob_c", "Ipê: prob. C"), ("prob_d", "Ipê: prob. D"), ("densidade_aviso", "Ipê: densidade — aviso"),
    ("bac_grau", "Ipê: BAC grau (pela área)"), ("bac_area", "Ipê: BAC área, mama pior (mm²)"),
    ("bac_area_d", "Ipê: BAC área direita (mm²)"), ("bac_area_e", "Ipê: BAC área esquerda (mm²)"),
    ("bac_R-CC", "Ipê: BAC área CC direita (mm²)"), ("bac_L-CC", "Ipê: BAC área CC esquerda (mm²)"),
    ("bac_R-MLO", "Ipê: BAC área MLO direita (mm²)"), ("bac_L-MLO", "Ipê: BAC área MLO esquerda (mm²)"),
    ("csbi", "Ipê: CSBI estimado (0-3)"), ("csbi_vasos", "Ipê: vasos calcificados (soma das mamas)"),
    ("margolies", "Ipê: Margolies estimado (total)"), ("margolies_cat", "Ipê: Margolies estimado (categoria)"),
    ("loberant", "Ipê: Loberant estimado (0-3)"), ("bacss", "Ipê: BAC-SS estimado (maior mama)"),
    ("protese", "Ipê: prótese"), ("bac_imagens", "Ipê: imagens medidas"), ("bac_aviso", "Ipê: BAC — avisos"),
    ("medido_em", "Ipê: medido em"), ("versoes", "Ipê: versão das medidas"),
]
LEIA_ME = [
    "Colunas do Ipê — medidas automáticas, sem confirmação de um médico.",
    "",
    "Densidade: rede da NYU (Wu et al.), categoria BI-RADS A a D e a probabilidade de cada uma. Precisa das quatro "
    "incidências (CC e MLO dos dois lados).",
    "BAC (calcificação arterial da mama): rede SCU-Net (Emory). A área é a soma dos trechos calcificados alongados, "
    "em mm², em cada imagem; por mama vale a maior entre as imagens de campo inteiro; a do exame é a da mama pior.",
    "BAC grau (pela área): ausente < 5 mm²; leve < 30; moderada < 100; acentuada >= 100. Com prótese não há grau "
    "(a borda da prótese engana a rede).",
    "CSBI, Margolies, Loberant e BAC-SS: estimados a partir do traçado da rede (número de vasos, extensão, densidade) "
    "— são aproximações das escalas visuais, não a leitura de um radiologista.",
    "Situação: medido; não encontrado no PACS; nascimento não confere (o exame achado é de outra pessoa e não foi "
    "medido); erro ao baixar; sem mamografia 2D para medir; erro.",
    "Antes de usar na análise, confira uma amostra: abra o exame no Ipê pelo Study UID e veja o traçado.",
]


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
    sep = ";" if amostra.count(";") >= amostra.count(",") and ";" in amostra else ("\t" if "\t" in amostra else ",")
    return [list(l) for l in csv.reader(txt.splitlines(), delimiter=sep)]


def ler_planilha(caminho, aba: str | None = None) -> list[list]:
    return ler_csv(caminho) if str(caminho).lower().endswith((".csv", ".txt")) else ler_xlsx(caminho, aba)


def abas(caminho) -> list[str]:
    return [] if str(caminho).lower().endswith((".csv", ".txt")) else abas_do_xlsx(caminho)


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


# ====================================================================== a lista
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


def achar_colunas(cabecalho: list) -> dict:
    """Adivinha as colunas pelo título: {"id", "data", "nascimento", "nome"} → índice (ou -1)."""
    nomes = [_sem_acento(c).strip() for c in cabecalho]

    def acha(*testes) -> int:
        for t in testes:
            for i, n in enumerate(nomes):
                if n and t(n):
                    return i
        return -1
    return {
        "id": acha(lambda n: n in ("id", "patient id", "patientid", "id do paciente", "prontuario", "registro"),
                   lambda n: "prontu" in n or "patient id" in n or n.startswith("id ")),
        "data": acha(lambda n: "data" in n and "mamo" in n, lambda n: "mamo" in n and ("date" in n or "dia" in n),
                     lambda n: n in ("data do exame", "data exame", "study date", "data")),
        "nascimento": acha(lambda n: "nasc" in n or "birth" in n),
        "nome": acha(lambda n: n in ("paciente", "nome", "patient", "patient name", "nome do paciente")),
    }


@dataclass
class Linha:
    n: int                      # índice na planilha (0 = primeira linha de dados)
    pid: str
    data: str                   # AAAAMMDD
    nascimento: str = ""
    nome: str = ""

    @property
    def chave(self) -> str:
        return f"{self.pid}|{self.data}"


def montar_linhas(dados: list[list], colunas: dict) -> list[Linha]:
    """As linhas de dados (sem o cabeçalho) viram `Linha`; as vazias no fim são ignoradas."""
    def cel(linha, nome):
        i = colunas.get(nome, -1)
        return linha[i] if 0 <= i < len(linha) else None
    out = []
    for n, linha in enumerate(dados):
        if not any(v not in (None, "") for v in linha):
            continue
        out.append(Linha(n, para_id(cel(linha, "id")), para_data(cel(linha, "data")),
                         para_data(cel(linha, "nascimento")), str(cel(linha, "nome") or "").strip()))
    return out


# ====================================================================== o que entra na planilha
def _num(v, casas: int = 2):
    try:
        return round(float(v), casas)
    except (TypeError, ValueError):
        return None


def campos_da_medida(d: dict | None, c: dict | None) -> dict:
    """As medidas guardadas (densidade `d`, calcificações `c`) → as colunas da planilha."""
    out: dict = {}
    if d:
        out["densidade"] = (d.get("nyu") or "").upper()
        for letra, p in zip("abcd", d.get("nyu_probs") or []):
            out[f"prob_{letra}"] = _num(p, 4)
        avisos = [d.get("nyu_aviso") or ""] + list(d.get("avisos") or [])
        out["densidade_aviso"] = " ".join(a for a in avisos if a)
    if c:
        if c.get("sugestao"):
            out["bac_grau"] = GRAUS_BAC.get(c["sugestao"], c["sugestao"])
        out["bac_area"] = _num(c.get("area_mm2"))
        pm = c.get("por_mama") or {}
        out["bac_area_d"], out["bac_area_e"] = _num(pm.get("R")), _num(pm.get("L"))
        vistas = c.get("vistas") or {}
        for k in VISTAS:
            if k in vistas:
                out[f"bac_{k}"] = _num(vistas[k].get("area_mm2"))
        e = c.get("escalas") or {}
        if e:
            out["csbi"] = (e.get("csbi") or {}).get("grau")
            out["csbi_vasos"] = (e.get("csbi") or {}).get("vasos")
            out["margolies"] = (e.get("margolies") or {}).get("total")
            out["margolies_cat"] = {"negativa": "Negativa", "leve": "Leve", "moderada_acentuada": "Moderada a acentuada"} \
                .get((e.get("margolies") or {}).get("categoria"), "")
            out["loberant"] = (e.get("loberant") or {}).get("grau")
            out["bacss"] = (e.get("bacss") or {}).get("maior")
        imagens = c.get("imagens") or []
        out["protese"] = "sim" if any(v.get("protese") for v in imagens) else ("não" if imagens else "")
        out["bac_imagens"] = len(imagens) or None
        out["bac_aviso"] = " ".join(a for a in [c.get("aviso") or ""] + list(c.get("avisos") or []) if a)
        out["aparelho"] = c.get("aparelho") or ""
    if d and not out.get("aparelho"):
        out["aparelho"] = d.get("aparelho") or ""
    out["medido_em"] = (c or {}).get("quando") or (d or {}).get("quando") or ""
    out["versoes"] = f"densidade {(d or {}).get('versao', '-')}, calcificações {(c or {}).get('versao', '-')}"
    return out


def tem_medida(campos: dict) -> bool:
    return bool(campos.get("densidade")) or campos.get("bac_area") is not None


# ====================================================================== o lote
@dataclass
class Servicos:
    """O que o lote precisa do Ipê — funções, para a janela ligar no programa e os testes em dublês.

    - `local(pid, data)` → exames MG do banco do Ipê nesse dia: [{"study_uid", "birth_date", "accession", …}]
    - `pacs(pid, data)` → o mesmo, do PACS (C-FIND)
    - `baixar(exame, parar)` → (deu certo, mensagem)
    - `medir(study_uid, parar)` → (densidade, calcificações) guardadas, depois de medir o que faltava
    - `apagar(study_uid)` → tira do banco o que foi baixado só para medir
    """
    local: callable
    pacs: callable
    baixar: callable
    medir: callable
    apagar: callable


@dataclass
class Opcoes:
    apagar_depois: bool = True          # apagar do banco o exame que foi baixado só para medir
    refazer_erros: bool = True          # ao retomar: tentar de novo os não encontrados e os com erro
    limite: int = 0                     # 0 = todos; N = só as N primeiras linhas por fazer (para testar)
    gravar_a_cada: int = 25             # linhas entre duas gravações da planilha


@dataclass
class Andamento:
    total: int = 0
    feitos: int = 0                     # linhas com resposta (nesta rodada e nas anteriores)
    nesta_rodada: int = 0
    contagem: dict = field(default_factory=dict)
    atual: str = ""
    inicio: float = 0.0

    def falta_s(self) -> float | None:
        """Quanto falta, pelo ritmo desta rodada (None antes de três linhas)."""
        if self.nesta_rodada < 3:
            return None
        por_linha = (time.time() - self.inicio) / self.nesta_rodada
        return por_linha * max(0, self.total - self.feitos)


def _confere_nascimento(da_lista: str, do_exame: str) -> bool:
    """Falso só quando as duas datas existem e são diferentes."""
    a, b = para_data(da_lista), para_data(do_exame)
    return not (a and b and a != b)


def _escolher(exames: list[dict]) -> dict:
    """Entre os exames de mamografia do dia, o que tem mais imagens (o complemento costuma ter menos)."""
    return max(exames, key=lambda e: (int(e.get("num_images") or 0), str(e.get("study_time") or "")))


class Lote:
    def __init__(self, cabecalho: list, dados: list[list], linhas: list[Linha], servicos: Servicos, saida,
                 opcoes: Opcoes | None = None, leia_me: list[str] | None = None) -> None:
        self.cabecalho = [("" if c is None else c) for c in cabecalho]
        self.dados = dados
        self.linhas = linhas
        self.s = servicos
        self.saida = Path(saida)
        self.op = opcoes or Opcoes()
        self.leia_me = leia_me or LEIA_ME
        self.arquivo_andamento = self.saida.with_name(self.saida.name + ".andamento.json")
        self.resultados: dict[str, dict] = {}
        self.carregar()

    # ------------------------------------------------------------ andamento em disco
    def carregar(self) -> None:
        try:
            self.resultados = json.loads(self.arquivo_andamento.read_text(encoding="utf-8")).get("linhas", {})
        except (OSError, ValueError):
            self.resultados = {}

    def guardar(self) -> None:
        tmp = self.arquivo_andamento.with_name(self.arquivo_andamento.name + ".gravando")
        tmp.write_text(json.dumps({"versao": 1, "linhas": self.resultados}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.arquivo_andamento)

    def pronta(self, l: Linha) -> bool:
        r = self.resultados.get(l.chave)
        if not r:
            return False
        return r.get("situacao") in PRONTAS or not self.op.refazer_erros

    def por_fazer(self) -> list[Linha]:
        vistos = set()
        out = []
        for l in self.linhas:
            if l.chave in vistos or self.pronta(l):
                continue
            vistos.add(l.chave)
            out.append(l)
        return out[:self.op.limite] if self.op.limite else out

    def contagem(self) -> dict:
        c: dict[str, int] = {}
        for l in self.linhas:
            r = self.resultados.get(l.chave)
            if r:
                c[r.get("situacao", ERRO)] = c.get(r.get("situacao", ERRO), 0) + 1
        return c

    # ------------------------------------------------------------ uma linha
    def uma(self, l: Linha, parar=None) -> dict:
        if not l.pid or not l.data:
            return {"situacao": SEM_ID}
        r: dict = {}
        exames = self.s.local(l.pid, l.data)
        veio_do_pacs = False
        if exames:
            r["de_onde"] = "já estava no Ipê"
        else:
            exames = self.s.pacs(l.pid, l.data)
            veio_do_pacs = True
            r["de_onde"] = "baixado do PACS"
        if not exames:
            return {"situacao": NAO_ACHADO, "observacao": f"Nenhuma mamografia de {l.pid} em "
                    f"{l.data[6:8]}/{l.data[4:6]}/{l.data[:4]}."}
        ex = _escolher(exames)
        r.update({"study_uid": ex.get("study_uid", ""), "accession": ex.get("accession", ""),
                  "data_exame": ex.get("study_date", ""), "descricao": ex.get("description", ""),
                  "exames_no_dia": len(exames)})
        if not _confere_nascimento(l.nascimento, ex.get("birth_date", "")):
            r["de_onde"] = ""
            return dict(r, situacao=OUTRA_PESSOA, observacao="A data de nascimento do exame achado é outra: "
                        "não foi baixado nem medido.")
        if len(exames) > 1:
            r["observacao"] = f"No dia há {len(exames)} exames de mamografia: medido o de mais imagens."
        uid = r["study_uid"]
        if veio_do_pacs:
            ok, msg = self.s.baixar(ex, parar)
            if parar is not None and parar.is_set():
                raise InterruptedError
            if not ok:
                return dict(r, situacao=SEM_DOWNLOAD, observacao=msg)
        try:
            d, c = self.s.medir(uid, parar)
            if parar is not None and parar.is_set():
                raise InterruptedError
            campos = campos_da_medida(d, c)
            r.update({k: v for k, v in campos.items() if v not in (None, "")})
            r["situacao"] = MEDIDO if tem_medida(campos) else SEM_IMAGENS
        finally:
            if veio_do_pacs and self.op.apagar_depois and not (parar is not None and parar.is_set()):
                try:
                    self.s.apagar(uid)
                except Exception as e:  # noqa: BLE001 - não conseguir apagar não estraga a medida
                    log.warning("lote da mama: apagar %s: %s", uid, e)
                    r["observacao"] = " ".join(x for x in (r.get("observacao", ""), "Não foi possível apagar o exame do Ipê.") if x)
        return r

    # ------------------------------------------------------------ o lote inteiro
    def rodar(self, parar=None, avisar=None) -> Andamento:
        """Faz as linhas que faltam, uma por vez. `avisar(andamento, linha, resultado)` a cada linha.
        Para em `parar` (um threading.Event) no fim da linha em curso; o que foi feito fica gravado."""
        fila = self.por_fazer()
        a = Andamento(total=len({l.chave for l in self.linhas}), inicio=time.time())
        a.feitos = a.total - len(self.por_fazer_sem_limite())
        a.contagem = self.contagem()
        desde_gravar = 0
        try:
            for l in fila:
                if parar is not None and parar.is_set():
                    break
                a.atual = l.pid
                try:
                    r = self.uma(l, parar)
                except InterruptedError:
                    break
                except Exception as e:  # noqa: BLE001 - uma linha ruim não para o lote
                    log.exception("lote da mama: linha %s", l.n + 2)
                    r = {"situacao": ERRO, "observacao": str(e)[:300]}
                self.resultados[l.chave] = r
                a.feitos += 1                    # as que vão ser refeitas não estavam na conta de partida
                a.nesta_rodada += 1
                a.contagem = self.contagem()
                desde_gravar += 1
                self.guardar()
                if desde_gravar >= max(1, self.op.gravar_a_cada):
                    self.gravar_planilha()
                    desde_gravar = 0
                if avisar is not None:
                    try:
                        avisar(a, l, r)
                    except Exception:  # noqa: BLE001
                        log.debug("lote da mama: aviso", exc_info=True)
        finally:
            a.atual = ""
            self.guardar()
            self.gravar_planilha()
        return a

    def por_fazer_sem_limite(self) -> list[Linha]:
        limite, self.op.limite = self.op.limite, 0
        try:
            return self.por_fazer()
        finally:
            self.op.limite = limite

    # ------------------------------------------------------------ a planilha de saída
    def tabela(self) -> list[list]:
        largura = max([len(self.cabecalho)] + [len(x) for x in self.dados]) if self.dados else len(self.cabecalho)
        cab = list(self.cabecalho) + [""] * (largura - len(self.cabecalho)) + [t for _k, t in COLUNAS]
        out = [cab]
        por_n = {l.n: l for l in self.linhas}
        for n, linha in enumerate(self.dados):
            l = por_n.get(n)
            if l is None:
                continue
            r = self.resultados.get(l.chave) or {}
            out.append(list(linha) + [None] * (largura - len(linha)) + [r.get(k) for k, _t in COLUNAS])
        return out

    def resumo(self) -> list[list]:
        c = self.contagem()
        total = len(self.linhas)
        linhas = [["Resumo do lote", ""], ["Linhas na lista", total], ["Com resposta", sum(c.values())]]
        linhas += [[k, v] for k, v in sorted(c.items(), key=lambda kv: -kv[1])]
        dens: dict[str, int] = {}
        bac: dict[str, int] = {}
        for l in self.linhas:
            r = self.resultados.get(l.chave) or {}
            if r.get("densidade"):
                dens[r["densidade"]] = dens.get(r["densidade"], 0) + 1
            if r.get("bac_grau"):
                bac[r["bac_grau"]] = bac.get(r["bac_grau"], 0) + 1
        linhas += [["", ""], ["Densidade (rede)", ""]] + [[k, dens[k]] for k in sorted(dens)]
        linhas += [["", ""], ["BAC grau (pela área)", ""]] + [[k, bac[k]] for k in GRAUS_BAC.values() if k in bac]
        linhas += [["", ""], ["Gravado em", time.strftime("%d/%m/%Y %H:%M")]]
        return linhas

    def gravar_planilha(self) -> Path:
        gravar_xlsx(self.saida, [("Resultados", self.tabela()), ("Resumo", self.resumo()),
                                 ("LEIA-ME", [[t] for t in self.leia_me])])
        return self.saida
