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
        from ipe.ui.network_dialog import local_ips
        ips = ", ".join(local_ips()) or "(não detectado)"
        hint = QLabel(f"<small>Endereço para os clientes: http://<b>{ips}</b>:porta — libere a porta no "
                      "firewall. Os usuários são os deste computador (Usuário → Usuários e permissões). "
                      "Outros visualizadores DICOMweb podem usar /dicomweb com usuário e senha.</small>")
        hint.setWordWrap(True)
        fs.addRow(hint)
        lay.addWidget(gs)

        # cliente
        gc = QGroupBox("Cliente")
        fc = QFormLayout(gc)
        self.url = QLineEdit(settings.get("central.url", "") or "", placeholderText="Ex.: http://10.0.0.5:8043")
        fc.addRow("Endereço do servidor:", self.url)
        self.verify = QCheckBox("Conferir o certificado HTTPS (desligue para certificado próprio)")
        self.verify.setChecked(bool(settings.get("central.verify_tls", False)))
        fc.addRow(self.verify)
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
            info = RemoteClient(self.url.text().strip(), verify_tls=self.verify.isChecked()).ping()
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
        s.set("central.cache_gb", self.cache.value())
        s.save()
        if (mode == "client") != (self._mode0 == "client"):
            QMessageBox.information(self, "Servidor central", "Feche e abra o programa de novo para "
                                    + ("entrar como cliente do servidor central." if mode == "client"
                                       else "voltar a usar o banco deste computador."))
        self.accept()
