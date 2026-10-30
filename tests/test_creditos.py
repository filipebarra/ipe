"""0.99.13: a história do Ipê e os créditos. E a regra pedida por ele: toda ferramenta que entrar no
programa entra também nos créditos — este teste reprova quando não entra."""
import ast
import sys
import tomllib
from pathlib import Path

from PySide6.QtWidgets import QApplication

from ipe import creditos
from ipe.ui import ajuda

RAIZ = Path(__file__).resolve().parents[1]


def _requisitos() -> set[str]:
    cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    projeto = cfg["project"]
    reqs = list(projeto.get("dependencies", []))
    for lista in (projeto.get("optional-dependencies") or {}).values():
        reqs += lista
    nomes = set()
    for r in reqs:
        nome = r.split(";")[0]
        for sep in "<>=!~[ ":
            nome = nome.split(sep)[0]
        nomes.add(nome.strip().lower().replace("_", "-"))
    return nomes


def _imports_de_terceiros() -> set[str]:
    proprios = {"ipe", "dicomviewer"}
    achados = set()
    for pasta in ("src", "tools", "installer"):
        for arq in (RAIZ / pasta).rglob("*.py"):
            try:
                arvore = ast.parse(arq.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name for a in no.names]
                elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                    nomes = [no.module]
                else:
                    continue
                for n in nomes:
                    topo = n.split(".")[0]
                    if topo not in sys.stdlib_module_names and topo not in proprios:
                        achados.add(topo)
    # módulos locais das ferramentas (tools/) que se importam entre si
    locais = {p.stem for p in (RAIZ / "tools").rglob("*.py")}
    return achados - locais


def test_todo_pacote_do_pyproject_tem_credito():
    com_credito = {p.lower().replace("_", "-") for c in creditos.CREDITOS for p in c.pacotes}
    faltam = _requisitos() - com_credito
    assert not faltam, f"pacotes sem crédito em src/ipe/creditos.py: {sorted(faltam)}"


def test_todo_import_de_terceiros_tem_credito():
    com_credito = {m for c in creditos.CREDITOS for m in c.modulos}
    faltam = _imports_de_terceiros() - com_credito
    assert not faltam, f"imports sem crédito em src/ipe/creditos.py: {sorted(faltam)}"


def test_todo_credito_tem_licenca_e_link():
    for c in creditos.CREDITOS:
        assert c.licenca and c.link.startswith("https://"), c.nome
        assert c.onde in creditos.NOME_DO_ONDE, c.nome
    assert any(c.nome == "TotalSegmentator" and c.citacao for c in creditos.CREDITOS)


def test_arquivos_da_raiz_estao_em_dia():
    sys.path.insert(0, str(RAIZ / "tools"))
    import gerar_creditos
    for caminho, texto in gerar_creditos.arquivos().items():
        assert caminho.read_text(encoding="utf-8") == texto, \
            f"{caminho.name} desatualizado: rode python tools/gerar_creditos.py"


def test_historia_nos_tres_idiomas():
    for idioma, trecho in (("pt-BR", "Fil**ipe**"), ("en", "Fil**ipe**"), ("es", "Fil**ipe**")):
        p = ajuda.caminho_da_historia(idioma)
        assert p is not None and p.name == f"historia.{idioma}.md"
        texto = p.read_text(encoding="utf-8")
        assert trecho in texto and "Claude" in texto and "TotalSegmentator" in texto
    assert ajuda.caminho_da_historia("de").name == "historia.pt-BR.md"     # sem tradução: português


def test_sobre_tem_a_historia_e_os_creditos():
    QApplication.instance() or QApplication([])
    d = ajuda.janela_sobre()
    assert d.b_historia.text() == "A história do Ipê" and d.b_creditos.text() == "Créditos e licenças"
    assert "Fil<b>ipe</b>" in ajuda.texto_sobre()
    h = ajuda.janela_da_historia(d)
    assert "Por que Ipê" in h.texto.toPlainText()
    c = ajuda.janela_de_creditos(d)
    assert "TotalSegmentator" in c.texto.toPlainText() and "Apache-2.0" in c.texto.toPlainText()
    assert c.texto.openExternalLinks()


def test_historia_e_creditos_vao_no_pacote():
    cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert "ajuda/*.md" in cfg["tool"]["setuptools"]["package-data"]["ipe"]
    spec = (RAIZ / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"ipe" / "ajuda"' in spec
