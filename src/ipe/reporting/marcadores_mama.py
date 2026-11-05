"""Achados da mamografia por marcadores CC e MLO (0.99.64, pesquisa de visualizadores PV 20 — OsiriX), sem Qt.

O radiologista marca o mesmo achado na CC e na MLO (botão direito ▸ Achado BI-RADS aqui). Cada marca guarda,
na hora, onde caiu em relação ao **mamilo** (o mesmo ponto da 0.99.61: a pele mais longe da parede torácica):

- **distância ao mamilo** em mm (pelo espaçamento do pixel);
- na **CC**, o deslocamento lateral (+) ou medial (−) da linha do mamilo; na **MLO**, o superior (+) ou inferior
  (−). O lado lateral da CC e o superior da MLO saem do PatientOrientation da imagem (a direção para baixo nas
  linhas); sem ele, vale a convenção (CC com o lateral em cima, MLO com o superior em cima);
- a **profundidade**: a fração da distância do mamilo até a parede torácica (terço anterior, médio, posterior).

Com as duas vistas do mesmo achado sai a localização: **quadrante** (ou união, região central/retroareolar) e
**hora do relógio**, olhando a paciente de frente (na mama direita o lateral fica às 9 h; na esquerda, às 3 h).
Com uma vista só, sai o que ela diz. A distância do mamilo é a média das duas vistas.
"""
from __future__ import annotations

import math

CENTRAL_MM = 10.0            # deslocamento abaixo disto = "na linha do mamilo"
RETROAREOLAR_MM = 20.0       # perto do mamilo e na linha dele = retroareolar
MEDIAL = {"R": "L", "L": "R"}           # letra do PatientOrientation que aponta para o lado medial
LADO_PT = {"R": "D", "L": "E"}


def posicao(vista: str, lado: str, ponto, mamilo, espac, parede_img: str, largura: int,
            orientacao=None) -> dict | None:
    """Onde o ponto (x, y em pixels) caiu em relação ao mamilo (x, y) nesta imagem.

    `vista`: "CC" ou "MLO" (ML, LM e XCC entram como CC/MLO pelo plano); `lado`: "R"/"L"; `espac` = (linha,
    coluna) mm; `parede_img`: "left"/"right" (onde está a parede torácica na imagem); `orientacao`: o
    PatientOrientation da imagem (dois valores)."""
    if ponto is None or mamilo is None:
        return None
    rs, cs = (float(v) for v in (espac or (0.1, 0.1)))
    dx = (float(ponto[0]) - float(mamilo[0])) * cs
    dy = (float(ponto[1]) - float(mamilo[1])) * rs
    dist = math.hypot(dx, dy)
    baixo = ""
    if orientacao and len(orientacao) >= 2:
        baixo = str(orientacao[1] or "").upper()
    v = (vista or "").upper()
    plano = "CC" if v.startswith(("CC", "XCC")) else "MLO"
    if plano == "CC":
        # para cima = lateral, a não ser que o arquivo diga que para baixo é lateral
        lat_baixo = bool(baixo) and MEDIAL.get(lado, "") not in baixo and any(c in baixo for c in "LR")
        desloc = dy if lat_baixo else -dy
    else:
        sup_baixo = "H" in baixo
        desloc = dy if sup_baixo else -dy
    # profundidade: do mamilo até a parede torácica, na horizontal
    x_parede = 0.0 if parede_img == "left" else float(largura)
    prof_total = abs(float(mamilo[0]) - x_parede) * cs
    prof = abs(float(ponto[0]) - float(mamilo[0])) * cs
    frac = min(1.0, prof / prof_total) if prof_total > 0 else None
    return {"plano": plano, "vista": v, "lado": lado, "dist_mm": round(dist, 1), "desloc_mm": round(desloc, 1),
            "prof_frac": None if frac is None else round(frac, 3)}


def terco(frac: float | None) -> str:
    if frac is None:
        return ""
    return "terço anterior" if frac < 1 / 3 else "terço médio" if frac < 2 / 3 else "terço posterior"


def hora(lat_mm: float, sup_mm: float, lado: str) -> int:
    """Hora do relógio olhando a paciente de frente."""
    x = lat_mm if lado == "L" else -lat_mm           # mama esquerda: lateral à direita de quem olha
    ang = math.degrees(math.atan2(x, sup_mm)) % 360.0
    h = int(round(ang / 30.0)) % 12
    return 12 if h == 0 else h


def quadrante(lat_mm: float | None, sup_mm: float | None, dist_mm: float | None) -> str:
    if dist_mm is not None and dist_mm < RETROAREOLAR_MM and (lat_mm is None or abs(lat_mm) < CENTRAL_MM) \
            and (sup_mm is None or abs(sup_mm) < CENTRAL_MM):
        return "região retroareolar"
    if lat_mm is None or sup_mm is None:
        if sup_mm is not None:
            return "" if abs(sup_mm) < CENTRAL_MM else ("metade superior" if sup_mm > 0 else "metade inferior")
        if lat_mm is not None:
            return "" if abs(lat_mm) < CENTRAL_MM else ("metade lateral" if lat_mm > 0 else "metade medial")
        return ""
    cl, cs_ = abs(lat_mm) < CENTRAL_MM, abs(sup_mm) < CENTRAL_MM
    if cl and cs_:
        return "região central"
    if cl:
        return "união dos quadrantes superiores" if sup_mm > 0 else "união dos quadrantes inferiores"
    if cs_:
        return "união dos quadrantes laterais" if lat_mm > 0 else "união dos quadrantes mediais"
    return "quadrante " + ("supero" if sup_mm > 0 else "infero") + ("lateral" if lat_mm > 0 else "medial")


def localizar(marcas: list[dict]) -> dict:
    """As marcas de um achado (uma por vista) → {lado, dist_mm, quadrante, hora, terco, vistas, texto}."""
    cc = next((m for m in marcas if m.get("plano") == "CC"), None)
    mlo = next((m for m in marcas if m.get("plano") == "MLO"), None)
    lado = (cc or mlo or {}).get("lado", "")
    dists = [m["dist_mm"] for m in (cc, mlo) if m is not None and m.get("dist_mm") is not None]
    dist = round(sum(dists) / len(dists), 1) if dists else None
    fracs = [m["prof_frac"] for m in (cc, mlo) if m is not None and m.get("prof_frac") is not None]
    frac = sum(fracs) / len(fracs) if fracs else None
    lat = cc["desloc_mm"] if cc is not None else None
    sup = mlo["desloc_mm"] if mlo is not None else None
    quad = quadrante(lat, sup, dist)
    h = hora(lat, sup, lado) if lat is not None and sup is not None and quad not in (
        "região retroareolar", "região central") else None
    partes = [quad] if quad else []
    if h is not None:
        partes.append(f"às {h} horas")
    t = terco(frac)
    if t and quad != "região retroareolar":
        partes.append(t)
    vistas = "+".join(m["vista"] for m in (cc, mlo) if m is not None)
    return {"lado": lado, "dist_mm": dist, "quadrante": quad, "hora": h, "terco": t, "vistas": vistas,
            "local": ", ".join(partes), "so_uma_vista": cc is None or mlo is None}


def achado_birads(numero: int, loc: dict, tipo: str = "Nódulo") -> dict:
    """O achado no formato do BI-RADS do laudo (reporting/birads.finding_text)."""
    dist = loc.get("dist_mm")
    return {"side": LADO_PT.get(loc.get("lado", ""), ""), "type": tipo, "desc": "", "size": "",
            "location": loc.get("local", ""),
            "distance": "" if dist is None else f"{dist / 10:.1f} cm".replace(".", ","),
            "change": "", "category": "", "marcador": numero}
