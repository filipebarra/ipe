"""Rede → Configurar servidor central: modo local, servidor do grupo ou cliente."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)


class CentralDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Servidor central (intranet)")
        self.resize(620, 560)
        mode = settings.get("central.mode", "local")
        lay = QVBoxLayout(self)
        self.r_local = QRadioButton("Local — este computador trabalha sozinho (banco e usuários próprios)")
        self.r_server = QRadioButton("Servidor central — este computador guarda os exames, usuários, medidas, "
                                     "listas e filmes, e atende os outros")
        self.r_client = QRadioButton("Cliente — usar o servidor central (exames baixados ficam num cache local)")
        grp = QButtonGroup(self)
        for r in (self.r_local, self.r_server, self.r_client):
            grp.addButton(r)
            lay.addWidget(r)
        {"local": self.r_local, "server": self.r_server, "client": self.r_client}.get(mode, self.r_local).setChecked(True)

        # servidor
        gs = QGroupBox("Servidor")
        fs = QFormLayout(gs)
        self.port = QSpinBox(minimum=1, maximum=65535, value=int(settings.get("central.port", 8043)))
        fs.addRow("Porta HTTP:", self.port)
        self.cert = QLineEdit(settings.get("central.certfile", "") or "", placeholderText="opcional: HTTPS")
        self.key = QLineEdit(settings.get("central.keyfile", "") or "", placeholderText="opcional")
        for lab, ed in (("Certificado (.pem):", self.cert), ("Chave (.pem):", self.key)):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(ed, 1)
            b = QPushButton("…")
            b.clicked.connect(lambda _=False, e=ed: self._pick(e))
            h.addWidget(b)
            fs.addRow(lab, row)
        # 0.99.74: certificado da rede interna, feito pelo próprio Ipê (AC interna)
        rc = QHBoxLayout()
        b_gerar = QPushButton("Gerar certificado para a rede interna…")
        b_gerar.clicked.connect(self.gerar_certificado)
        rc.addWidget(b_gerar)
        b_ac = QPushButton("Salvar a AC (.crt)…")
        b_ac.setToolTip("O certificado da AC interna, para instalar no Windows dos clientes (navegador e outros "
                        "visualizadores DICOMweb)")
        b_ac.clicked.connect(self.salvar_ac)
        rc.addWidget(b_ac)
        rc.addStretch(1)
        fs.addRow(rc)
        self.cert_info = QLabel("")
        self.cert_info.setWordWrap(True)
        fs.addRow(self.cert_info)
        self._mostrar_cert()
        self.cert.textChanged.connect(lambda _t: self._mostrar_cert())
        from ipe.ui.network_dialog import local_ips
        ips = ", ".join(local_ips()) or "(não detectado)"
        hint = QLabel(f"<small>Endereço para os clientes: http://<b>{ips}</b>:porta — libere a porta no "
                      "firewall. Os usuários são os deste computador (Usuário → Usuários e permissões). "
                      "Outros visualizadores DICOMweb podem usar /dicomweb com usuário e senha.</small>")
        hint.setWordWrap(True)
        fs.addRow(hint)
        # 0.99.24: sem certificado o servidor fala HTTP, e a senha de cada login passa aberta na rede
        self.aviso_http = QLabel("<small><span style='color:#c03030'>Sem certificado o servidor usa HTTP: "
                                 "usuário e senha passam pela rede sem criptografia. Use só numa rede "
                                 "interna confiável, ou indique um certificado (.pem) para HTTPS.</span> "
                                 "Senha errada 5 vezes em 10 minutos bloqueia aquele computador por 10 minutos."
                                 "</small>")
        self.aviso_http.setWordWrap(True)
        fs.addRow(self.aviso_http)
        self.cert.textChanged.connect(lambda t: self.aviso_http.setVisible(not t.strip()))
        self.aviso_http.setVisible(not self.cert.text().strip())
        lay.addWidget(gs)

        # cliente
        gc = QGroupBox("Cliente")
        fc = QFormLayout(gc)
        self.url = QLineEdit(settings.get("central.url", "") or "", placeholderText="Ex.: http://10.0.0.5:8043")
        fc.addRow("Endereço do servidor:", self.url)
        self.verify = QCheckBox("Conferir o certificado HTTPS (desligue para certificado próprio)")
        self.verify.setChecked(bool(settings.get("central.verify_tls", False)))
        fc.addRow(self.verify)
        self.ca_pem = settings.get("central.ca_pem", "") or ""
        rt = QHBoxLayout()
        b_conf = QPushButton("Confiar no certificado deste servidor…")
        b_conf.setToolTip("Baixa a AC interna do servidor (gerada nele pelo Ipê) e passa a conferir o HTTPS com ela")
        b_conf.clicked.connect(self.confiar_no_servidor)
        rt.addWidget(b_conf)
        b_esq = QPushButton("Esquecer")
        b_esq.clicked.connect(self.esquecer_ac)
        rt.addWidget(b_esq)
        rt.addStretch(1)
        fc.addRow(rt)
        self.ca_info = QLabel("")
        self.ca_info.setWordWrap(True)
        fc.addRow(self.ca_info)
        self._mostrar_ca()
        self.cache = QDoubleSpinBox(minimum=1, maximum=10000, value=float(settings.get("central.cache_gb", 20)),
                                    suffix=" GB", decimals=0)
        fc.addRow("Cache local (máx.):", self.cache)
        row = QHBoxLayout()
        b = QPushButton("Testar conexão")
        b.clicked.connect(self.test)
        row.addWidget(b)
        self.test_label = QLabel("")
        row.addWidget(self.test_label, 1)
        fc.addRow(row)
        lay.addWidget(gc)
        self.gs, self.gc = gs, gc
        for r in (self.r_local, self.r_server, self.r_client):
            r.toggled.connect(self._update)
        self._update()
        self._mode0 = mode
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ------------------------------------------------------------------ 0.99.74: certificados
    def _mostrar_cert(self) -> None:
        from ipe.core import certificados as CE
        c = self.cert.text().strip()
        inf = CE.info(c) if c else None
        if inf is None:
            self.cert_info.setText("")
            return
        lista = ", ".join(inf["nomes"] + inf["ips"])
        if CE.ac_ao_lado(c) is not None:
            validade = inf["validade"]
            self.cert_info.setText(f"<small>Vale para: <b>{lista}</b> · até {validade} · com AC interna "
                                   f"(os clientes podem confiar pelo botão deles)</small>")
        else:
            validade = inf["validade"]
            self.cert_info.setText(f"<small>Vale para: <b>{lista}</b> · até {validade}</small>")

    def gerar_certificado(self) -> dict | None:
        from ipe.core import certificados as CE
        paths = getattr(self.parent(), "paths", None)
        if paths is None:
            from ipe.core.config import get_paths
            paths = get_paths()
        try:
            r = CE.gerar(CE.pasta(paths))
        except CE.ErroCertificado as e:
            QMessageBox.warning(self, "Certificado", str(e))
            return None
        self.cert.setText(r["certfile"])
        self.key.setText(r["keyfile"])
        lista, validade, imp = ", ".join(r["nomes"] + r["ips"]), r["validade"], r["impressao_ac"]
        QMessageBox.information(
            self, "Certificado",
            f"Certificado gerado para: {lista} (vale até {validade}).\n\nDê OK e feche e abra o programa: o "
            f"servidor passa a usar HTTPS. Nos clientes, troque o começo do endereço para https e use Confiar no "
            f"certificado deste servidor. Confira que a impressão digital é esta:\n\n{imp}")
        return r

    def salvar_ac(self) -> str | None:
        from ipe.core import certificados as CE
        pem = CE.ac_ao_lado(self.cert.text().strip())
        if pem is None:
            QMessageBox.information(self, "Certificado", "Gere primeiro o certificado para a rede interna.")
            return None
        caminho, _f = QFileDialog.getSaveFileName(self, "Salvar a AC interna", "Ipe-AC-interna.crt",
                                                  "Certificado (*.crt)")
        if not caminho:
            return None
        from pathlib import Path
        Path(caminho).write_bytes(pem)
        return caminho

    def _mostrar_ca(self) -> None:
        if not self.ca_pem:
            self.ca_info.setText("")
            return
        from ipe.core import certificados as CE
        try:
            imp = CE.impressao(self.ca_pem)
        except Exception:  # noqa: BLE001
            imp = "?"
        self.ca_info.setText(f"<small>Confiando na AC interna do servidor: {imp[:23]}…</small>")

    def confiar_no_servidor(self) -> bool:
        from ipe.central.remote import RemoteClient, RemoteError
        from ipe.core import certificados as CE
        url = self.url.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        try:
            pem = RemoteClient.buscar_ac(url)
            imp = CE.impressao(pem)
        except (RemoteError, CE.ErroCertificado, ValueError) as e:
            QMessageBox.warning(self, "Confiar no servidor", str(e))
            return False
        if QMessageBox.question(self, "Confiar no servidor",
                                f"Impressão digital da AC do servidor:\n\n{imp}\n\nConfira que é a mesma "
                                f"mostrada no servidor quando o certificado foi gerado. Confiar?") != QMessageBox.Yes:
            return False
        self.ca_pem = pem
        self.url.setText(url)
        self.verify.setChecked(True)
        self._mostrar_ca()
        return True

    def esquecer_ac(self) -> None:
        self.ca_pem = ""
        self._mostrar_ca()

    def _pick(self, edit: QLineEdit) -> None:
        path, _f = QFileDialog.getOpenFileName(self, "Arquivo", "", "PEM (*.pem *.crt *.key);;Todos (*)")
        if path:
            edit.setText(path)

    def _update(self) -> None:
        self.gs.setEnabled(self.r_server.isChecked())
        self.gc.setEnabled(self.r_client.isChecked())

    def mode(self) -> str:
        return "server" if self.r_server.isChecked() else "client" if self.r_client.isChecked() else "local"

    def test(self) -> bool:
        from ipe.central.remote import RemoteClient, RemoteError
        try:
            info = RemoteClient(self.url.text().strip(), verify_tls=self.verify.isChecked(),
                                ca_pem=self.ca_pem).ping()
        except (RemoteError, ValueError) as e:
            self.test_label.setText(f"<span style='color:#f88'>{e}</span>")
            return False
        self.test_label.setText(f"<span style='color:#8f8'>OK: {info.get('app')} {info.get('version')} "
                                f"em {info.get('name')}</span>")
        return True

    def _ok(self) -> None:
        mode = self.mode()
        if mode == "client" and not self.url.text().strip():
            QMessageBox.warning(self, "Servidor central", "Informe o endereço do servidor.")
            return
        s = self.settings
        s.set("central.mode", mode)
        s.set("central.port", self.port.value())
        s.set("central.certfile", self.cert.text().strip())
        s.set("central.keyfile", self.key.text().strip())
        s.set("central.url", self.url.text().strip())
        s.set("central.verify_tls", self.verify.isChecked())
        s.set("central.ca_pem", self.ca_pem)
        s.set("central.cache_gb", self.cache.value())
        s.save()
        if (mode == "client") != (self._mode0 == "client"):
            QMessageBox.information(self, "Servidor central", "Feche e abra o programa de novo para "
                                    + ("entrar como cliente do servidor central." if mode == "client"
                                       else "voltar a usar o banco deste computador."))
        self.accept()
