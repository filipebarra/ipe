

def test_motivo_traduzido_em_ingles():
    """0.100.96: no Ipê em inglês, o menu das IAs dizia "o exame não tem CT" e "não achei no exame: Crânio and brain"."""
    from ipe.core import i18n
    from ipe.ui.viewer import aplicacoes as A
    try:
        i18n.load("en")
        ctx = A.Contexto(modalidades={"MR"}, regioes={"abdome"})
        assert A.avaliar(A.APLICACOES["composicao"], ctx)[1] == "the study has no CT"
        assert A.avaliar(A.APLICACOES["indices"], ctx)[1] == "not found in the study: Skull and brain"
        assert "Dynamic series" in A.avaliar(A.APLICACOES["dinamica"], ctx)[1]
    finally:
        i18n.load("pt-BR")
