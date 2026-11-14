"""Bancos e servidor na janela principal (mixin da MainWindow, separado do `main_window.py` na 0.100.42).

Aqui ficam: os locais (banco deste computador, bancos pessoais, servidor central), trocar de local, e levar e trazer
exames entre o servidor e este computador.

Os métodos continuam sendo da MainWindow (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QMessageBox,
    QProgressDialog,
)

from ipe import APP_NAME, NOT_FOR_DIAGNOSIS, __version__
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer

log = logging.getLogger("ipe.ui.main_window")      # o mesmo registro de antes da separação


class BancosMixin:
    """BancosMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ------------------------------------------------------------ locais (bancos)
    def _update_title(self) -> None:
        loc = getattr(self, "location", None)
        extra = "" if loc is None or loc.is_default else f" — {loc.name}"
        self.setWindowTitle(f"{APP_NAME} {__version__}{extra} — {NOT_FOR_DIAGNOSIS}")

    def switch_location(self, loc_id: str) -> bool:
        """Troca o local ativo: a lista passa a ser a daquela pasta (banco, listas, laudos e medidas)."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or loc.id == self.location.id:
            return False
        if loc.is_central and self._central is None:
            return False
        if not loc.online():
            QMessageBox.information(self, "Local fora do ar",
                                    f"A pasta não está acessível agora:\n{loc.path}")
            self.locations.rebuild()
            return False
        abertos = self.all_viewer_tabs()
        if abertos:
            r = QMessageBox.question(
                self, "Trocar de local",
                f"Usar “{loc.name}”?\n\nOs {len(abertos)} exame(s) abertos serão fechados "
                "(os exames continuam guardados no local de origem).")
            if r != QMessageBox.Yes:
                self.locations.rebuild()
                return False
        for w in list(self.detached):
            w.close()
        for i in range(self.tabs.count() - 1, 0, -1):
            self.tabs.removeTab(i)
        self.cache.clear()
        antigo = self.db
        if loc.is_central:                      # 0.99.28: de volta ao servidor do grupo
            cdb, crepo, cstorage = self._central
            self.location = loc
            LOC.set_current(self.settings, loc.id)
            self.settings.save()
            self._use_database(cdb, cstorage, Path(cstorage).parent / "Lixeira", repo=crepo)
            self.statusBar().showMessage(f"Local: {loc.name}", 6000)
            if antigo is not None and antigo is not cdb:
                antigo.close()
            return True
        try:
            db = Database(self.paths.database if loc.is_default else loc.database)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Local", f"Não foi possível abrir o banco do local:\n{e}")
            return False
        self.location = loc
        LOC.set_current(self.settings, loc.id)
        self.settings.save()
        self._use_database(db, self.paths.storage if loc.is_default else loc.storage,
                           (self.paths.data if loc.is_default else loc.path) / "Lixeira")
        self.statusBar().showMessage(f"Local: {loc.name}", 6000)
        if antigo is not None and antigo is not db and (self._central is None or antigo is not self._central[0]):
            antigo.close()
        return True

    def _use_database(self, db, storage, trash_root, repo=None) -> None:
        """Passa a usar este banco: religa a lista, a rede, o PACS, a automação e a sincronização."""
        self.db = db
        self.repo = repo if repo is not None else Repository(db)
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.browser.set_source(self.repo, self.storage)
        self.net.set_source(self.db, self.repo, self.storage)
        self.pacs.repo = self.repo
        self.pacs.refresh_nodes()
        self.auto.set_source(self.repo, self.db, Path(trash_root))
        self.sync_hub.repo = self.repo
        self.locations.set_repo(self.repo)
        self._refresh_other_locations()
        self._update_title()
        self._update_status()

    def move_default_database(self) -> None:
        """Muda a pasta do banco deste computador (com a opção de levar os arquivos junto)."""
        from ipe.core import locations as LOC
        from ipe.core.config import AppPaths, default_data_dir
        from ipe.ui.locations_panel import choose_folder
        atual = Path(self.paths.data)
        nova = choose_folder(self, self.settings, "Pasta do banco deste computador")
        if nova is None or nova.resolve() == atual.resolve():
            return
        if atual.resolve() in nova.resolve().parents:
            QMessageBox.warning(self, "Pasta do banco",
                                "Escolha uma pasta fora da pasta atual do banco.")
            return
        for outra in LOC.all_locations(self.settings, self.paths):
            if not outra.is_default and outra.online() and outra.path.resolve() == nova.resolve():
                QMessageBox.warning(self, "Pasta do banco",
                                    f"Essa pasta já é o local “{outra.name}”.")
                return
        itens = [d for d in ("postgres", "dicomviewer.sqlite", "dicomviewer.sqlite.migrado", "Storage", "Lixeira") if (atual / d).exists()]
        mb = sum(f.stat().st_size for d in itens for f in [atual / d] + list((atual / d).rglob("*"))
                 if f.is_file()) / 1024 / 1024
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Pasta do banco")
        caixa.setText(f"Usar esta pasta para o banco deste computador?\n\n{nova}")
        caixa.setInformativeText(
            f"Pasta de agora: {atual}\nBanco e arquivos: {mb:.0f} MB.\n\n"
            "“Mover” leva o banco e os arquivos para a pasta nova. "
            "“Só apontar” deixa tudo onde está e começa do que houver na pasta nova.")
        b_mover = caixa.addButton("Mover os arquivos", QMessageBox.AcceptRole)
        caixa.addButton("Só apontar", QMessageBox.AcceptRole)
        b_cancel = caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is b_cancel:
            return
        mover = caixa.clickedButton() is b_mover
        if mover:
            # 0.99.75: com o programa aberto o Windows não deixa mover o banco (WinError 32: os serviços de fundo
            # o mantêm aberto). A mudança fica marcada e é feita na próxima abertura, antes de abrir o banco.
            from ipe.core import mover_banco as MB
            conflito = [i for i in MB.itens_de(atual) if (nova / i).exists()]
            if conflito:
                QMessageBox.warning(self, "Pasta do banco",
                                    f"A pasta nova já tem {', '.join(conflito)}. Escolha uma pasta vazia, ou use "
                                    f"Só apontar para usar o banco que já está lá.")
                return
            MB.marcar(self.settings, atual, nova)
            r = QMessageBox.question(
                self, "Pasta do banco",
                "O banco vai ser movido na próxima vez que o programa abrir, antes de tudo (com ele aberto o "
                "Windows não deixa). Se algo falhar, nada muda.\n\nFechar o programa agora?")
            if r == QMessageBox.Yes:
                QTimer.singleShot(0, self.quit_app)
            return
        if self.all_viewer_tabs():
            for i in range(self.tabs.count() - 1, 0, -1):
                self.tabs.removeTab(i)
        self.cache.clear()
        antigo = self.db
        antigo.close()
        nova.mkdir(parents=True, exist_ok=True)
        self.settings.set("data_dir", "" if nova.resolve() == Path(default_data_dir()).resolve()
                          else str(nova))
        self.settings.save()
        self.paths = AppPaths(nova, self.paths.config, self.paths.logs).ensure()
        from ipe.core.config import publicar_pasta_do_banco
        publicar_pasta_do_banco(self.paths)
        self.location = LOC.default_location(self.paths)
        self.locations.paths = self.paths
        self._use_database(Database(self.paths.database), self.paths.storage,
                           self.paths.data / "Lixeira")
        self.locations.rebuild()
        self.statusBar().showMessage(f"Banco deste computador: {nova}", 12000)
        QMessageBox.information(
            self, "Pasta do banco",
            f"O banco deste computador passou a ser:\n{nova}\n\n"
            + ("Os arquivos foram movidos." if mover else
               "Os arquivos antigos continuam em:\n" + str(atual)))

    def _refresh_other_locations(self) -> None:
        """Os outros locais que aparecem no menu "Copiar para o local"."""
        from ipe.core import locations as LOC
        self.browser.other_locations = [
            (loc.id, loc.name) for loc in LOC.all_locations(self.settings, self.paths)
            if loc.id != self.location.id and loc.online()]

    def copy_studies_to_location(self, study_uids: list[str], loc_id: str) -> None:
        """Copia exames para outro local. Os arquivos de origem não são tocados."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or not loc.online():
            QMessageBox.information(self, "Local", "O local de destino não está acessível agora.")
            return
        if loc.is_central:                       # 0.99.28: daqui para o servidor do grupo
            self.enviar_ao_servidor(study_uids)
            return
        if self.location.is_central:             # 0.99.28: do servidor para um banco deste computador
            self.trazer_do_servidor(study_uids, loc)
            return
        arquivos: list[Path] = []
        for uid in study_uids:
            arquivos += [Path(f) for f in self.repo.files_for_study(uid)]
        arquivos = [f for f in arquivos if f.exists()]
        if not arquivos:
            QMessageBox.information(self, "Copiar para o local", "Nenhum arquivo encontrado.")
            return
        mb = sum(f.stat().st_size for f in arquivos) / 1024 / 1024
        r = QMessageBox.question(
            self, "Copiar para o local",
            f"Copiar {len(study_uids)} exame(s) — {len(arquivos)} imagem(ns), {mb:.0f} MB — "
            f"para “{loc.name}”?\n\nOs arquivos de origem não são alterados.")
        if r != QMessageBox.Yes:
            return
        dlg = QProgressDialog(f"Copiando para {loc.name}…", "Cancelar", 0, len(arquivos), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        alvo = None
        try:
            LOC.prepare(loc.path, loc.name)
            alvo = Database(loc.database)
            imp = Importer(alvo, loc.storage, copy_to_storage=True)
            res = imp.import_paths(arquivos, progress=lambda i, n, _t: (dlg.setValue(i),
                                                                       QApplication.processEvents()))
        except Exception as e:  # noqa: BLE001
            log.exception("copiar para o local")
            QMessageBox.warning(self, "Copiar para o local", f"Não foi possível copiar:\n{e}")
            return
        finally:
            dlg.close()
            if alvo is not None:
                alvo.close()
        self.statusBar().showMessage(
            f"{res.added} imagem(ns) copiada(s) para “{loc.name}”; {res.duplicates} já existiam.", 10000)

    # ------------------------------------------------------------ servidor ⇄ este computador (0.99.28)
    def _em_segundo_plano(self, titulo: str, fn):
        """Roda fn(progress, cancel) numa linha à parte, com barra de progresso; devolve o resultado."""
        import threading

        from PySide6.QtCore import QObject, Signal as _Sig

        class _B(QObject):
            prog = _Sig(int, int, str)
        b = _B()
        dlg = QProgressDialog(titulo + "…", "Cancelar", 0, 0, self)
        dlg.setWindowTitle(titulo)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        parar = threading.Event()
        dlg.canceled.connect(parar.set)
        b.prog.connect(lambda i, n, _t: (dlg.setMaximum(n), dlg.setValue(i),
                                         dlg.setLabelText(f"{titulo}… exame {i + 1} de {n}")))
        estado: dict = {}

        def trabalho():
            try:
                estado["res"] = fn(b.prog.emit, parar.is_set)
            except Exception as e:  # noqa: BLE001
                log.exception(titulo)
                estado["res"] = e
        th = threading.Thread(target=trabalho, daemon=True)
        th.start()
        while th.is_alive():
            QApplication.processEvents()
            th.join(0.03)
        QApplication.processEvents()
        dlg.close()
        return estado.get("res")

    def _fim_da_transferencia(self, titulo: str, res, verbo: str) -> None:
        if isinstance(res, Exception) or res is None:
            QMessageBox.warning(self, titulo, f"Não foi possível terminar:\n{res}")
            return
        texto = res.resumo(verbo)
        self.statusBar().showMessage(texto, 15000)
        if res.recusados or res.erros:
            QMessageBox.information(self, titulo, texto)
        self.browser.refresh()
        self.locations.rebuild()

    def trazer_do_servidor(self, study_uids: list[str], loc=None, mover: bool = False):
        """Do servidor do grupo para o banco deste computador (ou outro local), no meu banco pessoal."""
        from ipe.auth import session as S
        from ipe.central import transferir as T
        from ipe.core import locations as LOC
        if self._central is None:
            return None
        loc = loc or LOC.default_location(self.paths)
        cliente = self._central[1]
        destino = Database(self.paths.database if loc.is_default else loc.database)
        storage = self.paths.storage if loc.is_default else loc.storage
        titulo = "Mover para este computador" if mover else "Copiar para este computador"
        try:
            res = self._em_segundo_plano(titulo, lambda prog, cancel: T.trazer(
                cliente, list(study_uids), destino, storage, S.get().username, mover=mover,
                progress=prog, cancel=cancel))
        finally:
            destino.close()
        try:
            S.audit(self.repo, "trouxe_do_servidor", f"{getattr(res, 'exames', 0)} exame(s) para {loc.name}"
                    + (" (tirados do servidor)" if mover else ""))
        except Exception:  # noqa: BLE001
            pass
        self._fim_da_transferencia(titulo, res, "no " + loc.name)
        return res

    def _perguntar_banco_do_envio(self, n: int, como_estao: bool = False):
        """Compartilhado ou o meu banco no servidor? None = cancelou. `como_estao` (administrador):
        cada exame no banco em que estava aqui."""
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Enviar ao servidor central")
        caixa.setText(f"Enviar {n} exame(s) ao servidor do grupo, com laudos, medidas e anotações.\n\n"
                      "Em qual banco do servidor eles ficam?")
        b_meu = caixa.addButton("No meu banco (pessoal)", QMessageBox.AcceptRole)
        b_comp = caixa.addButton("No compartilhado", QMessageBox.AcceptRole)
        b_igual = caixa.addButton("Como estão aqui", QMessageBox.AcceptRole) if como_estao else None
        caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.exec()
        if b_igual is not None and caixa.clickedButton() is b_igual:
            return "como_estao"
        if caixa.clickedButton() is b_meu:
            return True
        if caixa.clickedButton() is b_comp:
            return False
        return None

    def enviar_ao_servidor(self, study_uids: list[str], origem=None, meu: bool | None = None):
        """De um banco deste computador (ou do local aberto) para o servidor do grupo."""
        from ipe.auth import session as S
        from ipe.central import transferir as T
        if self._central is None:
            return None
        origem = origem or self.repo
        if getattr(origem, "remote", False):
            return None
        if meu is None:
            meu = self._perguntar_banco_do_envio(len(study_uids))
            if meu is None:
                return None
        client = self._central[1].client
        res = self._em_segundo_plano("Enviar ao servidor central", lambda prog, cancel: T.enviar(
            client, origem, list(study_uids), meu, S.get().username, progress=prog, cancel=cancel))
        try:
            S.audit(self._central[1], "enviou_ao_servidor", f"{getattr(res, 'exames', 0)} exame(s) para o "
                    + ("banco de cada dono" if meu == "como_estao" else "banco pessoal" if meu else "compartilhado"))
        except Exception:  # noqa: BLE001
            pass
        self._fim_da_transferencia("Enviar ao servidor central", res, "no servidor")
        return res

    def enviar_local_ao_servidor(self, loc_id: str):
        """Locais ▸ botão direito ▸ Enviar este banco ao servidor central (migração do banco local)."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or loc.is_central or self._central is None or not loc.online():
            return None
        db = self.db if loc.id == self.location.id else Database(self.paths.database if loc.is_default
                                                                 else loc.database)
        try:
            from ipe.auth import visibilidade as V
            repo = Repository(db)
            v = V.visao_atual()
            admin = v is None or v.admin            # o administrador leva o banco inteiro; os outros, o que veem
            uids = [r.study_uid for r in repo.search_studies(limit=10_000_000,
                                                             banco="todos" if admin else "visivel")]
            if not uids:
                QMessageBox.information(self, "Enviar ao servidor central", f"“{loc.name}” não tem exames.")
                return None
            meu = self._perguntar_banco_do_envio(len(uids), como_estao=admin)
            if meu is None:
                return None
            return self.enviar_ao_servidor(uids, origem=repo, meu=meu)
        finally:
            if db is not self.db:
                db.close()

    def _novos_para_este_computador(self, uids) -> set:
        """Importados no modo cliente com "o meu banco neste computador": do cache para o banco daqui."""
        from ipe.auth import session as S
        from ipe.central import transferir as T
        destino = Database(self.paths.database)
        try:
            res = T.do_cache_para_este_computador(self._central[1], sorted(uids), destino, self.paths.storage,
                                                  S.get().username)
        finally:
            destino.close()
        if res.erros:
            log.warning("importados para este computador: %s", res.erros)
        return set(res.feitos)

    def acoes_do_servidor(self, sub, rows) -> None:
        """Botão direito ▸ Banco, no modo cliente: levar exames entre o servidor e este computador."""
        from ipe.auth import visibilidade as V
        if self._central is None or not rows:
            return
        uids = [r.study_uid for r in rows]
        sub.addSeparator()
        if self.location.is_central:
            sub.addAction("Copiar para este computador", lambda: self.trazer_do_servidor(uids))
            v = V.visao_atual()
            a = sub.addAction("Mover para este computador (sai do servidor)",
                              lambda: self.trazer_do_servidor(uids, mover=True))
            a.setEnabled(v is None or v.admin or all((r.dono or "").lower() == v.usuario.lower() for r in rows))
            a.setToolTip("Para o banco pessoal que funciona sem rede. Só o dono (ou o administrador) tira o "
                         "exame do servidor.")
        else:
            sub.addAction("Enviar ao servidor central…", lambda: self.enviar_ao_servidor(uids))

    def add_location(self) -> None:
        """Acrescenta uma pasta como local: HD externo, pasta de rede ou outra pasta do PC."""
        from ipe.core import locations as LOC
        from ipe.ui.locations_panel import choose_folder
        pasta = choose_folder(self, self.settings)
        if pasta is None:
            return
        if pasta.resolve() == Path(self.paths.data).resolve():
            QMessageBox.information(self, "Local", "Essa já é a pasta do banco deste computador.")
            return
        usada = LOC.looks_used(pasta)
        nome = LOC.suggest_name(pasta)
        nome, ok = QInputDialog.getText(
            self, "Abrir local" if usada else "Local novo",
            ("A pasta já tem um local montado; ele será aberto como está.\n\nNome:" if usada else
             "A pasta será usada como local. Os arquivos que já estiverem lá são apenas indexados — "
             "nada é copiado, movido ou alterado.\n\nNome:"), text=nome)
        if not ok or not nome.strip():
            return
        loc = LOC.add(self.settings, pasta, nome.strip())
        self.settings.save()
        self.locations.rebuild()
        self._refresh_other_locations()
        if not self.switch_location(loc.id):
            return
        if not usada:
            self.rescan_location(loc.id, primeira=True)

    def rescan_location(self, loc_id: str, primeira: bool = False) -> None:
        """Procura exames novos na pasta do local e indexa sem copiar (os originais ficam onde estão)."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or not loc.online():
            return
        if not primeira:
            r = QMessageBox.question(
                self, "Procurar exames",
                f"Procurar exames novos em:\n{loc.path}\n\n"
                "Os arquivos continuam onde estão — o programa só acrescenta ao índice.")
            if r != QMessageBox.Yes:
                return
        if loc.id != self.location.id and not self.switch_location(loc.id):
            return
        self.start_import([loc.path], reference=True)

    def open_pacs_node(self, node_id) -> None:
        """Abre a janela do PACS já com aquele nó escolhido."""
        self.show_pacs()
        if node_id is not None:
            i = self.pacs.node.findData(node_id)
            if i >= 0:
                self.pacs.node.setCurrentIndex(i)

    def open_network_settings(self) -> None:
        from ipe.auth import session as S
        if not S.can("configure"):
            # 0.99.26: quem não configura o computador ainda cadastra os nós e identidades dele
            from ipe.auth import visibilidade as V
            if V.visao_atual() is not None and S.can("query"):
                return self.abrir_meus_nos()
            S.require("configure", self)
            return
        from ipe.ui.network_dialog import NetworkDialog
        before = (dict(self.settings.get("dicom", {}) or {}),
                  dict(self.settings.get("print_scp", {}) or {}))
        dlg = NetworkDialog(self.settings, self.repo, self.net, self, ao_mudar=self._nos_mudaram)
        dlg.exec()
        # nós e identidades são gravados na hora; configurações locais só com OK
        if (dict(self.settings.get("dicom", {}) or {}),
                dict(self.settings.get("print_scp", {}) or {})) != before:
            self.start_services()
        else:
            self.net.refresh_acl()
        self.pacs.refresh_nodes()

    def abrir_meus_nos(self):
        """Nós DICOM e identidades **pessoais** (quem não tem a permissão de configurar)."""
        from ipe.ui.network_dialog import NetworkDialog
        dlg = NetworkDialog(self.settings, self.repo, self.net, self, ao_mudar=self._nos_mudaram, so_pessoal=True)
        dlg.exec()
        self.net.refresh_acl()
        self.pacs.refresh_nodes()
        return dlg

    def _nos_mudaram(self) -> None:
        """Um nó foi salvo ou excluído (na hora, sem esperar fechar a janela da rede)."""
        self.pacs.refresh_nodes()
        g = getattr(self, "gestao_window", None)
        if g is not None:
            g.recarregar_nos()

    def _register_url(self) -> None:
        from ipe.network.external import register_url_scheme
        try:
            QMessageBox.information(self, "Link ipe://", register_url_scheme(self.settings))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Link ipe://", f"Não foi possível registrar: {e}")

    def send_studies(self, study_uids: list, node_id: int, identity_id,
                     series_uids: list | None = None) -> None:
        """Põe os estudos na fila de envio; `series_uids`: só estas séries (um estudo só)."""
        from ipe.auth import session as S
        if not S.require("send", self):
            return
        node = self.repo.node(node_id)
        if node is None:
            return
        ident = self.repo.identity(identity_id)
        for uid in study_uids:
            info = self.repo.study_info(uid) or {}
            label = f"{info.get('patient_name', '')} — {info.get('description', '')}"
            if series_uids:
                label += f" ({len(series_uids)} série(s))"
            S.audit(self.repo, "enviar", f"{node['name']}: {label}", study_uid=uid)
            try:
                self.net.send(node, ident, [uid], label, series_uids or None)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Enviar", str(e))
                return
        if series_uids:
            msg = f"{len(series_uids)} série(s) na fila de envio para {node['name']}. Acompanhe na aba PACS."
        else:
            msg = f"{len(study_uids)} estudo(s) na fila de envio para {node['name']}. Acompanhe na aba PACS."
        self.statusBar().showMessage(msg, 8000)

    def _on_received(self, result, origin: str) -> None:
        self._refresh_timer.start()
        self._note_auto_film(getattr(result, "studies", set()) or set())
        from ipe.central.client_repo import upload_if_client
        studies = set(getattr(result, "studies", set()) or set())
        for uid in studies:
            upload_if_client(self.repo, uid)
        if origin == "received" and result.added:
            self.statusBar().showMessage(f"Recebidas {result.added} imagem(ns) pela rede.", 8000)
        if result.added:
            self._stream_progress(studies)

    def _on_job_changed(self, job) -> None:
        """Mudou alguma coisa no download: barra de estado e a tira das séries que faltam."""
        self._update_net_label()
        if getattr(job, "kind", "") != "retrieve":
            return
        abertos = set(getattr(job, "study_uids", []) or [])
        for tab in self.all_viewer_tabs():
            if abertos & set(tab.study_order):
                tab._fill_strip()
