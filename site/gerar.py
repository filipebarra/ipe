"""Gera o site do Ipê (GitHub Pages) em `_site/` a partir de `conteudo.py` — só a biblioteca padrão do Python.

    python site/gerar.py [saida]

Inglês na raiz, português em /pt/ e espanhol em /es/. As mídias de `site/media/` são copiadas como estão.
O workflow `.github/workflows/site.yml` roda este script e publica a pasta.
"""
from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import conteudo as C  # noqa: E402

G, LINGUAS = C.GERAL, C.LINGUAS
PASTA_DO_CLIPE = {"en": "en", "pt": "pt", "es": "es"}

ICONES = {   # traços simples, 24×24, herdam a cor
    "olho": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "mama": '<path d="M4 4c7 2 9 6 9 9a5 5 0 0 1-9 3"/><path d="M20 4c-4 1-6 3-7 6"/><circle cx="9" cy="14" r="1.2"/>',
    "curva": '<path d="M3 20h18"/><path d="M3 20V4"/><path d="M5 17c3-9 5-10 8-10s4 2 8 1"/>',
    "alvo": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "faisca": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    "folha": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5"/><path d="M9 12h7M9 16h7"/>',
    "capelo": '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/><path d="M22 9v6"/>',
    "nuvem": '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9a4.5 4.5 0 0 0 1 9z"/>',
    "baixar": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "seta": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "voltar": '<path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/>',
    "tocar": '<path d="M7 5v14l12-7z"/>',
}


def ic(nome: str, cls: str = "ic") -> str:
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONES[nome]}</svg>')


def e(s: str) -> str:
    return html.escape(s, quote=True)


class Pagina:
    def __init__(self, lingua: str, caminho: str):
        self.l, self.caminho = lingua, caminho          # caminho relativo à raiz da língua: "index.html", "tasks/x.html"
        self.prof = caminho.count("/")

    def t(self, d: dict) -> str:
        return d[self.l]

    def raiz(self) -> str:
        """Caminho até a raiz do site (onde ficam media/ e assets/)."""
        return "../" * (self.prof + (0 if self.l == LINGUAS[0] else 1))

    def link(self, caminho: str, lingua: str | None = None) -> str:
        lingua = lingua or self.l
        base = self.raiz() + ("" if lingua == LINGUAS[0] else f"{lingua}/")
        return base + caminho

    # ------------------------------------------------------------------------------------------------- moldura
    def documento(self, titulo: str, corpo: str, descricao: str = "") -> str:
        r = self.raiz()
        alternativas = "".join(
            f'<link rel="alternate" hreflang="{l}" href="{e(self.link(self.caminho, l))}">' for l in LINGUAS)
        linguas = "".join(
            f'<a href="{e(self.link(self.caminho, l))}" lang="{l}" hreflang="{l}"'
            f'{" aria-current=\"true\"" if l == self.l else ""}>{l.upper()}</a>' for l in LINGUAS)
        navs = [("tasks/index.html", G["menu_tarefas"]), ("start.html", G["menu_comecar"]),
                ("videos.html", G["menu_videos"])]
        nav = "".join(
            f'<a href="{e(self.link(c))}"{" aria-current=\"page\"" if self.caminho == c else ""}>{e(self.t(x))}</a>'
            for c, x in navs)
        return f"""<!doctype html>
<html lang="{self.l}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao or self.t(G['descricao']))}">
<meta property="og:title" content="{e(titulo)}">
<meta property="og:description" content="{e(descricao or self.t(G['descricao']))}">
<meta property="og:image" content="{r}assets/social.jpg">
<meta name="theme-color" content="#11151a">
{alternativas}
<link rel="icon" href="{r}assets/ipe-64.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{r}assets/site.css">
</head>
<body data-lingua="{self.l}">
<a class="pular" href="#conteudo">{e({'en': 'Skip to content', 'pt': 'Pular para o conteúdo', 'es': 'Saltar al contenido'}[self.l])}</a>
<header class="topo">
  <div class="largura topo-linha">
    <a class="marca" href="{e(self.link('index.html'))}"><img src="{r}assets/ipe-64.png" alt="" width="32" height="32"><span>Ipê</span></a>
    <nav class="nav" aria-label="{e(self.t(G['menu_tarefas']))}">{nav}</nav>
    <div class="linguas" aria-label="Language">{linguas}</div>
    <a class="botao botao-pequeno" href="{C.REPO}/releases/latest">{ic('baixar')}<span>{e(self.t(G['menu_baixar']))}</span></a>
  </div>
</header>
<div class="sugestao" id="sugestao" hidden></div>
<main id="conteudo">
{corpo}
</main>
<footer class="rodape">
  <div class="largura">
    <p class="aviso">{e(self.t(G['aviso']))}</p>
    <p class="rodape-links">
      <a href="{C.REPO}">{e(self.t(G['rodape_codigo']))}</a>
      <a href="{C.REPO}/blob/main/CREDITOS.md">{e(self.t(G['rodape_creditos']))}</a>
      <a href="{C.REPO}/blob/main/{ {'en': 'CHANGELOG.en.md', 'pt': 'CHANGELOG.md', 'es': 'CHANGELOG.es.md'}[self.l] }">{e(self.t(G['rodape_historico']))}</a>
      <a href="{C.REPO}/raw/main/docs/Ipe-guia-do-usuario.pdf">{e(self.t(G['rodape_guia']))}</a>
    </p>
    <p class="licenca">{e(self.t(G['rodape_licenca']))}</p>
  </div>
</footer>
<script>window.IPE_LINGUAS = {{{",".join(f'"{l}": {{"url": "{self.link(self.caminho, l)}", "texto": "{e(G["sugerir_lingua"][l])}", "ir": "{e(G["sugerir_ir"][l])}"}}' for l in LINGUAS)}}};</script>
<script src="{r}assets/site.js" defer></script>
</body>
</html>
"""

    # ------------------------------------------------------------------------------------------------- peças
    def clipe(self, nome: str, legenda: str = "", grande: bool = False) -> str:
        r = self.raiz()
        pasta = PASTA_DO_CLIPE[self.l] if (AQUI / "media" / "clipes" / PASTA_DO_CLIPE[self.l] / f"{nome}.mp4").exists() \
            else "en"
        src = f"{r}media/clipes/{pasta}/{nome}"
        leg = f'<figcaption>{legenda}</figcaption>' if legenda else ""
        return (f'<figure class="clipe{" clipe-grande" if grande else ""}">'
                f'<div class="tela"><video muted loop playsinline preload="none" poster="{src}.jpg" '
                f'data-src="{src}.mp4" aria-label="{e(legenda or nome)}"></video>'
                f'<button class="clipe-botao" type="button" data-tocar="{e(self.t(G["clipe_tocar"]))}" '
                f'data-pausar="{e(self.t(G["clipe_pausar"]))}" aria-label="{e(self.t(G["clipe_pausar"]))}"></button>'
                f'</div>{leg}</figure>')

    def tutorial(self, tid: str) -> str:
        tu = C.TUTORIAIS[tid]
        r = self.raiz()
        yt = tu["youtube"].get(self.l) or tu["youtube"].get("en")
        arq = AQUI / "media" / "tutoriais" / f"{tid}-{self.l}.mp4"
        lingua_arq = self.l if arq.exists() else "pt"
        src = f"{r}media/tutoriais/{tid}-{lingua_arq}"
        if yt:
            player = (f'<div class="tela tela-video"><iframe src="https://www.youtube-nocookie.com/embed/{e(yt)}" '
                      f'title="{e(self.t(tu["titulo"]))}" loading="lazy" allow="encrypted-media; picture-in-picture; '
                      f'fullscreen" allowfullscreen></iframe></div>')
            extra = f'<a href="https://www.youtube.com/watch?v={e(yt)}">{e(self.t(G["assistir_youtube"]))}</a>'
        else:
            player = (f'<div class="tela tela-video"><video controls preload="none" poster="{src}.jpg">'
                      f'<source src="{src}.mp4" type="video/mp4"></video></div>')
            extra = f'<a href="{src}.mp4" download>{e(self.t(G["baixar_video"]))}</a>'
        return (f'<article class="tutorial">{player}<div class="tutorial-texto">'
                f'<h3>{e(self.t(tu["titulo"]))} <span class="duracao">{e(tu["duracao"])}</span></h3>'
                f'<p>{e(self.t(tu["texto"]))}</p><p class="mais">{extra}</p></div></article>')

    def cartao_tarefa(self, ta: dict) -> str:
        r = self.raiz()
        pasta = PASTA_DO_CLIPE[self.l] if (AQUI / "media" / "clipes" / PASTA_DO_CLIPE[self.l] /
                                           f"{ta.get('cartao', ta['clipe'])}.jpg").exists() else "en"
        return (f'<a class="cartao" href="{e(self.link("tasks/" + ta["slug"] + ".html"))}">'
                f'<div class="cartao-img"><img src="{r}media/clipes/{pasta}/{ta.get("cartao", ta["clipe"])}.jpg" alt="" loading="lazy" '
                f'width="800" height="480"></div>'
                f'<div class="cartao-texto"><span class="cartao-icone">{ic(ta["icone"])}</span>'
                f'<h3>{e(self.t(ta["titulo"]))}</h3><p>{e(self.t(ta["frase"]))}</p>'
                f'<span class="cartao-ver">{e(self.t(G["ver_tarefa"]))} {ic("seta")}</span></div></a>')


# ------------------------------------------------------------------------------------------------------- páginas
def pagina_inicial(l: str) -> str:
    p = Pagina(l, "index.html")
    titulo = p.t(G["hero_titulo"]).split("\n")
    destaques = "".join(f'<li><strong>{e(n)}</strong><span>{e(p.t(t))}</span></li>' for n, t in C.DESTAQUES)
    cartoes = "".join(p.cartao_tarefa(ta) for ta in C.TAREFAS)
    corpo = f"""
<section class="hero">
  <div class="largura hero-grade">
    <div class="hero-texto">
      <p class="selo">{e(p.t(G['hero_sistemas']))}</p>
      <h1>{e(titulo[0])}<br><span class="destaque">{e(titulo[1])}</span></h1>
      <p class="lead">{e(p.t(G['hero_texto']))}</p>
      <p class="acoes">
        <a class="botao" href="{C.REPO}/releases/latest">{ic('baixar')}<span>{e(p.t(G['hero_baixar']))}</span></a>
        <a class="botao botao-secundario" href="#tarefas"><span>{e(p.t(G['hero_ver']))}</span>{ic('seta')}</a>
      </p>
    </div>
    <div class="hero-midia">{p.clipe('ler', grande=True)}</div>
  </div>
</section>
<section class="faixa">
  <div class="largura"><h2 class="sr">{e(p.t(G['destaques_titulo']))}</h2><ul class="destaques">{destaques}</ul></div>
</section>
<section class="secao" id="tarefas">
  <div class="largura">
    <h2>{e(p.t(G['tarefas_titulo']))}</h2>
    <p class="secao-lead">{e(p.t(G['tarefas_texto']))}</p>
    <div class="cartoes">{cartoes}</div>
  </div>
</section>
<section class="secao secao-alt">
  <div class="largura duas">
    <div>
      <h2>{e(p.t(C.TUTORIAIS['curso']['titulo']))}</h2>
      <p class="secao-lead">{e(p.t(C.TUTORIAIS['curso']['texto']))}</p>
      <p><a class="link-seta" href="{e(p.link('videos.html'))}">{e(p.t(G['menu_videos']))} {ic('seta')}</a></p>
    </div>
    <div>{p.tutorial('curso')}</div>
  </div>
</section>
<section class="secao">
  <div class="largura historia">
    <img src="{p.raiz()}assets/ipe-256.png" alt="" width="120" height="120">
    <div>
      <h2>{e(p.t(G['por_que_titulo']))}</h2>
      <p>{p.t(G['por_que_texto'])}</p>
      <p><a class="link-seta" href="{C.REPO}/blob/main/{ {'en': 'HISTORIA.en.md', 'pt': 'HISTORIA.md', 'es': 'HISTORIA.es.md'}[l] }">{e(p.t(G['por_que_mais']))} {ic('seta')}</a></p>
    </div>
  </div>
</section>
"""
    return p.documento(p.t(G["titulo"]), corpo)


def pagina_tarefas(l: str) -> str:
    p = Pagina(l, "tasks/index.html")
    cartoes = "".join(p.cartao_tarefa(ta) for ta in C.TAREFAS)
    corpo = f"""
<section class="secao">
  <div class="largura">
    <h1>{e(p.t(G['tarefas_titulo']))}</h1>
    <p class="secao-lead">{e(p.t(G['tarefas_texto']))}</p>
    <div class="cartoes">{cartoes}</div>
  </div>
</section>"""
    return p.documento(f"{p.t(G['tarefas_titulo'])} — Ipê", corpo)


def pagina_tarefa(l: str, i: int) -> str:
    ta = C.TAREFAS[i]
    p = Pagina(l, f"tasks/{ta['slug']}.html")
    passos = "".join(f"<li>{p.t(x)}</li>" for x in ta["passos"])
    recursos = "".join(
        f'<li><h3>{e(p.t(n))}</h3><p>{e(p.t(t))}</p><p class="onde"><span>{e(p.t(G["onde"]))}:</span> '
        f'{e(p.t(w))}</p></li>' for n, t, w in ta["recursos"])
    extras = "".join(p.clipe(nome, e(p.t(leg))) for nome, leg in ta["extras"])
    videos = ""
    if ta["videos"]:
        videos = (f'<section class="secao secao-alt"><div class="largura"><h2>{e(p.t(G["videos_relacionados"]))}</h2>'
                  + "".join(p.tutorial(v) for v in ta["videos"]) + "</div></section>")
    ant, prox = C.TAREFAS[i - 1] if i > 0 else None, C.TAREFAS[i + 1] if i + 1 < len(C.TAREFAS) else None
    navega = '<nav class="navega">'
    navega += (f'<a href="{e(p.link("tasks/" + ant["slug"] + ".html"))}">{ic("voltar")}<span><small>'
               f'{e(p.t(G["anterior"]))}</small>{e(p.t(ant["titulo"]))}</span></a>') if ant else "<span></span>"
    navega += f'<a class="navega-todas" href="{e(p.link("tasks/index.html"))}">{e(p.t(G["todas"]))}</a>'
    navega += (f'<a class="navega-prox" href="{e(p.link("tasks/" + prox["slug"] + ".html"))}"><span><small>'
               f'{e(p.t(G["proxima"]))}</small>{e(p.t(prox["titulo"]))}</span>{ic("seta")}</a>') if prox else \
        "<span></span>"
    navega += "</nav>"
    corpo = f"""
<section class="secao tarefa-topo">
  <div class="largura">
    <p class="migalha"><a href="{e(p.link('tasks/index.html'))}">{e(p.t(G['menu_tarefas']))}</a></p>
    <h1><span class="h1-icone">{ic(ta['icone'])}</span>{e(p.t(ta['titulo']))}</h1>
    <p class="lead">{e(p.t(ta['frase']))}</p>
    {p.clipe(ta['clipe'], e(p.t(G['clipe_legenda'])), grande=True)}
  </div>
</section>
<section class="secao">
  <div class="largura{' duas duas-passos' if extras else ''}">
    <div>
      <h2>{e(p.t(G['passos']))}</h2>
      <ol class="passos{'' if extras else ' passos-largos'}">{passos}</ol>
    </div>
    {f'<div class="extras">{extras}</div>' if extras else ''}
  </div>
</section>
<section class="secao secao-alt">
  <div class="largura">
    <h2>{e(p.t(G['recursos']))}</h2>
    <ul class="recursos">{recursos}</ul>
  </div>
</section>
{videos}
<section class="secao"><div class="largura">{navega}</div></section>
"""
    return p.documento(f"{p.t(ta['titulo'])} — Ipê", corpo, p.t(ta["frase"]))


def pagina_videos(l: str) -> str:
    p = Pagina(l, "videos.html")
    tut = "".join(p.tutorial(t) for t in C.TUTORIAIS)
    clipes = "".join(
        f'<a class="mini" href="{e(p.link("tasks/" + ta["slug"] + ".html"))}">{p.clipe(ta["clipe"])}'
        f'<span>{e(p.t(ta["titulo"]))}</span></a>' for ta in C.TAREFAS)
    corpo = f"""
<section class="secao">
  <div class="largura">
    <h1>{e(p.t(G['videos_titulo']))}</h1>
    <p class="secao-lead">{e(p.t(G['videos_texto']))}</p>
    {tut}
    <p class="em-breve">{e(p.t(G['em_breve']))}</p>
  </div>
</section>
<section class="secao secao-alt">
  <div class="largura">
    <h2>{e(p.t(G['tarefas_titulo']))}</h2>
    <div class="minis">{clipes}</div>
  </div>
</section>"""
    return p.documento(f"{p.t(G['videos_titulo'])} — Ipê", corpo)


def pagina_comecar(l: str) -> str:
    p = Pagina(l, "start.html")
    cc = C.COMECAR
    sistemas = "".join(f'<li><h3>{e(n)}</h3><p>{p.t(t)}</p></li>' for n, t in cc["sistemas"])
    passos = "".join(f"<li>{p.t(x)}</li>" for x in cc["passos"])
    corpo = f"""
<section class="secao">
  <div class="largura">
    <h1>{e(p.t(cc['titulo']))}</h1>
    <p class="secao-lead">{e(p.t(cc['texto']))}</p>
    <p class="acoes"><a class="botao" href="{C.REPO}/releases/latest">{ic('baixar')}<span>{e(p.t(G['hero_baixar']))}</span></a></p>
    <ul class="recursos sistemas">{sistemas}</ul>
  </div>
</section>
<section class="secao secao-alt">
  <div class="largura duas duas-passos">
    <div><h2>{e(p.t(G['passos']))}</h2><ol class="passos">{passos}</ol><p class="nota">{e(p.t(cc['ia']))}</p></div>
    <div class="extras">{p.clipe('banco', e(p.t(C.TAREFAS[0]['extras'][0][1])))}</div>
  </div>
</section>"""
    return p.documento(f"{p.t(cc['titulo'])} — Ipê", corpo)


def gerar(saida: Path) -> None:
    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    shutil.copytree(AQUI / "assets", saida / "assets")
    if (AQUI / "media").exists():
        shutil.copytree(AQUI / "media", saida / "media")
    for l in LINGUAS:
        base = saida if l == LINGUAS[0] else saida / l
        (base / "tasks").mkdir(parents=True, exist_ok=True)
        (base / "index.html").write_text(pagina_inicial(l), encoding="utf-8")
        (base / "tasks" / "index.html").write_text(pagina_tarefas(l), encoding="utf-8")
        (base / "videos.html").write_text(pagina_videos(l), encoding="utf-8")
        (base / "start.html").write_text(pagina_comecar(l), encoding="utf-8")
        for i, ta in enumerate(C.TAREFAS):
            (base / "tasks" / f"{ta['slug']}.html").write_text(pagina_tarefa(l, i), encoding="utf-8")
    (saida / ".nojekyll").write_text("", encoding="utf-8")
    (saida / "404.html").write_text(
        '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=/ipe/">'
        '<title>Ipê</title><a href="/ipe/">Ipê</a>', encoding="utf-8")
    n = sum(1 for _ in saida.rglob("*.html"))
    print(f"site: {n} páginas em {saida}")


if __name__ == "__main__":
    gerar(Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI.parent / "_site")
