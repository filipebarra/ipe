"""Onde uma análise roda: a regra que escolhe as imagens pelo que o DICOM diz.

Cada serviço tem aparelho e protocolo diferentes — por isso a regra é do usuário, e por isso ela
precisa ser explícita sobre o que **não** consegue decidir.

**Nenhuma análise usa este mecanismo hoje.** A densidade mamária usou na 0.37 e saiu dele na 0.39
(na tela, quem escolhe as imagens é o médico, pondo-as no quadro). O módulo fica, inteiro e
testado, para a próxima análise que precisar varrer o acervo — que é onde a regra faz falta.
"""

import pytest

from PySide6.QtCore import Qt

from ipe.core import selecao as S
from ipe.core.config import Settings


def crit(campo, operador, valor):
    return S.Criterio(campo=campo, operador=operador, valor=valor)


MG = {"modalidade": "MG", "descricao": "R CC Tomosynthesis", "vista": "CC", "lado": "R",
      "quadros": "1", "classe": "1.2.840.10008.5.1.4.1.1.1.2", "aparelho": "GE Senographe"}


# ------------------------------------------------------------------ operadores
@pytest.mark.parametrize("op,valor,esperado", [
    ("contem", "tomo", True), ("contem", "espiculado", False),
    ("nao_contem", "espiculado", True), ("nao_contem", "tomo", False),
    ("igual", "r cc tomosynthesis", True), ("igual", "R CC", False),
    ("diferente", "outra coisa", True),
    ("comeca", "R CC", True), ("comeca", "CC", False),
    ("regex", r"^R\s+CC", True), ("regex", r"^L\s+CC", False),
    ("regex", "[", False),                       # expressão inválida não derruba: só não combina
])
def test_operadores_na_descricao(op, valor, esperado):
    assert crit("descricao", op, valor).combina(MG) is esperado


def test_um_de_aceita_lista():
    c = crit("vista", "um_de", "CC, MLO, XCCL")
    assert c.combina(MG)
    assert not c.combina({**MG, "vista": "ML"})


def test_compara_sem_caixa_e_sem_espaco_repetido():
    assert crit("descricao", "igual", "  r   cc   TOMOSYNTHESIS ").combina(MG)


# ------------------------------------------------------------------ o que falta
def test_campo_que_o_chamador_nao_trouxe_nao_combina():
    """Sem o arquivo aberto não dá para saber a incidência — e "não sei" nunca vira "sim"."""
    regra = S.Selecao(nome="x", criterios=[crit("vista", "igual", "CC")])
    assert not regra.combina({"modalidade": "MG"})
    assert regra.faltando({"modalidade": "MG"}) == ["vista"]
    assert regra.faltando(MG) == []


def test_parcial_ignora_o_que_ainda_nao_da_para_saber():
    """A prévia precisa de um limite de cima; `combina` continua exigindo tudo."""
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"), crit("vista", "igual", "CC")])
    so_banco = {"modalidade": "MG", "descricao": "mamo"}
    assert regra.parcial(so_banco)          # passa pelo que dá para saber
    assert not regra.combina(so_banco)      # mas não roda sem conferir a incidência
    assert not regra.parcial({"modalidade": "CT"})
    assert not S.Selecao(criterios=[]).parcial(so_banco)
    assert not S.Selecao(ativa=False, criterios=[crit("modalidade", "igual", "MG")]).parcial(so_banco)


def test_filtrar_parcial_pega_mais_que_o_estrito():
    regras = [S.Selecao(criterios=[crit("modalidade", "igual", "MG"), crit("vista", "igual", "CC")])]
    itens = [{"modalidade": "MG"}, {"modalidade": "CT"}]
    assert len(S.filtrar(regras, itens, lambda i: i)) == 0
    assert len(S.filtrar(regras, itens, lambda i: i, parcial=True)) == 1


def test_sabe_quando_precisa_abrir_o_arquivo():
    so_banco = [S.Selecao(criterios=[crit("descricao", "contem", "mamo")])]
    com_vista = [S.Selecao(criterios=[crit("vista", "igual", "CC")])]
    assert not S.precisa_do_arquivo(so_banco)
    assert S.precisa_do_arquivo(com_vista)


# ------------------------------------------------------------------ E / OU
def test_criterios_da_mesma_selecao_sao_e():
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"),
                                 crit("vista", "igual", "CC")])
    assert regra.combina(MG)
    assert not regra.combina({**MG, "vista": "MLO"})


def test_selecoes_diferentes_sao_ou():
    regras = [S.Selecao(nome="CC", criterios=[crit("vista", "igual", "CC")]),
              S.Selecao(nome="MLO", criterios=[crit("vista", "igual", "MLO")])]
    assert S.escolhe(regras, MG).nome == "CC"
    assert S.escolhe(regras, {**MG, "vista": "MLO"}).nome == "MLO"
    assert S.escolhe(regras, {**MG, "vista": "ML"}) is None


def test_selecao_desligada_nao_pega_nada():
    regra = S.Selecao(ativa=False, criterios=[crit("modalidade", "igual", "MG")])
    assert not regra.combina(MG)


def test_selecao_sem_criterio_nao_pega_tudo():
    """Regra vazia pegando tudo seria a pior falha possível: rodaria o modelo no acervo inteiro."""
    assert not S.Selecao(criterios=[]).combina(MG)
    assert "não pega nada" in S.Selecao(criterios=[]).texto()


def test_filtrar_uma_lista():
    regras = [S.Selecao(criterios=[crit("vista", "um_de", "CC, MLO")])]
    itens = [{"v": "CC"}, {"v": "ML"}, {"v": "MLO"}]
    saida = S.filtrar(regras, itens, lambda i: {"vista": i["v"]})
    assert [i["v"] for i in saida] == ["CC", "MLO"]


# ------------------------------------------------------------------ guardar
#: um padrão de bancada. O catálogo de fábrica (`S.PADROES`) está **vazio de propósito** desde a
#: 0.39 — a densidade saiu dele —, mas "carregar o padrão" e "restaurar o padrão" continuam sendo
#: o contrato do módulo, e contrato sem teste não é contrato.
EXEMPLO = [{"nome": "Mamografia 2D, CC e MLO", "ativa": True, "criterios": [
    {"campo": "modalidade", "operador": "igual", "valor": "MG"},
    {"campo": "classe", "operador": "igual", "valor": "1.2.840.10008.5.1.4.1.1.1.2"},
    {"campo": "quadros", "operador": "igual", "valor": "1"},
    {"campo": "vista", "operador": "um_de", "valor": "CC, MLO"},
]}]


@pytest.fixture()
def padrao(monkeypatch):
    monkeypatch.setitem(S.PADROES, "exemplo", EXEMPLO)
    return "exemplo"


def test_o_catalogo_de_fabrica_esta_vazio(env):
    """A densidade não usa mais regra: nenhuma análise vem com padrão pronto."""
    paths, _db, _repo = env
    assert S.PADROES == {}
    assert S.carregar(Settings(paths.settings_file), "densidade") == []


def test_o_padrao_de_fabrica_pega_a_2d_e_recusa_a_tomo(env, padrao):
    paths, _db, _repo = env
    regras = S.carregar(Settings(paths.settings_file), padrao)
    assert len(regras) == 1 and regras[0].ativa
    assert S.escolhe(regras, MG) is not None
    tomo = {**MG, "quadros": "60", "classe": "1.2.840.10008.5.1.4.1.1.13.1.3"}
    assert S.escolhe(regras, tomo) is None
    assert S.escolhe(regras, {**MG, "vista": "ML"}) is None


def test_guarda_e_volta_ao_padrao(env, padrao):
    paths, _db, _repo = env
    cfg = Settings(paths.settings_file)
    S.salvar(cfg, padrao, [S.Selecao(nome="só minha", criterios=[crit("vista", "igual", "ML")])])
    lidas = S.carregar(Settings(paths.settings_file), padrao)
    assert [x.nome for x in lidas] == ["só minha"]
    voltou = S.restaurar_padrao(cfg, padrao)
    assert voltou[0].nome == "Mamografia 2D, CC e MLO"


def test_ida_e_volta_pelo_dicionario():
    regra = S.Selecao(nome="x", criterios=[crit("descricao", "regex", "^R")])
    assert S.Selecao.from_dict(regra.to_dict()).to_dict() == regra.to_dict()
    assert S.Criterio.from_dict({"campo": "vista", "lixo": 1}).campo == "vista"


def test_texto_legivel_da_regra():
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"), crit("vista", "um_de", "CC, MLO")])
    t = regra.texto()
    assert "Modalidade é igual a “MG”" in t and " e " in t and "Incidência" in t


# ------------------------------------------------------------------ o acervo alimenta o menu
def test_valores_do_acervo_vem_do_banco(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    mods = dict(repo.valores_do_acervo("modalidade"))
    assert "CT" in mods and mods["CT"] >= 1
    assert repo.valores_do_acervo("campo_que_nao_existe") == []
    descr = repo.valores_do_acervo("descricao")
    assert descr and all(isinstance(v, str) and n > 0 for v, n in descr)


def test_series_para_analise_traz_os_campos_do_banco(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    linhas = repo.series_para_analise(modalidades=["MG"])
    assert linhas and all(r["modalidade"] == "MG" for r in linhas)
    assert all(set(S.DO_BANCO) <= set(r) for r in linhas)
    assert all(r["imagens"] >= 1 for r in linhas)


# ------------------------------------------------------------------ ligado à densidade
def test_atributos_saem_do_arquivo_de_mamografia():
    from ipe.imaging import density as D
    from test_densidade import _mamo
    ds, _ = _mamo(lado="L", incidencia="MLO")
    a = D.atributos(ds)
    assert a["modalidade"] == "MG" and a["vista"] == "MLO" and a["lado"] == "L"
    assert a["quadros"] == "1" and a["classe"].endswith("1.1.1.2")


def test_a_regra_decide_em_cima_dos_atributos_do_arquivo(env, padrao):
    """A densidade saiu daqui, mas a ponte continua: atributos do arquivo entram na regra.

    É o que a próxima análise vai usar para escolher imagem no acervo inteiro.
    """
    from ipe.imaging import density as D
    from test_densidade import _mamo
    paths, _db, _repo = env
    regras = S.carregar(Settings(paths.settings_file), padrao)
    ds_cc, _ = _mamo(incidencia="CC")
    ds_ml, _ = _mamo(incidencia="ML")
    assert S.escolhe(regras, D.atributos(ds_cc)) is not None
    assert S.escolhe(regras, D.atributos(ds_ml)) is None   # perfil não entra no padrão
    regras.append(S.Selecao(nome="perfil", criterios=[crit("vista", "igual", "ML")]))
    assert S.escolhe(regras, D.atributos(ds_ml)) is not None


# ------------------------------------------------------------------ a tela
def _tela(env, sample_dir=None, analise="exemplo"):
    from PySide6.QtWidgets import QApplication
    from ipe.ui.selecao_dialog import SelecaoDialog
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    if sample_dir is not None:
        from ipe.importer.scanner import Importer
        Importer(db, paths.storage).import_paths([sample_dir])
    return SelecaoDialog(Settings(paths.settings_file), analise, repo), repo


def test_tela_abre_com_o_padrao(env, padrao):
    dlg, _ = _tela(env, analise=padrao)
    assert dlg.lista.count() == 1
    assert "Mamografia 2D" in dlg.lista.item(0).text()
    assert dlg.lista.item(0).checkState() == Qt.Checked


def test_desmarcar_desliga_a_regra_e_grava(env, padrao):
    paths, _db, _repo = env
    dlg, _ = _tela(env, analise=padrao)
    dlg.lista.item(0).setCheckState(Qt.Unchecked)
    gravadas = S.carregar(Settings(paths.settings_file), padrao)
    assert gravadas[0].ativa is False


def test_o_editor_oferece_os_valores_do_acervo(env, sample_dir):
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env, sample_dir)
    ed = EditorSelecao(S.Selecao(criterios=[S.Criterio("modalidade", "igual", "")]), repo)
    combo = ed.tabela.cellWidget(0, 3)   # coluna do valor (a 0 virou E/OU)
    oferecidos = {combo.itemText(i) for i in range(combo.count())}
    assert "CT" in oferecidos and "MG" in oferecidos     # saiu do banco, não de lista fixa


def test_a_previa_conta_no_acervo_e_avisa_do_que_falta(env, sample_dir):
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env, sample_dir)
    ed = EditorSelecao(S.Selecao(criterios=[S.Criterio("modalidade", "igual", "MG")]), repo)
    assert "série(s)" in ed.previa.text() and "exame(s)" in ed.previa.text()
    assert ": 0 série(s)" not in ed.previa.text()     # a prévia não pode zerar por falta de dado
    ed2 = EditorSelecao(S.Selecao(criterios=[S.Criterio("vista", "igual", "CC")]), repo)
    assert "abrindo cada imagem" in ed2.previa.text()   # honesto sobre o limite da prévia
    assert "limite de cima" in ed2.previa.text()


def test_regra_sem_criterio_nao_e_aceita(env, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env)
    ed = EditorSelecao(S.Selecao(), repo)
    while ed.tabela.rowCount():
        ed.tabela.removeRow(0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    ed.aceitar()
    assert ed.result() != QDialog_Accepted()


def QDialog_Accepted():
    from PySide6.QtWidgets import QDialog
    return QDialog.Accepted


def test_restaurar_padrao_volta_tudo(env, monkeypatch, padrao):
    from PySide6.QtWidgets import QMessageBox
    paths, _db, _repo = env
    dlg, _ = _tela(env, analise=padrao)
    dlg.regras = [S.Selecao(nome="minha", criterios=[S.Criterio("vista", "igual", "ML")])]
    dlg.guardar()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dlg.restaurar()
    assert dlg.regras[0].nome == "Mamografia 2D, CC e MLO"


# ------------------------------------------------------------------ E / OU dentro da regra
def ou(campo, operador, valor):
    return S.Criterio(campo=campo, operador=operador, valor=valor, ligacao="ou")


def test_o_caso_do_usuario_v_preview_ou_proc():
    """“quero as séries que contenham v-preview OU proc” — dois critérios no mesmo campo."""
    regra = S.Selecao(nome="preview ou proc", criterios=[
        crit("descricao", "contem", "v-preview"),
        ou("descricao", "contem", "proc")])
    assert regra.combina({"descricao": "MAMA V-PREVIEW"})
    assert regra.combina({"descricao": "Mama PROC"})
    assert not regra.combina({"descricao": "Mama tomo"})


def test_o_mesmo_caso_num_criterio_so():
    """`contém um de` resolve em uma linha; `um de` não serve, porque compara igualdade exata."""
    um = S.Selecao(criterios=[crit("descricao", "contem_um_de", "v-preview, proc")])
    assert um.combina({"descricao": "MAMA V-PREVIEW"}) and um.combina({"descricao": "x proc y"})
    assert not um.combina({"descricao": "Mama tomo"})
    exato = S.Selecao(criterios=[crit("descricao", "um_de", "v-preview, proc")])
    assert not exato.combina({"descricao": "MAMA V-PREVIEW"})   # é "contém", não "igual"
    assert exato.combina({"descricao": "proc"})


def test_e_amarra_mais_forte_que_ou():
    """“A e B ou C” é “(A e B) ou C”, como em qualquer linguagem."""
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"),
                                 crit("vista", "igual", "CC"),
                                 ou("descricao", "contem", "especial")])
    assert regra.combina({"modalidade": "MG", "vista": "CC", "descricao": ""})
    assert regra.combina({"modalidade": "CT", "vista": "AX", "descricao": "muito especial"})
    assert not regra.combina({"modalidade": "MG", "vista": "MLO", "descricao": "comum"})


def test_grupos_separam_pelos_ou():
    cs = [crit("a", "igual", "1"), crit("b", "igual", "2"),
          ou("c", "igual", "3"), crit("d", "igual", "4"), ou("e", "igual", "5")]
    assert [[c.campo for c in g] for g in S.grupos(cs)] == [["a", "b"], ["c", "d"], ["e"]]
    assert S.grupos([]) == []


def test_ligacao_do_primeiro_criterio_e_ignorada():
    regra = S.Selecao(criterios=[ou("modalidade", "igual", "MG")])
    assert regra.combina({"modalidade": "MG"})
    assert not regra.combina({"modalidade": "CT"})


def test_texto_mostra_o_agrupamento():
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"),
                                 crit("vista", "igual", "CC"),
                                 ou("descricao", "contem", "proc")])
    t = regra.texto()
    assert "e também" in t and "ou então" in t
    assert t.index("ou então") > t.index("e também")


def test_parcial_tambem_respeita_o_ou():
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "CT"),
                                 ou("descricao", "contem", "mamo")])
    assert regra.parcial({"modalidade": "MG", "descricao": "mamo bilateral"})
    assert not regra.parcial({"modalidade": "MG", "descricao": "cranio"})


def test_ida_e_volta_guarda_a_ligacao():
    regra = S.Selecao(criterios=[crit("a", "igual", "1"), ou("b", "igual", "2")])
    voltou = S.Selecao.from_dict(regra.to_dict())
    assert [c.ligacao for c in voltou.criterios] == ["e", "ou"]
    assert S.Criterio.from_dict({"campo": "a"}).ligacao == "e"      # padrão para regra antiga


def test_a_tela_monta_e_le_o_ou(env, sample_dir):
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env, sample_dir)
    ed = EditorSelecao(S.Selecao(criterios=[crit("descricao", "contem", "v-preview"),
                                            ou("descricao", "contem", "proc")]), repo)
    assert ed.tabela.columnCount() == 4
    assert not ed.tabela.cellWidget(0, 0).isEnabled()              # a primeira não se liga a nada
    assert ed.tabela.cellWidget(1, 0).currentData() == "ou"
    assert [c.ligacao for c in ed.atual().criterios] == ["e", "ou"]


def test_o_motor_nao_traduz_sozinho_mas_aceita_o_tradutor():
    """O motor guarda o texto em português e quem mostra traduz — se o rótulo não passasse pelo
    tradutor, o combo apareceria em português num programa em inglês."""
    regra = S.Selecao(criterios=[crit("modalidade", "igual", "MG"), ou("vista", "igual", "CC")])
    assert "Modalidade" in regra.texto()
    trocado = regra.texto(lambda s: {"Modalidade": "Modality", "é igual a": "is equal to",
                                     "OU então": "OR else"}.get(s, s))
    assert "Modality is equal to “MG”" in trocado and "or else" in trocado
    assert S.Selecao(criterios=[]).texto(lambda s: "VAZIO") == "VAZIO"


def test_a_tela_mostra_os_rotulos_traduzidos(env, monkeypatch):
    from ipe.core import i18n
    from ipe.ui import selecao_dialog as SD
    dlg, repo = _tela(env)
    monkeypatch.setattr(SD, "tr", lambda s: f"[{s}]")
    ed = SD.EditorSelecao(S.Selecao(criterios=[crit("modalidade", "igual", "MG")]), repo)
    assert ed.tabela.cellWidget(0, 1).currentText() == "[Modalidade]"
    assert ed.tabela.cellWidget(0, 2).currentText() == "[é igual a]"
    assert ed.tabela.cellWidget(0, 0).currentText() == "[E também]"


def test_a_previa_quebra_por_grupo_e_denuncia_o_grupo_solto(env, sample_dir):
    """O caso real: “… e descrição contém V-Preview OU descrição contém PROC” — o segundo grupo
    não limita modalidade e alcança `Processed Images` de TC e RM."""
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env, sample_dir)
    solta = S.Selecao(criterios=[crit("modalidade", "igual", "MG"),
                                 crit("descricao", "contem", "mamo"),
                                 ou("descricao", "contem", "a")])     # pega de tudo
    ed = EditorSelecao(solta, repo)
    texto = ed.previa.text()
    assert "Grupo 1" in texto and "Grupo 2" in texto
    assert "grupos ligados por OU" in texto
    assert "Atenção" in texto                       # o grupo solto é denunciado
    assert "#c98b12" in ed.previa.styleSheet()      # e fica em âmbar


def test_previa_sem_ou_nao_fala_em_grupo(env, sample_dir):
    from ipe.ui.selecao_dialog import EditorSelecao
    dlg, repo = _tela(env, sample_dir)
    ed = EditorSelecao(S.Selecao(criterios=[crit("modalidade", "igual", "MG")]), repo)
    assert "A regra:" in ed.previa.text() and "Grupo" not in ed.previa.text()
    assert "Atenção" not in ed.previa.text()
