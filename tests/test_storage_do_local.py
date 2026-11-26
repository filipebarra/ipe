"""0.100.122: a automação (IAs) grava na pasta de arquivos do local em uso, não na do computador."""
from pathlib import Path

from ipe.automation.engine import AutomationEngine
from ipe.core.config import Settings


class _Sinal:
    def connect(self, *a):
        pass


class _Rede:
    received = _Sinal()
    job_finished = _Sinal()


def test_engine_usa_a_pasta_do_local(env, tmp_path):
    paths, db, repo = env
    st = Settings(paths.settings_file)
    hd = tmp_path / "hd" / "Storage"
    eng = AutomationEngine(repo, db, _Rede(), st, paths, storage=hd)
    assert eng.storage == hd                                   # o do local, não o do computador
    eng2 = AutomationEngine(repo, db, _Rede(), st, paths)
    assert eng2.storage == Path(paths.storage)                 # sem local escolhido: o do computador
    outro = tmp_path / "outro" / "Storage"
    eng2.set_source(repo, db, None, outro)
    assert eng2.storage == outro                               # trocar de local troca a pasta junto
    eng2.set_source(repo, db, None)
    assert eng2.storage == outro                               # sem pasta nova: fica a que estava


def test_nenhuma_ia_grava_em_paths_storage():
    """Quem grava resultado de IA usa self.storage; paths.storage só serve de valor inicial."""
    src = Path(__file__).resolve().parents[1] / "src" / "ipe" / "automation" / "engine.py"
    assert src.read_text(encoding="utf-8").count("self.paths.storage") == 0


def test_cad_ia_rotulo_de_cada_ferramenta_e_o_dela(env):
    """Cada ferramenta de CAD/IA mostra o 'automático' da própria caixa (a do alinhamento da dinâmica deslocava as seguintes)."""
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    c = PreferencesDialog(Settings(paths.settings_file), pai).cad_ia
    nomes = [c.l_ferramentas.item(k).text().split("\n")[0] for k in range(c.l_ferramentas.count())]
    k = nomes.index("Dinâmica da mama: alinhar as fases")
    antes = [c.l_ferramentas.item(j).text() for j in range(len(nomes))]
    c.c_dce_auto.setChecked(not c.c_dce_auto.isChecked())
    depois = [c.l_ferramentas.item(j).text() for j in range(len(nomes))]
    assert [j for j in range(len(nomes)) if antes[j] != depois[j]] == [k]      # só a do alinhamento mudou


def test_pasta_temporaria_curta_so_no_windows():
    import os

    from ipe.ai import instalar_modelos_extras as I
    if os.name != "nt":
        assert I.pasta_temporaria_curta() is None
    else:
        assert len(I.pasta_temporaria_curta()) < 20
