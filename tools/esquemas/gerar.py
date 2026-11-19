"""Gera os esquemas-guia do Ipê (0.100.72): desenhos **originais**, feitos aqui por código — nada copiado de
banco de imagens nem de figura de terceiros (o mapa de setores da próstata segue os *nomes* dos setores do
PI-RADS v2.1, com geometria própria e esquemática).

Uso: `python tools/esquemas/gerar.py` → grava `src/ipe/reporting/esquemas_modelos.json`.

Cada modelo: `id`, `nome`, `grupo`, `w`, `h` (unidades do desenho), `tracos` (polilinhas: `p` = pontos, `l` =
espessura, `c` = "forte" | "leve", `f` = fechada), `rotulos` (textos pequenos de orientação), `setores` (regiões
que se pintam com um clique: `id`, `nome`, `p`) e `categorias` (as cores dos setores).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

N = 14          # segmentos por curva


def caminho(d: str) -> list[list[float]]:
    """Um caminho no jeito do SVG (M, L, C, Q absolutos; um só traço) → pontos."""
    tok = re.findall(r"[MLCQZ]|-?\d+(?:\.\d+)?", d)
    pts: list[list[float]] = []
    i, cmd = 0, ""
    cur = (0.0, 0.0)

    def num(k):
        return [float(x) for x in tok[i:i + k]]
    while i < len(tok):
        if tok[i] in "MLCQZ":
            cmd = tok[i]
            i += 1
            if cmd == "Z":
                pts.append(list(pts[0]))
            continue
        if cmd in "ML":
            x, y = num(2)
            i += 2
            cur = (x, y)
            pts.append([x, y])
            cmd = "L"
        elif cmd == "C":
            x1, y1, x2, y2, x, y = num(6)
            i += 6
            for k in range(1, N + 1):
                t = k / N
                a, b, c, e = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                pts.append([a * cur[0] + b * x1 + c * x2 + e * x, a * cur[1] + b * y1 + c * y2 + e * y])
            cur = (x, y)
        elif cmd == "Q":
            x1, y1, x, y = num(4)
            i += 4
            for k in range(1, N + 1):
                t = k / N
                a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
                pts.append([a * cur[0] + b * x1 + c * x, a * cur[1] + b * y1 + c * y])
            cur = (x, y)
    return [[round(x, 1), round(y, 1)] for x, y in pts]


def espelho(p, cx):
    return [[round(2 * cx - x, 1), y] for x, y in p]


def elipse(cx, cy, rx, ry, a0=0.0, a1=360.0, n=48):
    out = []
    for k in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * k / n)
        out.append([round(cx + rx * math.cos(a), 1), round(cy - ry * math.sin(a), 1)])
    return out


class Modelo:
    def __init__(self, id_, nome, grupo, w, h):
        self.d = {"id": id_, "nome": nome, "grupo": grupo, "w": w, "h": h, "tracos": [], "rotulos": [], "setores": [],
                  "categorias": []}

    def t(self, p, l=3.0, c="forte", sim=None):
        """Um traço (caminho SVG ou pontos); `sim` = x do eixo para desenhar também o espelhado."""
        p = caminho(p) if isinstance(p, str) else p
        self.d["tracos"].append({"p": p, "l": l, "c": c})
        if sim is not None:
            self.d["tracos"].append({"p": espelho(p, sim), "l": l, "c": c})

    def r(self, x, y, texto, tam=22, c="leve"):
        self.d["rotulos"].append({"x": x, "y": y, "t": texto, "s": tam, "c": c})

    def s(self, id_, nome, p, curto=""):
        cx = sum(q[0] for q in p) / len(p)
        cy = sum(q[1] for q in p) / len(p)
        self.d["setores"].append({"id": id_, "nome": nome, "curto": curto, "p": p, "cx": round(cx, 1), "cy": round(cy, 1)})


# ---------------------------------------------------------------------- face
def face_frente():
    m = Modelo("face_frente", "Face — frente", "Pele", 800, 1000)
    c = 400
    m.t("M 400 70 C 530 70 628 170 632 330 C 634 420 622 500 598 575 C 568 668 500 762 400 778", 3.5, sim=c)  # contorno
    m.t("M 400 150 C 318 150 228 196 196 318", 1.6, "leve", sim=c)                                             # linha do cabelo
    m.t("M 630 372 C 668 350 688 404 676 462 C 668 506 640 528 612 506", 3, sim=c)                             # orelha
    m.t("M 646 392 C 662 404 662 452 644 484", 1.4, "leve", sim=c)
    m.t("M 502 726 L 508 860 C 524 902 606 934 712 968", 3, sim=c)                                             # pescoço e ombro
    m.t("M 452 402 Q 500 368 550 402 Q 500 428 452 402", 2.4, sim=c)                                           # olho
    m.t(elipse(501, 400, 15, 15), 1.8, sim=c)
    m.t("M 440 352 Q 500 316 566 348", 3, sim=c)                                                               # sobrancelha
    m.t("M 386 414 C 380 470 372 500 362 528 C 350 552 366 570 386 562", 2.2, sim=c)                           # nariz
    m.t("M 386 562 Q 400 574 414 562", 2.2)
    m.t("M 336 644 Q 372 624 400 636 Q 428 624 464 644", 2.4)                                                  # lábios
    m.t("M 336 644 Q 400 662 464 644", 1.8)
    m.t("M 354 656 Q 400 694 446 656", 2.4)
    m.t("M 372 716 Q 400 728 428 716", 1.4, "leve")                                                            # mento
    m.r(70, 60, "D", 34)
    m.r(730, 60, "E", 34)
    return m


def face_perfil(lado):
    """`lado` = "direito": o lado direito do paciente à vista (o nariz aponta para a direita da figura)."""
    m = Modelo(f"face_perfil_{lado}", f"Face — perfil {lado}", "Pele", 800, 1000)
    tr = []
    tr.append(("M 384 76 C 232 74 118 196 124 372 C 128 476 186 566 252 612 L 262 792 C 250 850 190 900 110 940", 3.5, "forte"))
    tr.append(("M 384 76 C 506 78 596 150 606 268 C 608 306 598 330 606 356 L 668 468 C 676 490 654 502 628 504 "
               "C 620 520 638 534 642 550 C 644 562 628 568 624 574 C 642 582 642 602 630 610 C 616 624 622 640 "
               "628 656 C 634 702 594 734 544 738 C 486 740 446 724 424 704 L 434 862 C 470 906 540 934 640 960", 3.5, "forte"))
    tr.append(("M 548 730 C 486 708 430 652 408 572", 1.6, "leve"))                                            # mandíbula
    tr.append(("M 352 424 C 404 398 428 462 400 524 C 384 556 356 546 352 512 C 350 484 362 470 352 424", 3, "forte"))  # orelha
    tr.append(("M 368 446 C 392 448 398 486 382 512", 1.4, "leve"))
    tr.append(("M 540 382 Q 566 364 590 382 Q 564 394 540 382", 2.4, "forte"))                                 # olho
    tr.append(("M 522 346 Q 566 322 602 344", 3, "forte"))                                                     # sobrancelha
    tr.append(("M 384 150 C 300 150 222 210 206 330 C 250 360 300 372 344 410", 1.6, "leve"))                  # cabelo
    tr.append(("M 624 574 L 596 580", 1.8, "forte"))                                                           # boca
    tr.append(("M 628 504 C 618 498 612 488 616 478", 1.8, "forte"))                                           # asa do nariz
    for d, l, c in tr:
        p = caminho(d)
        m.t(p if lado == "direito" else espelho(p, 400), l, c)
    return m


# ---------------------------------------------------------------------- corpo
def corpo(vista):
    m = Modelo(f"corpo_{vista}", f"Corpo — {vista}", "Pele", 640, 1240)
    c = 320
    m.t("M 320 36 C 368 36 396 74 396 122 C 396 164 374 198 350 210 L 352 240 C 380 256 432 260 462 276 "
        "C 494 292 504 332 506 372 L 520 532 L 546 672 C 562 714 562 756 546 778 C 530 794 514 782 516 756 "
        "L 504 684 L 478 544 L 458 404 L 452 492 C 446 552 452 592 468 652 C 480 714 474 814 464 894 "
        "C 462 936 464 976 456 1056 L 448 1140 C 466 1168 476 1186 452 1192 L 400 1192 C 390 1186 398 1160 "
        "404 1140 C 398 1056 394 976 386 904 C 376 814 352 714 322 664 L 320 664", 3.5, sim=c)
    if vista == "frente":
        m.t("M 344 262 C 380 272 420 274 458 280", 1.6, "leve", sim=c)                                          # clavícula
        m.t(elipse(392, 356, 7, 7), 1.6, "leve", sim=c)                                                        # mamilo
        m.t("M 352 400 Q 396 424 440 396", 1.4, "leve", sim=c)                                                 # sulco peitoral
        m.t(elipse(320, 540, 6, 8), 1.6, "leve")                                                               # umbigo
        m.t("M 452 620 Q 380 660 322 690", 1.4, "leve", sim=c)                                                 # prega inguinal
        m.t(elipse(416, 902, 22, 26), 1.3, "leve", sim=c)                                                      # joelho
        m.t("M 300 100 Q 320 108 340 100", 1.4, "leve")                                                        # face (só um traço)
        m.r(60, 60, "D", 34)
        m.r(580, 60, "E", 34)
    else:
        m.t("M 320 214 L 320 620", 1.6, "leve")                                                                # coluna
        m.t("M 356 300 C 404 300 430 336 426 400 C 400 414 372 396 356 372", 1.4, "leve", sim=c)               # escápula
        m.t("M 320 664 C 360 690 420 690 458 660", 1.6, "leve", sim=c)                                         # prega glútea
        m.t("M 320 600 L 320 664", 1.6, "leve")
        m.t("M 396 902 Q 420 916 446 902", 1.3, "leve", sim=c)                                                 # poplítea
        m.t("M 300 204 Q 320 214 340 204", 1.4, "leve")
        m.r(60, 60, "E", 34)
        m.r(580, 60, "D", 34)
    return m


# ---------------------------------------------------------------------- tireoide
def tireoide():
    m = Modelo("tireoide", "Tireoide e níveis cervicais", "Pescoço", 900, 720)
    c = 450
    m.t("M 120 96 C 250 190 360 214 450 214", 3, sim=c)                                                        # mandíbula
    m.t("M 96 150 C 190 330 300 520 404 652", 1.8, "leve", sim=c)                                              # ECM (borda anterior)
    m.t("M 60 196 C 130 380 210 540 300 640", 1.8, "leve", sim=c)                                              # ECM (borda posterior)
    m.t("M 20 640 C 150 600 310 612 420 664", 3, sim=c)                                                        # clavícula
    m.t("M 20 420 C 40 500 40 580 20 640", 1.6, "leve", sim=c)                                                 # trapézio
    m.t("M 396 250 L 450 276 L 450 330 L 392 330 Z", 2.2, sim=c)                                               # cartilagem tireoide
    m.t("M 404 346 L 450 346", 1.6, "leve", sim=c)                                                             # cricoide
    # lobos e istmo
    m.t("M 398 372 C 352 330 306 372 310 452 C 314 520 356 566 402 536 C 412 520 414 506 414 492 L 450 492", 3.5, sim=c)
    m.t("M 398 372 C 408 392 412 414 414 432 L 450 432", 3.5, sim=c)
    # traqueia abaixo do istmo
    m.t("M 416 498 L 416 668", 2.2, sim=c)
    for y in (540, 580, 620):
        m.t(f"M 416 {y} Q 450 {y + 16} 484 {y}", 1.3, "leve")
    m.r(60, 50, "D", 34)
    m.r(840, 50, "E", 34)
    m.r(356, 458, "LD", 22)
    m.r(544, 458, "LE", 22)
    m.r(450, 468, "istmo", 16)
    for x, y, t in ((450, 170, "IA"), (300, 196, "IB"), (600, 196, "IB"), (196, 290, "II"), (704, 290, "II"),
                    (262, 420, "III"), (638, 420, "III"), (320, 560, "IV"), (580, 560, "IV"),
                    (110, 470, "V"), (790, 470, "V"), (450, 600, "VI")):
        m.r(x, y, t, 22)
    return m


# ---------------------------------------------------------------------- mamas
def mamas():
    m = Modelo("mamas", "Mamas", "Mama", 1000, 640)
    for cx, lado, ax in ((270, "D", -1), (730, "E", 1)):
        cy, r = 340, 196
        m.t(elipse(cx, cy, r, r, n=72), 3.5)
        m.t(elipse(cx, cy, 46, 46), 1.8, "leve")
        m.t(elipse(cx, cy, 13, 13), 2.2)
        m.t([[cx - r, cy], [cx - 46, cy]], 1.4, "leve")
        m.t([[cx + 46, cy], [cx + r, cy]], 1.4, "leve")
        m.t([[cx, cy - r], [cx, cy - 46]], 1.4, "leve")
        m.t([[cx, cy + 46], [cx, cy + r]], 1.4, "leve")
        for hora in range(12):                                                                                # relógio
            a = math.radians(90 - 30 * hora)
            m.t([[round(cx + (r - 12) * math.cos(a), 1), round(cy - (r - 12) * math.sin(a), 1)],
                 [round(cx + r * math.cos(a), 1), round(cy - r * math.sin(a), 1)]], 1.6, "leve")
            if hora % 3 == 0:
                m.r(round(cx + (r - 32) * math.cos(a)), round(cy - (r - 32) * math.sin(a)), str(hora or 12), 18)
        # prolongamento axilar (para cima e para fora)
        a1, a2 = (math.radians(118), math.radians(152)) if ax < 0 else (math.radians(62), math.radians(28))
        p1 = (cx + r * math.cos(a1), cy - r * math.sin(a1))
        p2 = (cx + r * math.cos(a2), cy - r * math.sin(a2))
        m.t(f"M {p1[0]:.0f} {p1[1]:.0f} C {cx + ax * 118:.0f} {cy - 232:.0f} {cx + ax * 176:.0f} {cy - 286:.0f} "
            f"{cx + ax * 218:.0f} {cy - 268:.0f} C {cx + ax * 252:.0f} {cy - 252:.0f} {cx + ax * 236:.0f} {cy - 176:.0f} "
            f"{p2[0]:.0f} {p2[1]:.0f}", 2.6)
        m.r(cx, 600, "Direita" if lado == "D" else "Esquerda", 24)
        fora, dentro = (-1, 1) if ax < 0 else (1, -1)
        for dx, dy, t in ((fora, -1, "QSL"), (dentro, -1, "QSM"), (fora, 1, "QIL"), (dentro, 1, "QIM")):
            m.r(cx + dx * 98, cy + dy * 104, t, 17)
    return m


# ---------------------------------------------------------------------- próstata (mapa de setores)
LADO = {"D": "direita", "E": "esquerda"}
ZONA = {"AS": "estroma fibromuscular anterior", "TZa": "zona de transição anterior", "TZp": "zona de transição posterior",
        "CZ": "zona central", "PZa": "zona periférica anterior", "PZpl": "zona periférica posterolateral",
        "PZpm": "zona periférica posteromedial"}
NIVEL = {"base": "base", "medio": "terço médio", "apice": "ápice"}


def prostata():
    m = Modelo("prostata", "Próstata — mapa de setores", "Próstata", 1000, 1350)
    m.d["categorias"] = [{"k": "1", "nome": "PI-RADS 1", "cor": "#b0bec5"}, {"k": "2", "nome": "PI-RADS 2", "cor": "#9ccc65"},
                         {"k": "3", "nome": "PI-RADS 3", "cor": "#ffd54f"}, {"k": "4", "nome": "PI-RADS 4", "cor": "#ff9800"},
                         {"k": "5", "nome": "PI-RADS 5", "cor": "#e53935"}]
    FI = 0.54                                            # até onde vai a zona de transição
    FC = 0.77                                            # zona central, na base (entre a transição e a periférica)

    def pt(cx, cy, rx, ry, ang, f):
        a = math.radians(ang)
        return [round(cx + f * rx * math.cos(a), 1), round(cy - f * ry * math.sin(a), 1)]

    def anel(cx, cy, rx, ry, a0, a1, f0, f1, n=14):
        fora = [pt(cx, cy, rx, ry, a0 + (a1 - a0) * k / n, f1) for k in range(n + 1)]
        dentro = [pt(cx, cy, rx, ry, a1 - (a1 - a0) * k / n, f0) for k in range(n + 1)]
        return fora + dentro

    def cunha(cx, cy, rx, ry, a0, a1, n=14):
        return [[cx, cy]] + [pt(cx, cy, rx, ry, a0 + (a1 - a0) * k / n, FI) for k in range(n + 1)]

    for nivel, cy, rx, ry in (("base", 376, 300, 190), ("medio", 766, 280, 180), ("apice", 1110, 220, 140)):
        cx = 500
        # direita do paciente = esquerda da figura (ângulos de 90° a 270°)
        partes = [("AS", "D", anel(cx, cy, rx, ry, 90, 122, FI, 1)), ("AS", "E", anel(cx, cy, rx, ry, 58, 90, FI, 1)),
                  ("PZa", "D", anel(cx, cy, rx, ry, 122, 182, FI, 1)), ("PZa", "E", anel(cx, cy, rx, ry, -2, 58, FI, 1)),
                  ("PZpl", "D", anel(cx, cy, rx, ry, 182, 232, FI, 1)), ("PZpl", "E", anel(cx, cy, rx, ry, -52, -2, FI, 1)),
                  ("TZa", "D", cunha(cx, cy, rx, ry, 90, 180)), ("TZa", "E", cunha(cx, cy, rx, ry, 0, 90)),
                  ("TZp", "D", cunha(cx, cy, rx, ry, 180, 270)), ("TZp", "E", cunha(cx, cy, rx, ry, -90, 0))]
        if nivel == "base":
            partes += [("CZ", "D", anel(cx, cy, rx, ry, 232, 270, FI, FC)), ("CZ", "E", anel(cx, cy, rx, ry, -90, -52, FI, FC)),
                       ("PZpm", "D", anel(cx, cy, rx, ry, 232, 270, FC, 1)), ("PZpm", "E", anel(cx, cy, rx, ry, -90, -52, FC, 1))]
        else:
            partes += [("PZpm", "D", anel(cx, cy, rx, ry, 232, 270, FI, 1)), ("PZpm", "E", anel(cx, cy, rx, ry, -90, -52, FI, 1))]
        for zona, lado, p in partes:
            m.s(f"{nivel}_{zona}_{lado}", f"{ZONA[zona]} {LADO[lado]}, {NIVEL[nivel]}", p, zona)
            m.t(p + [p[0]], 1.6, "leve")
        m.t(elipse(cx, cy, rx, ry, n=72), 3.5)
        m.t(elipse(cx, cy, rx * FI, ry * FI, n=60), 2.4)
        m.t(elipse(cx, cy + ry * 0.06, 9, 9), 1.6, "leve")                                                     # uretra
        m.r(92, cy, {"base": "Base", "medio": "Terço médio", "apice": "Ápice"}[nivel], 24)
    # vesículas seminais e esfíncter
    for lado, cx in (("D", 372), ("E", 628)):
        p = elipse(cx, 92, 112, 44, n=40)
        m.s(f"VS_{lado}", f"vesícula seminal {LADO[lado]}", p[:-1], "VS")
        m.t(p, 3)
    p = elipse(500, 1300, 46, 30, n=32)
    m.s("esfincter", "esfíncter uretral", p[:-1], "EU")
    m.t(p, 3)
    m.r(60, 40, "D", 34)
    m.r(940, 40, "E", 34)
    m.r(500, 160, "anterior", 17)
    m.r(92, 92, "Vesículas", 20)
    return m


def todos():
    return [x.d for x in (face_frente(), face_perfil("direito"), face_perfil("esquerdo"), corpo("frente"), corpo("costas"),
                          tireoide(), mamas(), prostata())]


if __name__ == "__main__":
    destino = Path(__file__).resolve().parents[2] / "src" / "ipe" / "reporting" / "esquemas_modelos.json"
    destino.write_text(json.dumps(todos(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("gravado:", destino, destino.stat().st_size, "bytes")
