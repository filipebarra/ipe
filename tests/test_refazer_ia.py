"""0.100.90: "Refazer no exame" em todas as IAs, e as IAs no menu Configurações ▸ CAD/IA."""
from types import SimpleNamespace

import pytest

from ipe.ui.viewer import ia_aba as IA


class _Aba:
    """O mínimo da aba para o despacho do "Refazer"."""

    def __init__(self, preferida="S2"):
        self.chamadas = []
        self.study_uid = "E1"
        self.study_order = ["E1"]
        self.settings = None
        self.carregou = []
        self.active = SimpleNamespace(series_uid="S1", study_uid="E1", frames=[1])
        self.viewports = [self.active]
        self.preferida = preferida
        self.repo = SimpleNamespace(achados=lambda u, t: [], revisar_achado=lambda *a, **k: None)

    def load_series_into(self, vp, uid):
        self.carregou.append(uid)
        vp.series_uid = uid

    def achados_mudaram(self):
        pass

    def __getattr__(self, nome):
        if nome.startswith("_quadro") or nome == "refazer_ia":
            return getattr(IA.IAMixin, nome).__get__(self)
        return lambda *a, **k: self.chamadas.append((nome, getattr(a[0], "series_uid", None) if a else None, k))


@pytest.mark.parametrize("tipo,metodo,kw", [
    ("abdome", "segmentar_orgaos", {}), ("coluna", "segmentar_orgaos", {"tipo": "coluna"}),
    ("cefalometria", "cefalometria_automatica", {}), ("neuro", "neuro_automatica", {}),
    ("linfonodos", "linfonodos_automatico", {})])
def test_refazer_as_especiais_na_serie_preferida(monkeypatch, tipo, metodo, kw):
    monkeypatch.setattr(IA, "escolher_serie_de", lambda t: (lambda repo, uid, st: ("S2", "")))
    a = _Aba()
    a.refazer_ia(tipo)
    nome, serie, k = a.chamadas[-1]
    assert nome == metodo and serie == "S2" and a.carregou == ["S2"]
    assert all(k.get(x) == v for x, v in kw.items())


def test_refazer_as_outras():
    a = _Aba()
    a.refazer_ia("densidade")
    a.refazer_ia("calc_vascular")
    a.refazer_ia("enfisema")
    assert [c[0] for c in a.chamadas] == ["densidade_em_segundo_plano", "calc_vascular_em_segundo_plano",
                                          "ferramenta_ia"]


def test_menu_cad_ia_tem_todas_as_ias():
    from ipe.ai import ferramentas as FE
    from ipe.ui import configuracoes as C
    itens = [t for t, _a, _p in dict(C.CATALOGO)["CAD/IA"]]
    for t in FE.tipos():
        assert FE.modulo(t).NOME_CADIA + "…" in itens
    for n in ("Níveis da coluna…", "Níveis linfonodais…", "Cefalometria do cavum…", "Densidade e calcificações (mama)…"):
        assert n in itens
    assert itens[0] == "Análises automáticas (CAD/IA)…" and itens[-1].startswith("Modelos de pesquisa")
