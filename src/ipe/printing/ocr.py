"""Ler o cabeçalho queimado na folha de impressão (OCR) e achar o paciente no banco.

É o último recurso para descobrir de quem é um trabalho de impressão DICOM: o padrão não manda
nome nem ID, e o texto está nos pixels. Erra às vezes — serve como sugestão, nunca como verdade.

**Leitor (0.80)**: o RapidOCR (modelos ONNX que vêm dentro do pacote), embutido no programa —
nada para instalar em cada computador e funciona sem internet. Até a 0.79 o programa dependia do
Tesseract instalado à parte, e na prática o botão vivia apagado. O Tesseract continua como reserva,
se estiver instalado e o RapidOCR não.

Medido em duas folhas reais da AW (GE, A4 2560 × 1810): o nome sai inteiro numa ("SOARES JANAINA
ANGELICAPEREIRA") e grudado e com letras trocadas na outra ("QARNIEIROISABELLEVTORIA SOUSA" para
CARNEIRO, ISABELLE VITORIA SOUSA). Por isso o texto lido não vai direto para o campo Nome: ele é
comparado com os pacientes do banco sem espaço, sem acento e tolerando letra trocada
(`combinar`), e quem confirma é o médico.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

_motor = None          # RapidOCR carregado uma vez (≈0,3 s); depois cada folha leva ~2 s
# A janela de identificação (thread da tela) e a chegada de impressão (thread da impressora)
# podem ler ao mesmo tempo: um leitor só, uma leitura por vez.
_trava = threading.Lock()


def _tem_rapidocr() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _tem_tesseract() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def available() -> bool:
    return _tem_rapidocr() or _tem_tesseract()


def motivo_indisponivel() -> str:
    """Por que o OCR não está disponível, em português, para a dica do botão."""
    if available():
        return ""
    return ("O leitor de texto (RapidOCR) não está instalado neste computador. Rode o instalar.bat "
            "de novo (ou: .venv\\Scripts\\python -m pip install rapidocr_onnxruntime).")


def _rapid():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR()
    return _motor


def _cinza(pixels):
    import numpy as np
    a = np.asarray(pixels)
    if a.ndim == 3:
        a = a[..., :3].mean(axis=2)
    a = a.astype(np.float32)
    if a.max() <= a.min():
        return None
    return ((a - a.min()) / (a.max() - a.min()) * 255.0).astype(np.uint8)


def linhas_em_ordem(caixas) -> list[str]:
    """Junta as caixas do OCR em linhas de leitura: de cima para baixo, da esquerda para a direita.

    `caixas`: [(pontos, texto, confiança)], com `pontos[0]` = canto superior esquerdo.
    """
    itens = []
    for pontos, texto, _conf in caixas or []:
        x, y = float(pontos[0][0]), float(pontos[0][1])
        alto = abs(float(pontos[3][1]) - y) if len(pontos) > 3 else 12.0
        itens.append((y, x, max(alto, 6.0), str(texto)))
    itens.sort()
    linhas: list[list[tuple]] = []
    for it in itens:
        if linhas and abs(it[0] - linhas[-1][0][0]) <= it[2] * 0.6:
            linhas[-1].append(it)
        else:
            linhas.append([it])
    return ["  ".join(t for _y, _x, _h, t in sorted(l, key=lambda i: i[1])) for l in linhas]


def read_header(pixels, faixa: float = 0.14, parte: str = "cima") -> str:
    """Texto de uma faixa da folha: `cima` (onde a maioria das modalidades escreve paciente e
    exame), `baixo` (rodapé) ou `tudo` (a folha inteira, o último recurso — mais lento)."""
    g = _cinza(pixels)
    if g is None:
        return ""
    alto = max(8, int(g.shape[0] * faixa))
    corte = g[:alto] if parte == "cima" else g[-alto:] if parte == "baixo" else g
    if _tem_rapidocr():
        import numpy as np
        if corte.shape[1] < 1200:                       # folha pequena: letra pequena demais
            corte = np.repeat(np.repeat(corte, 2, axis=0), 2, axis=1)
        try:
            with _trava:
                caixas, _tempo = _rapid()(corte)
        except Exception:  # noqa: BLE001
            log.exception("OCR (RapidOCR) falhou")
            return ""
        return "\n".join(linhas_em_ordem(caixas))
    if _tem_tesseract():
        import pytesseract
        from PIL import Image
        c = corte.astype("float32")
        if c.mean() < 110:                              # letra clara em fundo escuro: inverte
            c = 255.0 - c
        img = Image.fromarray(c.astype("uint8"))
        img = img.resize((img.width * 2, img.height * 2))
        try:
            return pytesseract.image_to_string(img, lang="por+eng")
        except Exception:  # noqa: BLE001
            log.exception("OCR (Tesseract) falhou")
    return ""


# ------------------------------------------------------------------ nome e ID no texto
_ID = re.compile(r"\b(\d{5,12})\b")
# o que aparece nos cabeçalhos das modalidades e não é nome de gente
_NAO_NOME = {"VIBRANT", "DFOV", "MIP", "CUT", "EX", "SE", "IM", "PH", "AX", "SAG", "COR", "MAMOGRAFIA",
             "TOMOGRAFIA", "RESSONANCIA", "CONTRASTE", "SERIES", "IMAGE", "PAGE", "FOLHA"}


def compactar(texto: str) -> str:
    """Só letras e números, maiúsculas e sem acento: "Soares, Janaína" -> "SOARESJANAINA"."""
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def guess(texto: str) -> tuple[str, str]:
    """Nome e ID a partir do texto lido: o pedaço com mais cara de nome e o primeiro número longo."""
    nome, ident = "", ""
    melhor = 0
    for linha in (texto or "").splitlines():
        if not ident:
            m = _ID.search(linha)
            if m:
                ident = m.group(1)
        for pedaco in re.split(r"[:|]|\s{2,}", linha):
            p = " ".join(pedaco.replace(",", " ").split()).strip(" .;-")
            palavras = [w for w in p.split() if w.isalpha()]
            letras = sum(ch.isalpha() or ch == " " for ch in p)
            if len(p) < 8 or len(palavras) < 2 or letras < 0.85 * len(p):
                continue
            if {compactar(w) for w in palavras} & _NAO_NOME:
                continue
            if len(p) > melhor:
                nome, melhor = p, len(p)
    return nome, ident


# ------------------------------------------------------------------ achar o paciente no banco
def _parecido(token: str, texto: str) -> float:
    """O quanto o pedaço do nome aparece no texto: 1 se aparece igual, senão a melhor semelhança
    contra um trecho do mesmo tamanho (letra trocada, letra a menos)."""
    if token in texto:
        return 1.0
    n = len(token)
    melhor = 0.0
    for tam in (n - 1, n, n + 1):
        if tam < 3:
            continue
        for i in range(0, max(1, len(texto) - tam + 1)):
            r = SequenceMatcher(None, token, texto[i:i + tam]).ratio()
            if r > melhor:
                melhor = r
    return melhor


def _parcial(nome: str, texto: str) -> float:
    """Semelhança do nome inteiro (na ordem) com o melhor trecho do texto do mesmo tamanho."""
    if nome in texto:
        return 1.0
    n = len(nome)
    if n > len(texto) + 2:                   # texto mais curto que o nome: compara os dois inteiros
        return SequenceMatcher(None, nome, texto).ratio()
    melhor = 0.0
    for tam in (n - 2, n - 1, n, n + 1, n + 2):
        if tam < 4 or tam > len(texto):
            continue
        for i in range(0, len(texto) - tam + 1):
            sm = SequenceMatcher(None, nome, texto[i:i + tam])
            if sm.real_quick_ratio() <= melhor or sm.quick_ratio() <= melhor:
                continue
            r = sm.ratio()
            if r > melhor:
                melhor = r
    return melhor


def combinar(texto: str, estudos: list[dict], limite: int = 6, minimo: float = 0.7) -> list[dict]:
    """Os pacientes do banco cujo nome (ou ID) aparece no texto lido, do mais provável ao menos.

    Duas passadas: (1) cada pedaço do nome é procurado no texto — igual, ou com letra trocada —, e
    só os pacientes com algum pedaço igual entram na conta (a semelhança de cada pedaço é medida uma
    vez só, porque sobrenome se repete muito); (2) os mais prováveis são conferidos pelo **nome
    inteiro, na ordem**, contra o trecho mais parecido do texto — é o que separa "SOARES JANAINA
    ANGELICA PEREIRA" de alguém que só tem SOARES e PEREIRA no nome.

    `estudos`: dicionários com patient_name, patient_id, study_uid, when… (um por exame). Devolve
    um por paciente — o exame mais recente dele —, com `score` de 0 a 1 e `ocr` = True.
    """
    alvo = compactar(texto)
    if len(alvo) < 6:
        return []
    numeros = set(_ID.findall(texto or ""))
    por_paciente: dict[tuple, dict] = {}
    for e in estudos:
        chave = (compactar(e.get("patient_name", "")), e.get("patient_id", ""))
        atual = por_paciente.get(chave)
        if atual is None or (e.get("when") and (atual.get("when") is None or e["when"] > atual["when"])):
            por_paciente[chave] = e
    memo: dict[str, float] = {}

    def pedaco(t: str) -> float:
        if t not in memo:
            memo[t] = 1.0 if t in alvo else max(0.0, (_parecido(t, alvo) - 0.6) / 0.4)
        return memo[t]

    previa = []
    for (nome_c, pid), e in por_paciente.items():
        tokens = [compactar(t) for t in re.split(r"[^A-Za-zÀ-ÿ]+", e.get("patient_name", ""))]
        tokens = [t for t in tokens if len(t) >= 3]
        if not tokens:
            continue
        id_bate = bool(pid) and pid in numeros
        if not id_bate and not any(len(t) >= 4 and t in alvo for t in tokens):
            continue                     # nenhum pedaço igual: nem vale a conta mais cara
        total = sum(len(t) for t in tokens)
        nota = sum(len(t) * pedaco(t) for t in tokens) / total
        previa.append((nota, id_bate, nome_c, e))
    previa.sort(key=lambda x: -x[0])
    saida = []
    for nota, id_bate, nome_c, e in previa[:25]:
        inteiro = _parcial(nome_c, alvo) if nome_c else 0.0
        final = min(nota, inteiro)       # os pedaços e a ordem têm de bater, os dois
        if id_bate:                      # o número do paciente escrito na folha é quase prova
            final = min(1.0, max(final + 0.5, 0.9))
        if final >= minimo:
            saida.append({**e, "score": final, "ocr": True, "_n": len(nome_c)})
    # Nome curto contido no certo ("PEREIRA, LUCIANA" dentro de "MOREIRA, LUCIANA BEATRIZ
    # PEREIRA") bate tão bem quanto ele: entre os que batem bem, ganha quem explica mais texto.
    longos = [c["_n"] for c in saida if c["score"] >= 0.85]
    maior = max(longos) if longos else 0
    for c in saida:
        n = c.pop("_n")
        if maior:
            c["score"] *= 0.8 + 0.2 * min(1.0, n / maior)
        c["score"] = round(c["score"], 3)
    saida.sort(key=lambda c: -c["score"])
    return saida[:limite]


def escolher(achados: list[dict], nota: float = 0.9, folga: float = 0.1) -> dict | None:
    """O paciente que dá para aceitar sem perguntar: nota alta **e** folga clara sobre o segundo.

    É a mesma regra na janela "Identificar paciente" (onde só deixa escolhido) e na chegada da
    impressão (onde decide se o filme segue pela regra ou espera você confirmar).
    """
    if not achados:
        return None
    primeiro = achados[0]
    segundo = achados[1]["score"] if len(achados) > 1 else 0.0
    if primeiro.get("score", 0.0) >= nota and primeiro["score"] - segundo >= folga:
        return primeiro
    return None
