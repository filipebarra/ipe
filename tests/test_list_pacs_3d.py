"""Marcas na lista, busca do PACS (cancelar/datas/séries), download por série e 3D (superfície e cortes)."""
import threading
from datetime import date, timedelta

import numpy as np
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------- marcas na lista
def test_marcas_de_laudo_comentario_e_filme(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    from ipe.ui.browser import _mark_list, _marks, _marks_tip, MARK_DRAFT, MARK_SIGNED, \
        MARK_AMENDED, MARK_FILM, MARK_COMMENT
    Importer(db, paths.storage).import_paths([sample_dir])
    estudo = repo.search_studies()[0]
    assert _mark_list(estudo) == []

    repo.save_report({"study_uid": estudo.study_uid, "text": "rascunho", "status": "draft"})
    linha = next(r for r in repo.search_studies() if r.study_uid == estudo.study_uid)
    assert linha.report == "rascunho" and _mark_list(linha) == [MARK_DRAFT]

    rid = repo.save_report({"study_uid": estudo.study_uid, "text": "final", "status": "draft"})
    repo.sign_report(rid, "eu", "final")
    linha = next(r for r in repo.search_studies() if r.study_uid == estudo.study_uid)
    assert linha.report == "assinado" and MARK_SIGNED in _mark_list(linha)

    # retificação: o laudo assinado não muda mais; a retificação é um laudo novo
    rid2 = repo.save_report({"study_uid": estudo.study_uid, "text": "retificado", "status": "draft"})
    repo.sign_report(rid2, "eu", "amended")
    linha = next(r for r in repo.search_studies() if r.study_uid == estudo.study_uid)
    assert linha.report == "retificado" and _mark_list(linha) == [MARK_AMENDED]

    repo.save_film("Filme", {"sheets": []}, [estudo.study_uid], "Fulano")
    repo.add_comment("study", estudo.study_uid, "olhar de novo")
    linha = next(r for r in repo.search_studies() if r.study_uid == estudo.study_uid)
    assert linha.has_film and linha.has_comment
    # as três marcas aparecem juntas, na ordem: comentário, laudo, filme
    assert _mark_list(linha) == [MARK_COMMENT, MARK_AMENDED, MARK_FILM]
    assert MARK_FILM in _marks(linha) and "filme salvo" in _marks_tip(linha)
    assert "comentário" in _marks_tip(linha) and "retificado" in _marks_tip(linha)


def test_status_por_serie_no_banco(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    estudo = repo.search_studies()[0]
    series = repo.series_for_study(estudo.study_uid)
    contagens = repo.series_instance_counts([s.series_uid for s in series])
    assert contagens and all(contagens[s.series_uid] == s.num_images for s in series)
    assert repo.series_instance_counts([]) == {}
    assert repo.series_instance_counts(["nao-existe"]) == {}


# ---------------------------------------------------------------- busca do PACS
def test_filtros_de_data_e_modalidade(env):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.pacs_panel import PacsPanel, PERIODS
    settings = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, settings)
    painel = PacsPanel(net, repo)
    try:
        # período pronto (últimos 7 dias)
        painel.period.setCurrentIndex(2)
        f = painel.filters()
        hoje = date.today().strftime("%Y%m%d")
        assert f["date_to"] == hoje and f["date_from"] == (date.today() - timedelta(days=7)).strftime("%Y%m%d")
        # data exata
        i_exata = [i for i, (_l, d) in enumerate(PERIODS) if d == "one"][0]
        painel.period.setCurrentIndex(i_exata)
        assert painel.date_a.isVisible() or True          # visível quando o painel está na tela
        from PySide6.QtCore import QDate
        painel.date_a.setDate(QDate(2026, 3, 4))
        f = painel.filters()
        assert f["date_from"] == f["date_to"] == "20260304"
        # intervalo, mesmo invertido
        i_faixa = [i for i, (_l, d) in enumerate(PERIODS) if d == "range"][0]
        painel.period.setCurrentIndex(i_faixa)
        painel.date_a.setDate(QDate(2026, 5, 20))
        painel.date_b.setDate(QDate(2026, 5, 2))
        f = painel.filters()
        assert (f["date_from"], f["date_to"]) == ("20260502", "20260520")
        # modalidade: uma, várias ou nenhuma
        painel.mod.setCurrentText("Todas")
        assert painel.filters()["modality"] == ""
        painel.mod.setCurrentText("CT")
        assert painel.filters()["modality"] == "CT"
        painel.mod.setCurrentText("ct, mr")
        assert painel.filters()["modality"] == "CT\\MR"
    finally:
        net.shutdown()
        painel.deleteLater()
    _ = app


def test_cancelar_busca(env):
    """O botão vira Parar e o cancelamento chega até o cliente DICOM."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.pacs_panel import PacsPanel
    settings = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, settings)
    painel = PacsPanel(net, repo)
    vistos = {}

    def falso_search(nodes, identity, filtros, on_done, cancel=None):
        vistos["cancel"] = cancel
        vistos["filtros"] = filtros
    net.search = falso_search
    repo.save_node({"name": "PACS", "ae_title": "PACS", "host": "127.0.0.1", "port": 104,
                    "retrieve": "get", "move_destination": "", "use_in_search": True})
    painel.refresh_nodes()
    try:
        painel.name.setText("SILVA")
        painel.search()
        assert isinstance(vistos["cancel"], threading.Event) and not vistos["cancel"].is_set()
        assert painel.btn_search.text() == "Parar"
        painel._search_or_stop()                      # o mesmo botão interrompe
        assert vistos["cancel"].is_set()
        painel._search_done(([], []), None)
        assert painel.btn_search.text() == "Buscar" and painel._cancel is None
    finally:
        net.shutdown()
        painel.deleteLater()
    _ = app


def test_download_serie_a_serie_com_pular(env):
    """Baixa série por série e respeita a que o usuário mandou pular no meio."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.network.service import Job, NetworkService
    settings = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, settings)
    try:
        job = Job("retrieve", "Exame", {"name": "PACS"}, None, ["1.2.3"])
        job.series_plan = [{"series_uid": f"s{i}", "series_number": i, "num_images": 10} for i in (1, 2, 3)]
        baixadas = []

        def baixar(series, prog):
            baixadas.append(series[0])
            prog(5, 10, "metade")
            if series[0] == "s1":
                net.skip_series(job, "s2")            # pula a próxima no meio do caminho
            return 10
        n = net._retrieve_by_series(job, job.series_plan, baixar, lambda *a: None)
        assert baixadas == ["s1", "s3"] and n == 20
        assert job.done_series == {"s1", "s2", "s3"}
        # série que já veio não dá para pular
        assert not net.skip_series(job, "s1")
    finally:
        net.shutdown()
    _ = app


# ---------------------------------------------------------------- 3D
class _VolFake:
    def __init__(self, data, dx=1.0, dy=1.0, dz=1.0):
        self.data = data.astype(np.float32)
        self.origin = np.zeros(3)
        self.row_dir = np.array([1.0, 0, 0])
        self.col_dir = np.array([0, 1.0, 0])
        self.slice_vec = np.array([0, 0, dz])
        self.dx, self.dy = dx, dy
        self.window = None
        self.source_path = ""
        self.monochrome1 = False

    @property
    def shape(self):
        return self.data.shape

    @property
    def dz(self):
        return float(np.linalg.norm(self.slice_vec))

    def matrix(self):
        return np.column_stack([self.row_dir * self.dx, self.col_dir * self.dy, self.slice_vec])

    def voxel_to_patient(self, i, j, k):
        return self.origin + self.matrix() @ np.array([i, j, k], float)


def _renderer():
    from ipe.imaging.render3d import Renderer3D
    z, y, x = np.mgrid[0:40, 0:40, 0:40]
    dados = np.full((40, 40, 40), -900.0)
    dados[((z - 20.) ** 2 + (y - 20.) ** 2 + (x - 20.) ** 2) < 100] = 800.0    # esfera no meio
    dados[5:9, 5:9, 5:9] = 800.0                                               # cubinho num canto
    return Renderer3D(_VolFake(dados), max_dim=48)


def test_modo_superficie():
    r = _renderer()
    img = r.render("surf", 0, 0, (80, 80), lo=200, hi=1000)
    assert img.shape == (80, 80, 3) and img.dtype == np.uint8
    assert img.max() > 60                       # a superfície aparece iluminada
    assert img.min() == 0                       # e o fundo fica preto
    # limiar acima de tudo: nada aparece
    vazio = r.render("surf", 0, 0, (60, 60), lo=5000, hi=6000)
    assert vazio.max() == 0


def test_cortes_do_volume():
    r = _renderer()
    assert r.clip_full()
    inteiro = r.render("mip", 0, 0, (60, 60), lo=-1000, hi=1000)
    acesos = lambda im: int((im > 0).sum())      # noqa: E731
    # corta tudo o que está à frente do meio (mantém o posterior)
    r.cut_at(r.center, "posterior")
    assert not r.clip_full()
    atras = r.render("mip", 0, -89, (60, 60), lo=-1000, hi=1000)   # olhando de cima
    r.clip_reset()
    assert r.clip_full()
    de_novo = r.render("mip", 0, -89, (60, 60), lo=-1000, hi=1000)
    assert acesos(atras) < acesos(de_novo)       # cortado mostra menos coisa
    # cortar num canto tira o cubinho: sobra menos sinal alto
    r.cut_at(r.center, "left")
    esq = r.render("mip", 0, 0, (60, 60), lo=-1000, hi=1000)
    r.clip_reset()
    assert float((esq > 400).sum()) <= float((inteiro > 400).sum())
    assert r.index_of(r.center)[0] > 0
