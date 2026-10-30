"""Monta o catálogo de textos em português (ipe/locale/pt-BR.json).

Varre o código à procura dos textos que aparecem na tela: literais e frases montadas com f-string
(essas viram "padrões", com {} no lugar das partes que mudam).

Uso:  python tools/i18n_extract.py [--check]
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "ipe"
OUT = SRC / "locale" / "pt-BR.json"

# mesh_fmt.py é só formato de arquivo (OBJ, PLY, glTF, 3MF): nada ali aparece na tela
SKIP_FILES = {"sample_data.py", "i18n.py", "qt_i18n.py", "mesh_fmt.py",
              "creditos.py"}   # créditos: nomes, licenças e links (0.99.13)
SKIP_DIRS = {"locale"}
ACCENTS = re.compile(r"[áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÇ]")
WORDS = re.compile(r"\b(de|da|do|das|dos|para|não|com|sem|em|no|na|nos|nas|os|as|um|uma|ao|à|e|ou|"
                   r"que|este|esta|esse|essa|pelo|pela|por|se|ser|está|são|tem|há|já|só|mais|menos|"
                   r"abrir|salvar|apagar|novo|nova|todos|todas|imagem|imagens|exame|exames|série|"
                   r"séries|medida|medidas|janela|quadro|quadros|laudo|lesão|lesões|nó|nós)\b", re.I)
EXTRA_OK = {"OK", "Cancelar", "Fechar", "Sim", "Não", "Salvar", "Abrir", "Apagar", "Remover", "Editar",
            "Duplicar", "Novo", "Nova", "Cor", "Filme", "Zoom", "Pan", "Ajuda", "Usuários", "Listas",
            "Reunião", "Monitor", "Atualizar", "Importar", "Exportar", "Enviar", "Imprimir", "Laudo",
            "Lesões", "Chave", "Ocultar", "Régua", "Ângulo", "Elipse", "Retângulo", "Polígono", "Seta",
            "Texto", "Lápis", "Coluna", "Curva", "Calibrar", "Quadrante", "Lupa", "Segmentar", "Oblíquo",
            "Curvo", "Dinâmica", "Fusão", "Sincronizar", "Anteriores", "Mais", "Configurações", "Voltar",
            "Esquerdo", "Direito", "Meio", "Roda", "Ctrl+roda", "Shift+roda", "EXAMES"}
# palavras técnicas que parecem rótulo de uma palavra só (tags DICOM, nomes de pasta)
NOT_UI = {
    # termos das regiões e dos tipos de série da barra (0.99.12): palavras de busca, não texto de tela
    'HEAD|BRAIN|CRANIO|CRANIUM|SKULL|ENCEFALO|CEREBR|SELA|HIPOFISE|PITUIT|ORBITA|ORBIT',
    'NECK|PESCOCO|CAROTID|CAROTIDA|CAROTIDAS|TIREOIDE|THYROID|LARING|LARYNX|FARING|PHARYN|TSA|SUPRA AORT|SUPRAAORT|TRONCOS SUPRA|PAROTID|SUBMANDIB|CERVICAL',
    'FACE|FACIAL|SEIOS|SINUS|PARANASAL|MANDIB|MAXIL|ATM|TMJ|DENTAL|ODONTO|CBCT|MASTOID|OUVIDO|TEMPORAL BONE|ROCHED',
    'BREAST|MAMA|MAMAS|MAMARIA|MAMOGRAF|MAMMO',
    'CHEST|THORAX|TORAX|TORACIC|LUNG|PULMAO|PULMON',
    'HEART|CARDIAC|CARDIACA|CORONAR|CORACAO|CARDIO',
    'ABD|ABDOM|LIVER|FIGADO|HEPAT|PANCREA|RENAL|RINS|RIM|KIDNEY|ENTERO|COLANGIO|MRCP|ADRENAL|SUPRARREN',
    'PELV|PELVE|PROSTAT|UTER|UTERO|OVARI|RETO|RECTUM|BEXIGA|BLADDER|ENDOMETR',
    'SPINE|COLUNA|CSPINE|TSPINE|LSPINE|LOMBAR|LUMBAR|LOMBOSSACR|DORSAL|SACR|VERTEB|CERVICAL',
    'KNEE|JOELHO|SHOULDER|OMBRO|QUADRIL|ANKLE|TORNOZELO|WRIST|PUNHO|MAO|HAND|FOOT|PE|ELBOW|COTOVELO|EXTREMIT|MEMBRO|COXA|PERNA|BRACO|ANTEBRACO',
    'ANGIO|ANGIOTC|ANGIORM|CTA|MRA|ATC|ARM|TOF|CEMRA|CE MRA|TRICKS|TWIST',
    'MPRAGE|MP RAGE|BRAVO|FSPGR|SPGR|3D T1|T1 3D|T13D|3DT1|T1W 3D|3D T1W|CUBE T1|T1 CUBE|TFL3D|VISTA T1|T1 VISTA',
    'CUBE|SPACE|VISTA|FIESTA|CISS|DRIVE|3D T2|T2 3D|T23D|3DT2',
    'DYN|DYNAMIC|DINAM|DINAMICO|DINAMICA|DCE|VIBRANT|THRIVE|DISCO|PERFUS|PERFUSION',
    "anteriores para a tira",
    # 0.99.9: log
    "copiar o quadro", "não gravei o nível de anotação", "série do layout da dinâmica",
    # 0.90: nome de etapa de fábrica acrescentada ao protocolo dele (vai para o log)
    "x ▸ x",
    # 0.91: log
    "janela do MIP 3D", "dinâmica da etapa", "fechar a dinâmica da etapa",
    # 0.95: texto do arquivo DICOM procurado (ViewModifier), não é tela
    "implant displaced", "implant-displaced",
    # 0.89: log do OCR do filme montado e o nome interno das fontes de leitura
    "OCR do filme montado %r", "OCR na chegada: paciente do filme montado %r não identificado", "imagem x (x)",
    # 0.88: dados dos protocolos de fábrica (nomes e padrões ficam gravados como estão), rótulos de
    # dado e mensagens de log das etapas
    "CRANIO|CRÂNIO|ENCEFALO|ENCÉFALO|BRAIN|HEAD", "MEDIAST|PARTES MOLES|SOFT|STANDARD|PADRAO|AXIAL",
    "MPRAGE|BRAVO|3D T1|T1 3D|T1 POS|GD", "PULM|LUNG|PARENQ|ALTA RES|HR|AXIAL",
    "T1 POS|T1 GD|T1+C|POS|GD|MPRAGE|BRAVO|3D T1", "T1 SE|T1 FSE|T1", "TORAX|TÓRAX|CHEST|THORAX",
    "TC de tórax", "RM de crânio", "Pulmão MIP", "Pós-contraste", "Sem contraste", "MIP da subtração",
    "T2, FLAIR e difusão", "anterior do protocolo", "janela %r do protocolo não entendida",
    "posição do quadro", "protocolo com etapas %r", "protocolos de exibição de fábrica",
    "sincronia da etapa", "x (W x / L x)", "x x x mm", "MPR x  x x mm", "janela x", "Etapa x", "Etapa 1",
    # 0.86: rótulos de dado nas listas da regra do filme automático e pedaços do resumo
    "x (outro nome)", "x (x)", "chamando", "x×x x", "nós DICOM para a regra", "identidades para a regra",
    "painel: impressões recebidas", "Montando o filme das imagens mandadas à impressora",
    # 0.85: rótulos de dado nas listas da regra (começam com o AE/nome) e pedaços do resumo da regra
    # (padrão de f-string se escreve com x no lugar de {}: é assim que looks_ui o compara)
    "x (não visto)", "x (porta x) — x", "x (sem nome)", "x (servidor apagado)", "Resumo:",
    "recebido em",
    "x (cópia x)", "Limpeza automática das impressões", "histórico de envios", "modalidade dos filmes",
    "servidores de impressão ao mudar os módulos", "Impressões (recebidas", "Limpeza: trabalho %s",
    "Modalidade do trabalho %s", "Limpeza automática: %d trabalho(s) de impressão apagado(s)",
    "\\s*\\(cópia(?: \\d+)?\\)$", "painel: impressões recebidas",
    "OCR (RapidOCR) falhou", "OCR (Tesseract) falhou", "comparar o OCR com o banco", "[^A-Za-zÀ-ÿ]+",
    "delete previous film copy in study", "Falha ao montar o filme das imagens recebidas",
    "Montando o filme das imagens mandadas à impressora", "Origem das imagens recebidas na impressora",
    # filme no formato da AW (ui/film/salvar_dicom.py): valores DICOM, não texto de tela
    "AW electronic film", "AW electronic pages", "AW41 EF TID", "Ipe film",
    "Document Title Modifier", "Electronic Film Presentation", "HAS CONCEPT MOD", "Page Presentation",
    "Person Observer's Organization Name", "Relative horizontal position of top left corner",
    "Relative horizontal size", "Relative vertical position of top left corner", "Relative vertical size",
    "SCREEN SAVE", "Slot Group Presentation", "Slot Presentation", "salvar o filme no exame",
    "CC, MLO", "densidade: sem VOI LUT utilizável",
          # texto de log: vai para o arquivo, não para a tela
          "mamografia: nenhum protocolo combina com %r",
          "mamografia: protocolo %r não subiu (sem imagens com lado reconhecido)",
          "monitores: %r é MG mas nenhum protocolo de mamografia combina",
          "monitores: o protocolo de mamografia %r não tem etapa nenhuma",
          "empacotado", "código", "volumes do CAD", "referências da mama",
          "apagar série", "recarregar séries da aba",
          "abrir a série da medida", "nomes das lesões", "painel de medidas", "rótulo da medida",
          "regras de dinâmico",
          "quadro que não abriu no pré-cálculo", "falhou a conta da mama inteira",
          # chaves internas da máscara da mama e do pré-cálculo: nome de estado, não texto de tela
          "corte na parede torácica", "sem parede encontrada", "sem corte posterior",
          "não achei dinâmica neste exame", "cache cheio",
          "não consegui guardar o layout deste exame",
          "Mn",                       # categoria unicode, no normalizador de acentos
          # pedaço de HTML montado por concatenação: não é texto de tela
          "<span style='color:", "<table cellpadding=3>", "</td><td align='right'><b>",
    "passagem da compressão", "transferências ativas","Polarity", "Trim", "Destination", "Impressoes", "Printer", "Normal", "Rule",
          "MARIA SOUZA", "MG_SALA1", "Radiopharmaceutical",
          # nomes de tecla do QKeySequence (atalhos de fábrica): não se traduzem
          "Right", "Left",
          # valores de SeriesType (0054,1000) e textos de ViewCodeSequence: vêm do DICOM,
          # não são o que aparece na tela (o que aparece é a tradução deles)
          "WHOLE BODY", "GATED TOMO", "RECON TOMO", "RECON GATED TOMO",
          "right anterior oblique", "left anterior oblique", "right posterior oblique",
          "left posterior oblique", "right lateral", "left lateral",
          # palavras procuradas na descrição do exame para adivinhar a receita de MN
          "CAPTAÇÃO", "CAPTACAO", "CÓLON", "COLONICO", "TIREÓIDE", "TRÂNSITO", "TRANSITO",
          "PARATIREOIDES",
          # nomes de série que a estação AW grava: são dado DICOM procurado, não texto de tela
          "aw electronic film", "aw electronic pages",
          # texto de log (vai para o arquivo de registro, não para a tela)
          "geometria da tomossíntese", "séries de filme da AW",
          "abrindo a lista de impressões", "modelo 3D", "segmentações do exame",
          "superfície", "maior componente",
          "densidade: a medição falhou", "densidade: não consegui abrir a imagem",
          "densidade: não consegui aplicar a máscara", "densidade: não li as imagens da série",
          "densidade: não li as séries do exame",
          # "Densidade" é a *fonte* do objeto de overlay: é chave de comparação, não texto de tela
          "Densidade",
          "rede de densidade", "a rede só recebe imagem 2D",
          "não consegui listar as séries para dividir", "não consegui montar o menu desta janela",
          "ação do menu falhou num dos monitores", "não consegui religar os monitores"}
BAD_SUBSTR = ("ALTER TABLE", "NOT NULL DEFAULT",
              "background:", "QWidget{", "QPushButton", "QMenu{", "QToolBar{", "QLabel{", "http://",
              "https://", "1.2.840", "%Y", "\\\\", "::", "-->", "<html", "utf-8", "application/",
              "font-size", "color:#", "px;", "border:")
BAD_EXACT = {"", " ", "\n", "{}", "{:.1f}", "…"}
TECH = ("%s", "%d", "%(", "%1", "%u", "\r\n", "ADD COLUMN", "-m ipe", "Connection:",
        "Content-Type", "text/html", "MimeType", "x-scheme-handler")
DICOM_KW = re.compile(r"^[A-Z][A-Za-z0-9]+$")          # PatientName, SeriesInstanceUID…
# rótulo de uma palavra só (menus e barra de ferramentas): Arquivo, &Rede, A&juda, Importar…
WORD_LABEL = re.compile(r"^[A-ZÀ-Ý][a-zà-ÿ]{1,18}$")


def one_word(t: str) -> bool:
    """Uma palavra só, ainda que com & do atalho e … no fim."""
    return bool(WORD_LABEL.match(t.replace("&", "", 1).rstrip("…:.")))


def looks_ui(text: str) -> bool:
    t = text.strip()
    if t in BAD_EXACT or t in NOT_UI or len(t) < 2 or len(t) > 600:
        return False
    if any(b in text for b in BAD_SUBSTR) or any(b in text for b in TECH):
        return False
    if text.startswith(("\n", "\r", "\t")):
        return False
    if t in EXTRA_OK or one_word(t):
        return True
    if DICOM_KW.match(t):
        return False
    if re.match(r"^[a-z0-9_.:/\\-]+$", t):             # chaves, caminhos, ids
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]", t):
        return False
    if " " not in t and not ACCENTS.search(t):
        return False
    if len(t) > 3 and not (ACCENTS.search(t) or WORDS.search(t) or " " in t):
        return False
    return True


def skeleton(node: ast.JoinedStr) -> str | None:
    """f-string -> texto com {} no lugar das partes que mudam."""
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
        else:
            parts.append("{}")
    text = "".join(parts)
    if text.strip("{} \n") == "" or text.count("{}") > 6:
        return None
    return text


def collect() -> tuple[set, set]:
    strings, patterns = set(), set()
    for f in sorted(SRC.rglob("*.py")):
        if f.name in SKIP_FILES or any(p in SKIP_DIRS for p in f.parts):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        # os pedaços literais de uma f-string não são textos por si: o texto é o padrão
        # inteiro. Sem isto, f"{nome}: não achei" vira também ": não achei" no catálogo.
        dentro_de_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
                             for v in n.values if isinstance(v, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in dentro_de_fstring:
                    continue
                if isinstance(getattr(node, "parent", None), ast.Expr):
                    continue
                if looks_ui(node.value):
                    strings.add(node.value)
            elif isinstance(node, ast.JoinedStr):
                sk = skeleton(node)
                if sk and looks_ui(sk.replace("{}", "x")):
                    patterns.add(sk)
    # fragmentos de concatenação que já estão dentro de um padrão (ex.: " imagens baixadas")
    joined = "\u0001".join(patterns)
    frag = {t for t in strings if (t != t.strip() or len(t) < 6) and t.strip() and t.strip() in joined}
    frag -= EXTRA_OK                       # palavras curtas que são mesmo texto de tela
    frag = {t for t in frag if t != t.strip() or not one_word(t)}
    strings -= frag
    # docstrings: fora
    docs = set()
    for f in sorted(SRC.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                d = ast.get_docstring(node, clean=False)
                if d:
                    docs.add(d)
    return strings - docs, {p for p in patterns if p not in docs}


def main() -> int:
    strings, patterns = collect()
    data = {"strings": sorted(strings), "patterns": sorted(patterns)}
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"strings": [], "patterns": []}
    if "--check" in sys.argv:
        new = set(data["strings"]) - set(old["strings"])
        gone = set(old["strings"]) - set(data["strings"])
        print(f"{len(data['strings'])} textos, {len(data['patterns'])} padrões; "
              f"{len(new)} novos, {len(gone)} sumiram")
        for t in sorted(new)[:40]:
            print("  +", t[:100])
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT}: {len(data['strings'])} textos e {len(data['patterns'])} padrões")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
