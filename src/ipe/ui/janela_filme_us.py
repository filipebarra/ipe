"""Filme automático do ultrassom (mixin da MainWindow, separado do `main_window.py` na 0.100.42).

Aqui fica a montagem do filme quando as imagens de um exame param de chegar.

Os métodos continuam sendo da MainWindow (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtWidgets import (
    QMenu, QMessageBox,
)

from ipe import APP_NAME

log = logging.getLogger("ipe.ui.main_window")      # o mesmo registro de antes da separação


class FilmeUSMixin:
    """FilmeUSMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ------------------------------------------------------------ filme automático (US)
    def _note_auto_film(self, studies) -> None:
        """Marca os exames que acabaram de receber imagens; o filme é montado quando pararem de chegar."""
        from ipe.printing.auto_film import alguma_ligada
        if not studies or not alguma_ligada(self.settings):
            return
        # o que chegou pela porta da impressão já vira filme lá (_on_print_images)
        studies = set(studies) - set(getattr(self.net, "print_port_studies", set()) or set())
        import time
        for uid in studies:
            self._auto_film_wait[uid] = time.monotonic()
        if not self._auto_film_timer.isActive():
            self._auto_film_timer.start()

    def _run_auto_film(self) -> None:
        """Monta o filme dos exames que estão quietos há alguns segundos (terminaram de chegar)."""
        import time
        from ipe.printing.auto_film import montar_para_estudo
        agora = time.monotonic()
        from ipe import modules as MOD
        if not MOD.ligado(self.settings, "impressao"):
            self._auto_film_wait.clear()
            self._auto_film_timer.stop()
            return
        prontos = [uid for uid, quando in self._auto_film_wait.items() if agora - quando >= 15]
        for uid in prontos:
            self._auto_film_wait.pop(uid, None)
            remetente = (getattr(getattr(self.net, "sink", None), "remetentes", {}) or {}).get(uid)
            try:
                film_id, cfg = montar_para_estudo(self.repo, self.settings, uid, remetente)
            except Exception:  # noqa: BLE001
                log.exception("Falha ao montar o filme automático")
                continue
            if film_id is None:
                continue
            info = self.repo.study_info(uid) or {}
            self.show_notification("Filme montado sozinho",
                                   f"{info.get('patient_name', '')} — {info.get('description', '')}".strip(" —"))
            if self._prints is not None:
                self._prints.refresh()
            if cfg.destination:
                self._send_film(film_id, cfg.destination, cfg.template)
        if not self._auto_film_wait:
            self._auto_film_timer.stop()

    def _send_film(self, film_id: int, destino: str, modelo: str = "") -> None:
        from ipe.printing.dispatch import find_destination
        dest = find_destination(self.settings, destino)
        if dest is None:
            self.statusBar().showMessage(f"Destino “{destino}” não existe mais; o filme ficou na lista.",
                                         8000)
            return
        aba = self.show_prints()
        linha = next((r for r in aba.rows if r["kind"] == "film" and r["id"] == film_id), None)
        if linha is not None:
            aba.send_rows([linha], dest, avisar=False, template=modelo, how="regra")

    def _stream_progress(self, studies: set) -> None:
        """Exame baixando com “abrir enquanto baixa”: abre no primeiro lote e vai acrescentando o resto."""
        for job in self.net.active_jobs():
            if job.kind != "retrieve" or not job.stream:
                continue
            uid = job.study_uids[0] if job.study_uids else ""
            if uid not in studies:
                continue
            if not job.opened and self.repo.study_info(uid):
                job.opened = True
                self.statusBar().showMessage(f"Abrindo enquanto baixa: {job.label}", 8000)
                self.open_study(uid)
        for uid in studies:
            for tab in self.all_viewer_tabs():
                if uid in tab.study_order:
                    tab.rescan(uid)

    def _on_job_finished(self, job) -> None:
        self.browser.refresh()
        if job.status == "error":
            self.statusBar().showMessage(f"Falha em “{job.label}”: {job.message}", 15000)
        elif job.status == "done":
            self.statusBar().showMessage(f"Concluído: {job.label} — {job.message}", 8000)
            if job.kind == "retrieve":
                from ipe.central.client_repo import upload_if_client
                aqui = self._baixados_para_este_computador(job)
                for uid in job.study_uids:
                    if uid not in aqui:
                        upload_if_client(self.repo, uid)
            if job.kind == "retrieve":
                self._learn_network(job)
                for uid in job.study_uids:
                    for tab in self.all_viewer_tabs():
                        if uid in tab.study_order:
                            tab.rescan(uid)
            if job.kind == "retrieve" and job.open_after and not job.opened \
                    and self.repo.study_info(job.study_uids[0]):
                # O exame que o RIS mandou baixar abre do mesmo jeito que o que já estava no
                # banco: no modo "só visualizador", sem passar pelo banco de dados.
                self.abrir_exame_do_pedido(job.study_uids[0])
        self._update_net_label()

    def _baixados_para_este_computador(self, job) -> set:
        """0.99.36, modo cliente com "o meu banco neste computador": o exame **novo** baixado do PACS não
        sobe ao servidor — vai para o banco deste computador, como a importação (0.99.28). Exame aberto
        numa aba só muda de lugar quando a aba fechar (os arquivos estão em uso pelo visualizador)."""
        from ipe.db import banco as B
        if not getattr(job, "novo", False) or self._central is None or self.repo is not self._central[1] \
                or not B.fica_neste_computador(self.settings):
            return set()
        uids = set(job.study_uids)
        abertos = {u for u in uids for t in self.all_viewer_tabs() if u in getattr(t, "study_order", [])}
        if job.open_after and not job.opened:
            abertos |= uids                      # vai abrir agora
        pend = self.__dict__.setdefault("_pendentes_este_computador", set())
        pend |= abertos
        feitos = self._novos_para_este_computador(uids - abertos) if uids - abertos else set()
        if feitos:
            self.browser.refresh()
            self.statusBar().showMessage(f"{len(feitos)} exame(s) baixado(s) para o meu banco deste computador.",
                                         10000)
        return feitos | abertos

    def _levar_pendentes_para_este_computador(self) -> None:
        """Depois de fechar uma aba: os baixados que esperavam a aba fechar vão para este computador."""
        pend = self.__dict__.get("_pendentes_este_computador") or set()
        if not pend or self._central is None:
            return
        abertos = {u for u in pend for t in self.all_viewer_tabs() if u in getattr(t, "study_order", [])}
        prontos = pend - abertos
        if not prontos:
            return
        pend -= prontos
        try:
            self._novos_para_este_computador(prontos)
        except Exception:  # noqa: BLE001
            log.exception("levar para este computador")
        self.browser.refresh()

    def _learn_network(self, job) -> None:
        """Aprende a velocidade do nó com o download que acabou (MB/s e MB por imagem)."""
        try:
            from ipe.network.probe import learn
            secs = max(0.5, (job.finished or time.time()) - (job.started or 0))
            rows = [r for r in self.repo.search_studies(limit=5000) if r.study_uid in set(job.study_uids)]
            mb = sum(r.size_mb for r in rows)
            imgs = sum(r.num_images for r in rows)
            if mb > 0 and imgs:
                learn(self.settings, job.node.get("id"), mb, secs, imgs)
        except Exception as e:  # noqa: BLE001
            log.debug("medida de rede: %s", e)

    def _update_net_label(self) -> None:
        active = len(self.net.active_jobs())
        text = self.net.server.status_text()
        if self.central is not None:
            text += f"  ·  servidor central :{self.central.port}"
        if getattr(self.repo, "remote", False):
            text += f"  ·  cliente de {self.repo.client.url}"
        if self.net.print_servers:
            text += "  ·  " + self.net.print_status_text()
        if self.http.server.isListening():
            text += f"  ·  API :{self.http.port}"
        if active:
            text += f"  ·  {active} transferência(s)"
        self.net_label.setText(text)
        hb = getattr(self, "home_bar", None)
        if hb is not None:
            hb.buttons["pacs"].defaultAction().setText(f"PACS ({active})" if active else "PACS")

    def _setup_tray(self) -> None:
        import sys
        from PySide6.QtWidgets import QSystemTrayIcon
        from ipe.ui.icons import icon
        self.tray = None
        # 0.100.30: no macOS não há ícone na barra de menus. No macOS 27, clicar nele fechava o programa: o Qt
        # (6.11) pergunta o número de cliques a um evento que não é de mouse e o sistema aborta
        # (`-[NSEvent clickCount]` dentro do `libqcocoa`). No Mac o Dock já faz o papel da bandeja.
        if sys.platform == "darwin" or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icon("mpr"), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        menu.addAction("Abrir", self.restore_from_tray)
        menu.addAction("Automação…", self.open_automation)
        menu.addSeparator()
        menu.addAction("Sair", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore_from_tray()
                                    if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        from ipe.auth import session as S
        S.audit(self.repo, "logout", "")
        self._really_quit = True
        self.close()

    def _confirmar_saida(self) -> bool:
        """0.99.6: *"Ative uma mensagem para confirmar se eu quero mesmo fechar o programa. Às vezes
        estou fechando por engano."* Preferências ▸ Geral ▸ "Perguntar antes de fechar o programa"."""
        if not self.settings.get("ui.confirmar_sair", True):
            return True
        caixa = QMessageBox(QMessageBox.Question, APP_NAME, "Fechar o Ipê?", parent=self)
        # 0.99.35: frases inteiras (a montada em pedaços não era traduzida)
        from ipe.core.i18n import tr
        servicos = []
        if any(getattr(s, "running", False) for s in getattr(self.net, "print_servers", []) or []):
            servicos.append(tr("o servidor de impressão"))
        if getattr(self.net, "active_jobs", None) and self.net.active_jobs():
            servicos.append(tr("os downloads e envios em andamento"))
        if servicos:
            lista = ", ".join(servicos)
            caixa.setInformativeText(f"Enquanto o programa estiver fechado, o nó DICOM não recebe exames. "
                                     f"Também param: {lista}.")
        else:
            caixa.setInformativeText("Enquanto o programa estiver fechado, o nó DICOM não recebe exames.")
        sim = caixa.addButton("Fechar", QMessageBox.AcceptRole)
        nao = caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.setDefaultButton(nao)                    # Enter por engano não fecha
        caixa.setEscapeButton(nao)
        caixa.exec()
        return caixa.clickedButton() is sim
