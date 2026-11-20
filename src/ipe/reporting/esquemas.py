"""0.100.72: esquemas-guia do laudo — um desenho de base (face, corpo, tireoide, mamas, próstata…) em que o médico
marca os achados; vai para o laudo (PDF), para o exame (imagem DICOM) e para o SR.

Pedido dele (19/11/2026): *"em especial para laudos de USG dermatológico, tireoide, mama e RM de próstata, quero
poder desenhar em imagens guias […] essa imagem depois ficará salva com SR e também no laudo. Quero no desktop e
web."* E: as marcas podem estar ligadas ao texto do laudo e a imagens-chave (o médico decide); na próstata, clicar
no setor pinta com a categoria.

Aqui não há Qt nem rede: os modelos, o formato, a conferência do que chega, a legenda e o desenho (Pillow), que é
o mesmo para o PDF, a imagem DICOM e a pré-visualização do navegador. As telas (Qt e canvas) desenham por conta
própria, a partir dos mesmos dados.

**Formato** (guardado por exame em `revisao_ia`, módulo "esquemas", como uma lista):

    {"id": "…", "modelo": "face_frente", "titulo": "", "setores": {"medio_PZpl_D": "4"},
     "marcas": [{"tipo": "ponto" | "elipse" | "traco" | "seta" | "texto", "n": 1, "p": [[x, y], …], "cor": "#d32f2f",
                 "l": 3, "texto": "nódulo hipoecoico de 4 mm",
                 "imagem": {"series_uid": "…", "sop_uid": "…", "frame": 0, "rotulo": "série 3, imagem 12"}}]}

Os pontos vão de 0 a 1 (fração da largura e da altura do modelo): servem em qualquer tamanho.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import uuid
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

MODULO = "esquemas"
CHAVE_MEUS = "esquemas_modelos"                    # modelos próprios da instalação (imagens), em app_setting
TIPOS = ("ponto", "elipse", "traco", "seta", "texto")
CORES = ["#d32f2f", "#1565c0", "#2e7d32", "#ef6c00", "#6a1b9a", "#111111"]
MAX_ESQUEMAS, MAX_MARCAS, MAX_PONTOS, MAX_TEXTO = 12, 200, 600, 300
MAX_LADO_MEU, MAX_MEUS = 1400, 24
_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
TINTA = {"forte": (40, 40, 40), "leve": (150, 150, 150)}


# ---------------------------------------------------------------------- modelos
@lru_cache(maxsize=1)
def _de_fabrica() -> tuple:
    from ipe.core.runtime import resource_dir
    p = resource_dir() / "reporting" / "esquemas_modelos.json"          # no pacote instalado, vem como arquivo
    if not p.exists():
        p = Path(__file__).with_name("esquemas_modelos.json")
    return tuple(json.loads(p.read_text(encoding="utf-8")))


def _guardados(repo) -> list[dict]:
    """O que esta instalação cadastrou: modelos próprios e alterações nos modelos do Ipê."""
    try:
        v = repo.get_app_setting(CHAVE_MEUS, []) if repo is not None else []
    except Exception:  # noqa: BLE001
        log.debug("esquemas: modelos próprios", exc_info=True)
        v = []
    return [m for m in (v or []) if isinstance(m, dict) and m.get("id")]


def _ids_de_fabrica() -> set[str]:
    return {m["id"] for m in _de_fabrica()}


def meus(repo) -> list[dict]:
    """Os modelos próprios, prontos para desenhar: de uma imagem (`png`), cópia de um modelo do Ipê (`origem`, de
    onde vêm os traços e os setores) ou em branco. `base` = o que foi desenhado no modelo."""
    fabrica = {m["id"]: m for m in _de_fabrica()}
    out = []
    for g in _guardados(repo):
        if g["id"] in fabrica:
            continue
        o = fabrica.get(g.get("origem") or "") or {}
        out.append({"id": g["id"], "nome": g.get("nome") or "Modelo", "grupo": g.get("grupo") or "Meus",
                    "w": o.get("w") or g.get("w") or 1000, "h": o.get("h") or g.get("h") or 1000, "meu": True,
                    "origem": g.get("origem") or "", "tracos": o.get("tracos") or [], "rotulos": o.get("rotulos") or [],
                    "setores": o.get("setores") or [], "categorias": o.get("categorias") or [],
                    "base": g.get("base") or [], **({"png": g["png"]} if g.get("png") else {})})
    return out


def modelos(repo=None, ocultos: bool = False) -> list[dict]:
    """Todos os modelos: os do Ipê (com o que a instalação mudou neles: nome, grupo, `base` desenhada, `oculto`) e
    os próprios (`meu` = True). Os ocultos só entram com `ocultos=True` (para gerenciar e para desenhar um esquema
    antigo feito com eles)."""
    mudados = {g["id"]: g for g in _guardados(repo) if g["id"] in _ids_de_fabrica()}
    out = []
    for m in _de_fabrica():
        g = mudados.get(m["id"])
        if g is None:
            out.append(m)
            continue
        if g.get("oculto") and not ocultos:
            continue
        out.append({**m, "nome": g.get("nome") or m["nome"], "grupo": g.get("grupo") or m["grupo"],
                    "base": g.get("base") or [], "alterado": True, "oculto": bool(g.get("oculto"))})
    return out + meus(repo)


def modelo(id_: str, repo=None) -> dict | None:
    return next((m for m in modelos(repo, ocultos=True) if m["id"] == id_), None)


def resumo_dos_modelos(repo=None) -> list[dict]:
    """Para as telas escolherem: sem os traços nem a imagem."""
    return [{"id": m["id"], "nome": m["nome"], "grupo": m.get("grupo", ""), "w": m["w"], "h": m["h"],
             "meu": bool(m.get("meu")), "setores": len(m.get("setores") or [])} for m in modelos(repo)]


def _png_do_modelo(dados: bytes) -> tuple[str, int, int]:
    """A imagem enviada → PNG de até 1400 px, fundo branco (base64), com a largura e a altura."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(dados))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError("Não consegui ler a imagem (use PNG ou JPG).") from e
    if im.mode in ("RGBA", "LA", "P"):                  # fundo branco no que é transparente
        im = im.convert("RGBA")
        fundo = Image.new("RGB", im.size, (255, 255, 255))
        fundo.paste(im, mask=im.split()[-1])
        im = fundo
    im = im.convert("RGB")
    if min(im.size) < 100:
        raise ValueError("A imagem é pequena demais (menos de 100 pixels).")
    im.thumbnail((MAX_LADO_MEU, MAX_LADO_MEU))
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return base64.b64encode(b.getvalue()).decode("ascii"), im.size[0], im.size[1]


def _base_conferida(marcas) -> list[dict]:
    """O desenho de um modelo: as mesmas marcas de um esquema, sem número nem imagem ligada."""
    out = []
    for m in (marcas or [])[:MAX_MARCAS]:
        x = normalizar_marca(m)
        if x:
            x["n"] = 0
            x.pop("imagem", None)
            out.append(x)
    return out


def salvar_modelo(repo, d: dict, imagem: bytes | None = None) -> dict:
    """Cadastra ou muda um modelo (0.100.73). `d`: `id` (vazio = novo), `nome`, `grupo`, `base` (o desenho do
    modelo), `oculto` e, num novo, `origem` (cópia de um modelo do Ipê). `imagem` = o fundo (novo, ou trocar).
    - `id` de um modelo do Ipê: guarda só a mudança (nome, grupo, desenho por cima, oculto); o original fica.
    - novo sem imagem e sem origem: modelo em branco (quadrado)."""
    nome = str(d.get("nome") or "").strip()[:60]
    grupo = str(d.get("grupo") or "").strip()[:30]
    if not nome:
        raise ValueError("Dê um nome ao modelo.")
    lista = _guardados(repo)
    fabrica = _ids_de_fabrica()
    mid = str(d.get("id") or "")
    base = _base_conferida(d.get("base"))
    if mid in fabrica:
        if imagem:
            raise ValueError("Num modelo do Ipê não se troca o fundo: faça uma cópia.")
        g = {"id": mid, "nome": nome, "grupo": grupo, "base": base, "oculto": bool(d.get("oculto"))}
        lista = [x for x in lista if x["id"] != mid] + [g]
    elif mid:
        g = next((x for x in lista if x["id"] == mid), None)
        if g is None:
            raise LookupError("modelo desconhecido")
        g.update(nome=nome, grupo=grupo or "Meus", base=base)
        if imagem:
            g["png"], g["w"], g["h"] = _png_do_modelo(imagem)
            g.pop("origem", None)
    else:
        if sum(1 for x in lista if x["id"] not in fabrica) >= MAX_MEUS:
            raise ValueError(f"Já há {MAX_MEUS} modelos próprios: exclua um antes.")
        g = {"id": "meu_" + uuid.uuid4().hex[:10], "nome": nome, "grupo": grupo or "Meus", "base": base}
        origem = str(d.get("origem") or "")
        o = modelo(origem, repo) if origem else None
        if imagem:
            g["png"], g["w"], g["h"] = _png_do_modelo(imagem)
        elif o is not None and o.get("png"):                 # cópia de um modelo próprio de imagem
            g["png"], g["w"], g["h"] = o["png"], o["w"], o["h"]
        elif o is not None:                                  # cópia de um do Ipê (ou de uma cópia dele)
            g["origem"] = o.get("origem") or (o["id"] if o["id"] in fabrica else "")
            g["w"], g["h"] = o["w"], o["h"]
        else:
            g["w"], g["h"] = 1000, 1000
        if o is not None and "base" not in d:
            g["base"] = _base_conferida(o.get("base"))
        lista.append(g)
    repo.set_app_setting(CHAVE_MEUS, lista)
    return modelo(g["id"], repo) or g


def novo_modelo_de_imagem(repo, nome: str, dados: bytes, grupo: str = "Meus") -> dict:
    """Cadastra um modelo próprio a partir de uma imagem (PNG, JPG…): reduzida a 1400 px e guardada como PNG."""
    if not (nome or "").strip():
        raise ValueError("Dê um nome ao modelo.")
    return salvar_modelo(repo, {"nome": nome, "grupo": grupo}, dados)


def excluir_modelo(repo, id_: str) -> str:
    """Exclui um modelo próprio ("excluido") ou desfaz as mudanças num modelo do Ipê ("restaurado"); "" se não há."""
    lista = _guardados(repo)
    resto = [m for m in lista if m["id"] != id_]
    if len(resto) == len(lista):
        return ""
    repo.set_app_setting(CHAVE_MEUS, resto)
    return "restaurado" if id_ in _ids_de_fabrica() else "excluido"


# ---------------------------------------------------------------------- guardar e ler
def _num(v, lo=0.0, hi=1.0) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return lo
    if v != v:                                           # NaN
        return lo
    return round(max(lo, min(hi, v)), 5)


def normalizar_marca(m: dict) -> dict | None:
    """Confere uma marca que veio de uma tela (ou do navegador): tipo conhecido, pontos de 0 a 1, tamanhos com teto."""
    if not isinstance(m, dict) or m.get("tipo") not in TIPOS:
        return None
    tipo = m["tipo"]
    pts = [[_num(p[0]), _num(p[1])] for p in (m.get("p") or [])[:MAX_PONTOS]
           if isinstance(p, (list, tuple)) and len(p) >= 2]
    precisa = {"ponto": 1, "texto": 1, "elipse": 2, "seta": 2, "traco": 2}[tipo]
    if len(pts) < precisa:
        return None
    if tipo != "traco":
        pts = pts[:precisa]
    cor = m.get("cor") if isinstance(m.get("cor"), str) and _COR.match(m["cor"]) else CORES[0]
    out = {"tipo": tipo, "p": pts, "cor": cor.lower(), "l": _num(m.get("l", 3), 1, 12),
           "n": int(_num(m.get("n", 0), 0, 999)), "texto": str(m.get("texto") or "").strip()[:MAX_TEXTO]}
    if tipo == "texto" and not out["texto"]:
        return None
    im = m.get("imagem")
    if isinstance(im, dict) and im.get("sop_uid"):
        out["imagem"] = {"series_uid": str(im.get("series_uid") or "")[:64], "sop_uid": str(im["sop_uid"])[:64],
                         "frame": int(_num(im.get("frame", 0), 0, 100000)), "rotulo": str(im.get("rotulo") or "")[:80]}
    return out


def normalizar(e: dict, repo=None) -> dict | None:
    """Um esquema conferido; None se o modelo não existe."""
    if not isinstance(e, dict):
        return None
    mod = modelo(str(e.get("modelo") or ""), repo)
    if mod is None:
        return None
    marcas = [x for x in (normalizar_marca(m) for m in (e.get("marcas") or [])[:MAX_MARCAS]) if x]
    cats = {c["k"] for c in mod.get("categorias") or []}
    ids = {s["id"] for s in mod.get("setores") or []}
    setores = {k: str(v) for k, v in (e.get("setores") or {}).items() if k in ids and str(v) in cats} \
        if isinstance(e.get("setores"), dict) else {}
    eid = str(e.get("id") or "")
    return {"id": eid if re.match(r"^[0-9a-f]{8,32}$", eid) else uuid.uuid4().hex[:12], "modelo": mod["id"],
            "titulo": str(e.get("titulo") or "").strip()[:80], "marcas": marcas, "setores": setores}


def ler(repo, study_uid: str) -> list[dict]:
    """Os esquemas do exame (lista vazia se não há)."""
    try:
        r = repo.revisao_ia(study_uid, MODULO)
        dados = json.loads(r["dados"]) if r and r.get("dados") else []
    except Exception:  # noqa: BLE001
        log.debug("esquemas: ler", exc_info=True)
        return []
    return [e for e in dados if isinstance(e, dict)] if isinstance(dados, list) else []


NO_LAUDO = "laudo"                                     # o `estado` que diz: os esquemas entram no laudo


def no_laudo(repo, study_uid: str) -> bool:
    """0.100.74: os esquemas deste exame entram no laudo (PDF e SR)? Quem decide é o médico, no laudo, como nas
    imagens-chave; o esquema em si é do exame e vive fora do laudo."""
    try:
        r = repo.revisao_ia(study_uid, MODULO)
    except Exception:  # noqa: BLE001
        return False
    return bool(r and r.get("estado") == NO_LAUDO)


def por_no_laudo(repo, study_uid: str, sim: bool, usuario: str = "") -> bool:
    """Liga ou desliga "os esquemas entram no laudo", sem mexer nos desenhos."""
    repo.salvar_revisao_ia(study_uid, MODULO, NO_LAUDO if sim else "editado", True, usuario or "",
                           json.dumps(ler(repo, study_uid), ensure_ascii=False))
    return bool(sim)


def gravar(repo, study_uid: str, lista: list, usuario: str = "") -> list[dict]:
    """Guarda os esquemas do exame (conferidos). Devolve o que ficou. O "entram no laudo" fica como estava."""
    limpa = [x for x in (normalizar(e, repo) for e in (lista or [])[:MAX_ESQUEMAS]) if x]
    estado = NO_LAUDO if no_laudo(repo, study_uid) else "editado"
    repo.salvar_revisao_ia(study_uid, MODULO, estado, True, usuario or "", json.dumps(limpa, ensure_ascii=False))
    return limpa


def vazio(e: dict) -> bool:
    return not (e.get("marcas") or e.get("setores"))


def proximo_numero(e: dict) -> int:
    return max([int(m.get("n") or 0) for m in e.get("marcas") or []] + [0]) + 1


# ---------------------------------------------------------------------- legenda (o elo com o texto do laudo)
def titulo(e: dict, repo=None) -> str:
    mod = modelo(e.get("modelo", ""), repo)
    return e.get("titulo") or (mod["nome"] if mod else "Esquema")


def legenda(e: dict, repo=None) -> list[str]:
    """Uma linha por marca numerada ou com texto, e uma por categoria dos setores pintados."""
    mod = modelo(e.get("modelo", ""), repo) or {}
    out = []
    for m in sorted(e.get("marcas") or [], key=lambda m: (int(m.get("n") or 0) == 0, int(m.get("n") or 0))):
        n, texto = int(m.get("n") or 0), (m.get("texto") or "").strip()
        if not n and (not texto or m.get("tipo") == "texto"):
            continue                                     # marca sem número: só desenho (o texto solto já está na figura)
        linha = (f"{n}. " if n else "– ") + (texto or "(sem descrição)")
        rot = ((m.get("imagem") or {}).get("rotulo") or "").strip()
        if rot:
            linha += f" ({rot})"
        out.append(linha)
    pintados = e.get("setores") or {}
    nomes = {s["id"]: s["nome"] for s in mod.get("setores") or []}
    for c in reversed(mod.get("categorias") or []):      # a categoria mais alta primeiro
        quais = [nomes[k] for k, v in pintados.items() if v == c["k"] and k in nomes]
        if quais:
            out.append(f"{c['nome']}: {'; '.join(quais)}.")
    return out


def texto_para_o_laudo(lista: list, repo=None) -> str:
    """O bloco que entra no texto do laudo (campo {esquemas} dos modelos e botão "Inserir a legenda")."""
    blocos = []
    for e in lista or []:
        linhas = legenda(e, repo)
        if linhas:
            blocos.append(f"{titulo(e, repo)}:\n" + "\n".join(linhas))
    return "\n\n".join(blocos)


# ---------------------------------------------------------------------- desenho (Pillow)
def _rgb(cor: str) -> tuple[int, int, int]:
    return tuple(int(cor[i:i + 2], 16) for i in (1, 3, 5)) if _COR.match(cor or "") else (211, 47, 47)


#: fontes com acento, na ordem em que são tentadas (Linux, Windows, macOS); a do Pillow não tem "ã" nem "ç"
_FONTES = ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf", "segoeui.ttf", "Helvetica.ttc",
           "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc")


@lru_cache(maxsize=1)
def _arquivo_da_fonte() -> str:
    from PIL import ImageFont
    candidatas = list(_FONTES)
    for nome in candidatas:
        try:
            ImageFont.truetype(nome, 12)
            return nome
        except OSError:
            continue
    return ""


@lru_cache(maxsize=64)
def _fonte(tam: int):
    from PIL import ImageFont
    tam = max(8, int(tam))
    arq = _arquivo_da_fonte()
    if arq:
        return ImageFont.truetype(arq, tam)
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:                                    # Pillow antigo: só a fonte pequena
        return ImageFont.load_default()


def _centrado(d, xy, texto: str, fonte, cor) -> None:
    try:
        d.text(xy, texto, font=fonte, fill=cor, anchor="mm")
    except (ValueError, TypeError):
        d.text((xy[0] - 4 * len(texto), xy[1] - 6), texto, font=fonte, fill=cor)


def desenhar(e: dict, largura: int = 1100, repo=None, com_titulo: bool = False):
    """A figura do esquema com as marcas (PIL.Image RGB, fundo branco). É a que vai para o PDF e para o DICOM."""
    from PIL import Image, ImageDraw
    mod = modelo(e.get("modelo", ""), repo)
    if mod is None:
        raise LookupError("modelo de esquema desconhecido")
    k = 2                                                # desenha no dobro e reduz: traço liso sem depender de mais nada
    W = int(largura) * k
    esc = W / mod["w"]
    H = int(round(mod["h"] * esc))
    im = Image.new("RGB", (W, H), (255, 255, 255))
    if mod.get("png"):
        try:
            fundo = Image.open(io.BytesIO(base64.b64decode(mod["png"]))).convert("RGB").resize((W, H))
            im.paste(fundo)
        except Exception:  # noqa: BLE001
            log.warning("esquema: imagem do modelo %s ilegível", mod["id"])
    d = ImageDraw.Draw(im, "RGBA")
    # setores pintados (por baixo dos traços)
    cores = {c["k"]: c["cor"] for c in mod.get("categorias") or []}
    pintados = e.get("setores") or {}
    for s in mod.get("setores") or []:
        cat = pintados.get(s["id"])
        if cat in cores:
            d.polygon([(x * esc, y * esc) for x, y in s["p"]], fill=_rgb(cores[cat]) + (205,))
    for t in mod.get("tracos") or []:
        d.line([(x * esc, y * esc) for x, y in t["p"]], fill=TINTA.get(t.get("c"), TINTA["forte"]),
               width=max(1, int(round(t.get("l", 3) * esc))), joint="curve")
    for s in mod.get("setores") or []:
        cat = pintados.get(s["id"])
        if s.get("curto"):
            f = _fonte(int(15 * esc))
            _centrado(d, (s["cx"] * esc, s["cy"] * esc - (9 * esc if cat else 0)), s["curto"], f, (90, 90, 90))
        if cat in cores:
            _centrado(d, (s["cx"] * esc, s["cy"] * esc + 10 * esc), cat, _fonte(int(24 * esc)), (0, 0, 0))
    for r in mod.get("rotulos") or []:
        _centrado(d, (r["x"] * esc, r["y"] * esc), r["t"], _fonte(int(r.get("s", 20) * esc)), TINTA.get(r.get("c"), TINTA["leve"]))
    base = W / 1000.0                                    # as marcas têm o mesmo tamanho em qualquer modelo
    for m in (mod.get("base") or []) + (e.get("marcas") or []):   # o desenho do modelo e, por cima, o do exame
        _marca(d, m, W, H, base)
    if com_titulo:
        _centrado(d, (W / 2, 18 * base), titulo(e, repo), _fonte(int(22 * base)), (60, 60, 60))
    return im.resize((W // k, H // k), Image.LANCZOS)


def _marca(d, m: dict, W: int, H: int, base: float) -> None:
    import math
    cor = _rgb(m.get("cor", ""))
    larg = max(2, int(round(float(m.get("l", 3)) * base)))
    pts = [(p[0] * W, p[1] * H) for p in m.get("p") or []]
    if not pts:
        return
    tipo, n = m.get("tipo"), int(m.get("n") or 0)
    r = 15 * base
    onde = pts[0]                                        # onde vai o número
    if tipo == "ponto":
        d.ellipse([pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r], fill=cor + (255,), outline=(255, 255, 255),
                  width=max(1, int(2 * base)))
        if n:
            _centrado(d, pts[0], str(n), _fonte(int(18 * base)), (255, 255, 255))
        return
    if tipo == "texto":
        f = _fonte(int(20 * base))
        try:
            cx = d.textbbox(pts[0], m.get("texto", ""), font=f, anchor="lm")
            d.rectangle([cx[0] - 4 * base, cx[1] - 3 * base, cx[2] + 4 * base, cx[3] + 3 * base], fill=(255, 255, 255, 215))
            d.text(pts[0], m.get("texto", ""), font=f, fill=cor, anchor="lm")
        except (ValueError, TypeError):
            d.text(pts[0], m.get("texto", ""), font=f, fill=cor)
        return
    if tipo == "elipse" and len(pts) >= 2:
        x0, x1 = sorted((pts[0][0], pts[1][0]))
        y0, y1 = sorted((pts[0][1], pts[1][1]))
        d.ellipse([x0, y0, max(x1, x0 + 2), max(y1, y0 + 2)], outline=cor, width=larg, fill=cor + (46,))
        onde = (x1, y0)
    elif tipo == "seta" and len(pts) >= 2:
        (xa, ya), (xb, yb) = pts[0], pts[1]
        d.line([pts[0], pts[1]], fill=cor, width=larg)
        ang = math.atan2(yb - ya, xb - xa)
        c = 16 * base + larg * 1.5
        d.polygon([(xb, yb), (xb - c * math.cos(ang - 0.42), yb - c * math.sin(ang - 0.42)),
                   (xb - c * math.cos(ang + 0.42), yb - c * math.sin(ang + 0.42))], fill=cor)
        onde = pts[0]
    elif tipo == "traco":
        d.line(pts, fill=cor, width=larg, joint="curve")
        onde = pts[0]
    if n:
        rr = 12 * base
        d.ellipse([onde[0] - rr, onde[1] - rr, onde[0] + rr, onde[1] + rr], fill=cor + (255,), outline=(255, 255, 255),
                  width=max(1, int(2 * base)))
        _centrado(d, onde, str(n), _fonte(int(15 * base)), (255, 255, 255))


def png(e: dict, largura: int = 1100, repo=None) -> bytes:
    b = io.BytesIO()
    desenhar(e, largura, repo).save(b, "PNG", optimize=True)
    return b.getvalue()


def miniatura_do_modelo(id_: str, largura: int = 260, repo=None) -> bytes:
    return png({"modelo": id_, "marcas": [], "setores": {}}, largura, repo)


# ---------------------------------------------------------------------- elo com a imagem do exame
def rotulo_da_imagem(repo, study_uid: str, series_uid: str, sop_uid: str, frame: int = 0) -> str:
    """"série 3, imagem 12" (e o quadro, se a imagem tem vários): é o que a legenda mostra."""
    try:
        serie = next((s for s in repo.series_for_study(study_uid, True) if s.series_uid == series_uid), None)
        inst = next((i for i in repo.instances_for_series(series_uid) if i["sop_uid"] == sop_uid), None)
    except Exception:  # noqa: BLE001
        log.debug("esquema: rótulo da imagem", exc_info=True)
        return ""
    if serie is None or inst is None:
        return ""
    txt = f"série {serie.series_number}, imagem {inst.get('instance_number') or 1}"
    if int(inst.get("frames") or 1) > 1:
        txt += f", quadro {int(frame) + 1}"
    return txt


def ligar_imagem(repo, study_uid: str, series_uid: str, sop_uid: str, frame: int = 0) -> dict | None:
    """A imagem do exame para ligar a uma marca: passa a ser **imagem-chave** (se ainda não era) e ganha o rótulo.
    None se a imagem não é deste exame."""
    rot = rotulo_da_imagem(repo, study_uid, series_uid, sop_uid, frame)
    if not rot:
        return None
    frame = int(frame or 0)
    try:
        if (sop_uid, frame) not in repo.key_image_set(study_uid):
            repo.toggle_key_image(study_uid, series_uid, sop_uid, frame)
    except Exception:  # noqa: BLE001
        log.exception("esquema: imagem-chave")
    return {"series_uid": series_uid, "sop_uid": sop_uid, "frame": frame, "rotulo": rot}
