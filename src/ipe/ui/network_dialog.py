"""Rede DICOM: este computador (nó local e API), nós remotos, identidades e auditoria."""

from __future__ import annotations

import re
import secrets

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QHostAddress, QNetworkInterface
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from ipe.ui.tabelas import colunas_ajustaveis

AE_RE = re.compile(r"^[A-Za-z0-9_\-. ]{1,16}$")


def local_ips() -> list[str]:
    out = []
    for a in QNetworkInterface.allAddresses():
        if a.protocol() == QHostAddress.IPv4Protocol and not a.isLoopback():
            out.append(a.toString())
    return out


def _check_ae(parent, ae: str) -> bool:
    if not AE_RE.match(ae.strip()):
        QMessageBox.warning(parent, "AE Title", "AE Title: até 16 caracteres (letras, números, - _ .).")
        return False
    return True


class NodeDialog(QDialog):
    def __init__(self, node: dict | None, parent=None, net=None, settings=None, repo=None):
        super().__init__(parent)
        self.net, self.settings = net, settings
        self.setWindowTitle("Nó DICOM remoto")
        n = node or {"retrieve": "get", "port": 104, "use_in_search": True, "use_in_priors": True,
                     "use_in_send": True, "active": True}
        self.data = dict(n)
        f = QFormLayout(self)
        self.name = QLineEdit(n.get("name", ""), placeholderText="Ex.: PACS IMEB")
        self.ae = QLineEdit(n.get("ae_title", ""), placeholderText="Ex.: IMEBPACS")
        self.host = QLineEdit(n.get("host", ""), placeholderText="IP ou nome, ex.: 10.0.0.5")
        self.port = QSpinBox(minimum=1, maximum=65535, value=int(n.get("port", 104)))
        self.retrieve = QComboBox()
        self.retrieve.addItem("C-GET (mais simples; imagens voltam pela mesma conexão)", "get")
        self.retrieve.addItem("C-MOVE (o PACS precisa ter este computador cadastrado)", "move")
        self.retrieve.setCurrentIndex(max(0, self.retrieve.findData(n.get("retrieve", "get"))))
        self.move_dest = QLineEdit(n.get("move_destination", ""),
                                   placeholderText="vazio = este programa")
        # --- DICOMweb
        self.kind = QComboBox()
        self.kind.addItem("DICOM clássico (DIMSE) — C-FIND, C-GET/C-MOVE, C-STORE", "dimse")
        self.kind.addItem("DICOMweb (HTTP) — QIDO-RS, WADO-RS, STOW-RS", "dicomweb")
        self.kind.setCurrentIndex(max(0, self.kind.findData(n.get("kind", "dimse"))))
        self.kind.currentIndexChanged.connect(self._trocar_tipo)
        self.base_url = QLineEdit(n.get("base_url", ""),
                                  placeholderText="Ex.: http://192.168.1.216:8042/dicom-web")
        self.user = QLineEdit(n.get("username", ""), placeholderText="vazio = sem autenticação")
        self.senha = QLineEdit(n.get("password", ""))
        self.senha.setEchoMode(QLineEdit.Password)
        self.ver_senha = QCheckBox("ver")
        self.ver_senha.toggled.connect(
            lambda on: self.senha.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        linha_senha = QHBoxLayout()
        linha_senha.addWidget(self.senha, 1)
        linha_senha.addWidget(self.ver_senha)
        self.tls = QCheckBox("Aceitar certificado não verificado (HTTPS com certificado próprio)")
        self.tls.setChecked(not bool(n.get("verify_tls", True)))
        self.tls.setToolTip("Marque só em rede interna, e sabendo o que faz: com isto o programa "
                            "não confere a identidade do servidor.")
        self.aviso_web = QLabel("<small>A senha fica <b>em texto claro</b> no banco deste "
                                "computador, como o token da API. Use um usuário só de "
                                "leitura quando o PACS permitir.</small>")
        self.aviso_web.setWordWrap(True)
        self.search = QCheckBox("Busca (“Todos os nós de busca”, chamada externa e buscas agendadas)")
        self.search.setChecked(bool(n.get("use_in_search", True)))
        self.priors = QCheckBox("Busca de anteriores (painel Anteriores e pré-busca automática)")
        self.priors.setChecked(bool(n.get("use_in_priors", n.get("use_in_search", True))))
        self.send = QCheckBox("Envio (aparece em “Enviar para”)")
        self.send.setChecked(bool(n.get("use_in_send", True)))
        uses = QWidget()
        ul = QVBoxLayout(uses)
        ul.setContentsMargins(0, 0, 0, 0)
        for cb in (self.search, self.priors, self.send):
            ul.addWidget(cb)
        self.active = QCheckBox("Ativo (pode conectar e enviar para este programa)")
        self.active.setChecked(bool(n.get("active", True)))
        self.stream = QComboBox()
        self.stream.addItem("Usar o padrão das preferências", None)
        self.stream.addItem("Sempre abrir enquanto baixa (streaming)", True)
        self.stream.addItem("Nunca: esperar o download terminar", False)
        self.stream.setCurrentIndex({None: 0, True: 1, False: 2}.get(n.get("stream_open"), 0))
        self.net_test = QLabel(self._stats_text(n))
        self.net_test.setWordWrap(True)
        b_test = QPushButton("Testar rede")
        b_test.clicked.connect(self._test)
        test_row = QHBoxLayout()
        test_row.addWidget(self.net_test, 1)
        test_row.addWidget(b_test)
        self.priority = QSpinBox(minimum=0, maximum=99, value=int(n.get("priority", 0)))
        self.note = QLineEdit(n.get("note", ""))
        self._linhas = {}
        for chave, lab, w in (
                ("tipo", "Tipo de conexão:", self.kind),
                ("nome", "Nome:", self.name),
                ("ae", "AE Title:", self.ae),
                ("host", "Endereço:", self.host),
                ("porta", "Porta:", self.port),
                ("url", "Endereço DICOMweb:", self.base_url),
                ("user", "Usuário:", self.user),
                ("senha", "Senha:", linha_senha),
                ("tls", "", self.tls),
                ("aviso", "", self.aviso_web),
                ("retrieve", "Download por:", self.retrieve),
                ("move", "Destino do C-MOVE:", self.move_dest),
                ("usos", "Usar em:", uses),
                ("ativo", "", self.active),
                ("stream", "Exames grandes:", self.stream),
                ("rede", "Rede:", test_row),
                ("ordem", "Ordem nas buscas:", self.priority),
                ("nota", "Observação:", self.note)):
            f.addRow(lab, w)
            self._linhas[chave] = (f.labelForField(w) if not isinstance(w, QHBoxLayout) else
                                   f.labelForField(linha_senha), w)
        # 0.99.26: quem vê este nó (todos, só eu, eu e escolhidos)
        from ipe.ui.visivel_para import VisivelPara
        self.visivel = VisivelPara(node, repo, settings, self)
        f.addRow("Visível para:", self.visivel)
        if not self.visivel.isVisibleTo(self) and settings is not None:
            f.labelForField(self.visivel).setVisible(False)
        self._trocar_tipo()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def eh_web(self) -> bool:
        return self.kind.currentData() == "dicomweb"

    def _trocar_tipo(self) -> None:
        """Mostra só os campos do protocolo escolhido: AE e porta não existem no DICOMweb, e
        endereço HTTP e senha não existem no DIMSE."""
        web = self.eh_web()
        so_dimse = ("ae", "host", "porta", "retrieve", "move")
        so_web = ("url", "user", "senha", "tls", "aviso")
        for chave in so_dimse + so_web:
            rotulo, campo = self._linhas[chave]
            visivel = (chave in so_web) if web else (chave in so_dimse)
            if rotulo is not None:
                rotulo.setVisible(visivel)
            if isinstance(campo, QHBoxLayout):
                for i in range(campo.count()):
                    w = campo.itemAt(i).widget()
                    if w is not None:
                        w.setVisible(visivel)
            else:
                campo.setVisible(visivel)
        self.send.setEnabled(True)

    def _ok(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Nó", "Preencha o nome.")
            return
        if self.eh_web():
            url = self.base_url.text().strip()
            if not url:
                QMessageBox.warning(self, "Nó DICOMweb", "Preencha o endereço DICOMweb "
                                    "(a base, que costuma terminar em /dicom-web).")
                return
            self.data.update({
                "name": self.name.text().strip(), "kind": "dicomweb",
                "base_url": url.rstrip("/"), "username": self.user.text().strip(),
                "password": self.senha.text(), "verify_tls": not self.tls.isChecked(),
                "ae_title": "", "host": "", "port": 0, "retrieve": "get", "move_destination": "",
                "use_in_search": self.search.isChecked(), "use_in_priors": self.priors.isChecked(),
                "use_in_send": self.send.isChecked(), "active": self.active.isChecked(),
                "stream_open": self.stream.currentData(),
                "priority": self.priority.value(), "note": self.note.text().strip(), **self.visivel.valor()})
            self.accept()
            return
        if not self.host.text().strip():
            QMessageBox.warning(self, "Nó", "Preencha nome e endereço.")
            return
        if not _check_ae(self, self.ae.text()):
            return
        if self.move_dest.text().strip() and not _check_ae(self, self.move_dest.text()):
            return
        self.data.update({
            "name": self.name.text().strip(), "kind": "dimse", "ae_title": self.ae.text().strip(),
            "host": self.host.text().strip(), "port": self.port.value(), "base_url": "",
            "username": "", "password": "",
            "retrieve": self.retrieve.currentData(), "move_destination": self.move_dest.text().strip(),
            "use_in_search": self.search.isChecked(), "use_in_priors": self.priors.isChecked(),
            "use_in_send": self.send.isChecked(), "active": self.active.isChecked(),
            "stream_open": self.stream.currentData(),
            "priority": self.priority.value(), "note": self.note.text().strip(), **self.visivel.valor()})
        self.accept()


    def _stats_text(self, n: dict) -> str:
        from ipe.network import probe
        if self.settings is None or not n.get("id"):
            return "Sem medidas ainda."
        return probe.summary(self.settings, n["id"])

    def _test(self) -> None:
        """C-ECHO algumas vezes: mostra se o nó responde e quanto demora."""
        if self.net is None:
            QMessageBox.information(self, "Rede", "Salve o nó antes de testar.")
            return
        node = dict(self.data)
        if self.eh_web():                # testa o que está na tela, salvo ou não (0.99.6)
            node.update({"kind": "dicomweb", "base_url": self.base_url.text().strip().rstrip("/"),
                         "username": self.user.text().strip(), "password": self.senha.text(),
                         "verify_tls": not self.tls.isChecked(), "name": self.name.text().strip() or "nó"})
        else:
            node.update({"kind": "dimse", "ae_title": self.ae.text().strip(), "host": self.host.text().strip(),
                         "port": self.port.value(), "retrieve": self.retrieve.currentData(),
                         "name": self.name.text().strip() or "nó"})
            if not node["host"] or not node["ae_title"]:
                self.net_test.setText("<span style='color:#b00'>Preencha o AE Title e o endereço para testar.</span>")
                return
        self.net_test.setText("Testando…")

        def done(res, err) -> None:
            from ipe.network import probe
            if err is not None or not res:
                self.net_test.setText(f"<span style='color:#b00'>Sem resposta: {err}</span>")
                return
            ms = res["ms"]
            extra = probe.summary(self.settings, node.get("id")) if self.settings is not None and node.get("id") else ""
            slow = " — rede lenta; vale abrir enquanto baixa" if ms > probe.SLOW_MS else ""
            self.net_test.setText(f"Responde em {ms:.0f} ms{slow}. {extra}")
        self.net.test_network(node, None, done)


class IdentityDialog(QDialog):
    def __init__(self, ident: dict | None, nodes: list[dict], parent=None, repo=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("Identidade (AE Title de origem)")
        i = ident or {}
        self.data = dict(i)
        f = QFormLayout(self)
        warn = QLabel("Use o AE de outra estação só com o conhecimento da TI: muitos PACS conferem o AE "
                      "junto com o IP. Toda operação com identidade fica registrada na auditoria.")
        warn.setWordWrap(True)
        f.addRow(warn)
        self.name = QLineEdit(i.get("name", ""), placeholderText="Ex.: Workstation mama 2")
        self.ae = QLineEdit(i.get("ae_title", ""), placeholderText="Ex.: WS-MAMA2")
        self.move_dest = QLineEdit(i.get("move_destination", ""),
                                   placeholderText="vazio = este programa; ou o AE da estação real")
        self.nodes = QListWidget()
        allowed = {x for x in str(i.get("allowed_nodes", "")).split(",") if x}
        for n in nodes:
            it = QListWidgetItem(f"{n['name']} ({n['ae_title']})")
            it.setData(Qt.UserRole, n["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if str(n["id"]) in allowed else Qt.Unchecked)
            self.nodes.addItem(it)
        self.note = QLineEdit(i.get("note", ""))
        f.addRow("Nome:", self.name)
        f.addRow("AE Title de origem:", self.ae)
        f.addRow("Destino do C-MOVE:", self.move_dest)
        f.addRow(QLabel("Nós em que pode ser usada (nenhum marcado = todos):"))
        f.addRow(self.nodes)
        f.addRow("Observação:", self.note)
        from ipe.ui.visivel_para import VisivelPara
        self.visivel = VisivelPara(ident, repo, settings, self)
        f.addRow("Visível para:", self.visivel)
        if not self.visivel.isVisibleTo(self) and settings is not None:
            f.labelForField(self.visivel).setVisible(False)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _ok(self) -> None:
        if not self.name.text().strip() or not _check_ae(self, self.ae.text()):
            return
        if self.move_dest.text().strip() and not _check_ae(self, self.move_dest.text()):
            return
        ids = [str(self.nodes.item(k).data(Qt.UserRole)) for k in range(self.nodes.count())
               if self.nodes.item(k).checkState() == Qt.Checked]
        self.data.update({"name": self.name.text().strip(), "ae_title": self.ae.text().strip(),
                          "move_destination": self.move_dest.text().strip(),
                          "allowed_nodes": ",".join(ids), "note": self.note.text().strip(),
                          **self.visivel.valor()})
        self.accept()


class NetworkDialog(QDialog):
    def __init__(self, settings, repo, net, parent=None, ao_mudar=None, so_pessoal: bool = False):
        super().__init__(parent)
        self.settings, self.repo, self.net = settings, repo, net
        self.ao_mudar = ao_mudar        # 0.99.6: nós/identidades mudaram → as outras telas já veem
        # 0.99.26: quem não configura o computador mexe só nos nós e identidades **dele**
        self.so_pessoal = so_pessoal
        self.setWindowTitle("Meus nós DICOM" if so_pessoal else "Rede DICOM")
        self.resize(860, 560)
        tabs = QTabWidget()
        if not so_pessoal:
            tabs.addTab(self._local_tab(), "Este computador")
        tabs.addTab(self._nodes_tab(), "Nós remotos")
        tabs.addTab(self._ident_tab(), "Identidades")
        if not so_pessoal:
            tabs.addTab(self._audit_tab(), "Auditoria")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept if so_pessoal else self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    # ------------------------------------------------------------ este computador
    def _local_tab(self) -> QWidget:
        c = self.settings.get("dicom", {}) or {}
        w = QWidget()
        f = QFormLayout(w)
        self.enabled = QCheckBox("Nó DICOM ligado (receber imagens e responder a consultas)")
        self.enabled.setChecked(bool(c.get("enabled", True)))
        self.ae = QLineEdit(c.get("ae_title", "DICOMVIEWER"))
        self.port = QSpinBox(minimum=1, maximum=65535, value=int(c.get("port", 11112)))
        self.accept_c = QComboBox()
        self.accept_c.addItem("Só nós cadastrados", "known")
        self.accept_c.addItem("Só nós cadastrados, conferindo o IP do nó", "known_ip")
        self.accept_c.addItem("Qualquer AE", "any")
        self.accept_c.setToolTip("O AE Title é só um nome que o aparelho diz ter: qualquer computador da rede "
                                 "pode imitá-lo. Conferindo o IP, a conexão só é aceita se vier do endereço "
                                 "cadastrado no nó com aquele AE (o campo IP do nó).")
        self.accept_c.setCurrentIndex(max(0, self.accept_c.findData(c.get("accept", "known"))))
        self.timeout = QSpinBox(minimum=5, maximum=600, suffix=" s", value=int(c.get("timeout", 30)))
        self.parallel = QSpinBox(minimum=1, maximum=8, value=int(c.get("max_parallel", 2)))
        status = QLabel(self.net.server.status_text())
        ips = ", ".join(local_ips()) or "?"
        info = QLabel(f"Para o PACS enviar para cá (C-MOVE/C-STORE), informe à TI:<br>"
                      f"<b>AE {c.get('ae_title', 'DICOMVIEWER')}</b> · IP <b>{ips}</b> · porta "
                      f"<b>{c.get('port', 11112)}</b>")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addRow(self.enabled)
        f.addRow("AE Title:", self.ae)
        f.addRow("Porta:", self.port)
        f.addRow("Aceitar conexões de:", self.accept_c)
        f.addRow("Tempo limite:", self.timeout)
        f.addRow("Transferências simultâneas:", self.parallel)
        f.addRow("Situação:", status)
        f.addRow(info)
        f.addRow(QLabel("<b>Chamada externa (RIS, navegador, scripts)</b>"))
        self.http = QCheckBox("API HTTP local ligada")
        self.http.setChecked(bool(c.get("http_enabled", True)))
        self.http_port = QSpinBox(minimum=1, maximum=65535, value=int(c.get("http_port", 8042)))
        self.token = QLineEdit(c.get("http_token", ""))
        self.token.setReadOnly(True)
        b_new = QPushButton("Gerar novo")
        b_new.clicked.connect(lambda: self.token.setText(secrets.token_urlsafe(18)))
        b_copy = QPushButton("Copiar")
        b_copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.token.text()))
        tok = QHBoxLayout()
        tok.addWidget(self.token, 1)
        tok.addWidget(b_new)
        tok.addWidget(b_copy)
        self.so_viewer = QCheckBox("Abrir só o visualizador (sem o banco de dados)")
        self.so_viewer.setChecked(bool(c.get("external_viewer_only", False)))
        self.so_viewer.setToolTip("O exame pedido abre numa janela de visualização e o banco de "
                                  "dados não aparece — e não há caminho até ele por essa janela: "
                                  "sem lista de pacientes, sem busca no PACS, sem exportar. "
                                  "Fechar o exame deixa o programa na bandeja, pronto para a "
                                  "próxima chamada. Isto é o padrão: cada chamada pode pedir o "
                                  "contrário com janela=viewer ou janela=completo.")
        self.remote = QCheckBox("Aceitar chamadas de outros computadores (só dos IPs abaixo)")
        self.remote.setChecked(bool(c.get("http_allow_remote", False)))
        self.ips = QLineEdit(", ".join(c.get("http_allowed_ips", []) or []),
                             placeholderText="Ex.: 10.0.0.20, 10.0.0.21")
        f.addRow(self.http)
        f.addRow("Porta HTTP:", self.http_port)
        f.addRow("Token:", tok)
        f.addRow(self.so_viewer)
        # 0.99.22: a chamada traz outro paciente com um já aberto
        from ipe.ui.main_window import MainWindow
        self.outro_pac = QComboBox()
        for chave, nome in MainWindow.OUTRO_PACIENTE:
            self.outro_pac.addItem(nome, chave)
        i = self.outro_pac.findData(str(self.settings.get("viewer.outro_paciente_externo", "perguntar") or "perguntar"))
        self.outro_pac.setCurrentIndex(max(0, i))
        self.outro_pac.setToolTip("Quando a chamada do RIS abre um paciente e outro ainda está aberto em "
                                  "algum monitor. Abrir o seguinte com o anterior à vista é como a imagem "
                                  "de um acaba laudada no nome do outro.")
        f.addRow("Chamada com outro paciente aberto:", self.outro_pac)
        # 0.99.24: link ipe:// sem o token — qualquer página da internet pode montar um
        self.link_sem = QComboBox()
        for chave, nome in (("perguntar", "Perguntar antes de abrir"), ("aceitar", "Aceitar"),
                            ("recusar", "Recusar")):
            self.link_sem.addItem(nome, chave)
        self.link_sem.setCurrentIndex(max(0, self.link_sem.findData(str(c.get("link_sem_token", "perguntar")))))
        self.link_sem.setToolTip("Um link ipe:// pode vir de qualquer página que se abra no navegador. Com o "
                                 "token no link (…&token=<o token acima>) ele abre direto; sem o token, vale "
                                 "esta escolha. Ponha o token no link do RIS para ele não perguntar.")
        f.addRow("Link ipe:// sem o token:", self.link_sem)
        # 0.99.31 (onda A3): link cifrado — sem o ID do paciente à vista, montado com o token
        b_cif = QPushButton("Montar link cifrado…")
        b_cif.setToolTip("Monta um ipe://open?c=… a partir de accession=…, patientid=… etc. Só quem tem o token "
                         "consegue montar; vale 24 horas; abre direto. O RIS monta igual (guia, Chamada externa).")
        b_cif.clicked.connect(self._montar_link_cifrado)
        f.addRow("", b_cif)
        f.addRow(self.remote)
        f.addRow("IPs permitidos:", self.ips)
        f.addRow(QLabel("<b>Impressora DICOM (receber filmes das modalidades)</b>"))
        b_print = QPushButton("Abrir as configurações de impressão…")
        b_print.clicked.connect(self._abrir_impressao)
        f.addRow(b_print)
        f.addRow(QLabel("<i>Servidores de impressão, destinos, regras e modelos de folha ficam numa "
                        "janela própria (botão Impressão na tela inicial).</i>"))
        f.addRow(QLabel("<b>Exames grandes (abrir enquanto baixa)</b>"))
        self.stream_default = QCheckBox("Abrir o exame assim que as primeiras imagens chegarem (padrão dos nós)")
        self.stream_default.setChecked(bool(self.settings.get("network.stream_default", False)))
        self.stream_ask = QCheckBox("Perguntar quando o download parecer demorado")
        self.stream_ask.setChecked(bool(self.settings.get("network.stream_ask", True)))
        self.stream_secs = QSpinBox(minimum=5, maximum=600, suffix=" s",
                                    value=int(self.settings.get("network.stream_suggest_seconds", 20) or 20))
        self.stream_ext = QCheckBox("Chamada externa (RIS, link, API) abre o exame enquanto baixa")
        self.stream_ext.setChecked(bool(self.settings.get("network.stream_external", True)))
        self.stream_ext.setToolTip("Quem chama de fora não está na tela para responder pergunta "
                                   "nenhuma. A opção do próprio nó, quando marcada, continua mandando.")
        f.addRow(self.stream_default)
        f.addRow(self.stream_ext)
        f.addRow(self.stream_ask)
        f.addRow("Perguntar a partir de:", self.stream_secs)
        f.addRow(QLabel("<i>O tempo é estimado pela velocidade medida em downloads anteriores de cada nó "
                        "(veja “Testar rede” no cadastro do nó).</i>"))
        return w

    def _montar_link_cifrado(self) -> str:
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from ipe.network import link_cifrado as LC
        q, ok = QInputDialog.getText(self, "Link cifrado", "O que vai no link (como na query do link comum):",
                                     text="accession=")
        if not ok or not q.strip():
            return ""
        try:
            link = f"ipe://open?c={LC.montar(q.strip(), self.token.text())}"
        except LC.LinkInvalido as e:
            QMessageBox.warning(self, "Link cifrado", str(e))
            return ""
        QGuiApplication.clipboard().setText(link)
        QMessageBox.information(self, "Link cifrado", f"Copiado (vale 24 horas):\n\n{link}")
        return link

    def _abrir_impressao(self) -> None:
        from ipe.ui.print_settings import PrintSettingsDialog
        PrintSettingsDialog(self.settings, self.net, self).exec()

    # ------------------------------------------------------------ nós
    def _nodes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.t_nodes = QTableWidget(0, 10)
        self.t_nodes.setHorizontalHeaderLabels(["Nome", "AE Title", "Endereço", "Porta", "Download",
                                                "Busca", "Anteriores", "Envio", "Ativo", "Visível para"])
        self.t_nodes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_nodes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_nodes.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.t_nodes.verticalHeader().setVisible(False)
        self.t_nodes.doubleClicked.connect(lambda _: self._edit_node())
        colunas_ajustaveis(self.t_nodes)
        btns = QHBoxLayout()
        for text, fn in (("Adicionar…", lambda: self._edit_node(new=True)), ("Editar…", self._edit_node),
                         ("Excluir", self._delete_node), ("Testar (C-ECHO)", self._test_node)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        self.node_status = QLabel("")
        lay.addWidget(self.t_nodes, 1)
        lay.addLayout(btns)
        lay.addWidget(self.node_status)
        from PySide6.QtWidgets import QGroupBox, QListWidget, QRadioButton
        g = QGroupBox("Busca por anteriores")
        gl = QVBoxLayout(g)
        self.pr_all = QRadioButton("Todos os nós marcados para anteriores")
        self.pr_sel = QRadioButton("Somente os nós selecionados:")
        self.pr_list = QListWidget()
        self.pr_list.setMaximumHeight(90)
        self.pr_all.toggled.connect(lambda on: self.pr_list.setEnabled(not on))
        gl.addWidget(self.pr_all)
        gl.addWidget(self.pr_sel)
        gl.addWidget(self.pr_list)
        lay.addWidget(g)
        self._fill_nodes()
        return w

    def _fill_prior_choice(self) -> None:
        from PySide6.QtWidgets import QListWidgetItem
        from ipe.network.nodes import prior_candidates, prior_selection
        if not hasattr(self, "pr_list"):
            return
        sel = prior_selection(self.settings)
        prev = self._prior_checked() if self.pr_list.count() else sel
        self.pr_list.clear()
        for n in prior_candidates(self.repo):
            it = QListWidgetItem(f"{n['name']}  ({n['ae_title']}@{n['host']})")
            it.setData(Qt.UserRole, n["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if prev is None or n["id"] in prev else Qt.Unchecked)
            self.pr_list.addItem(it)
        if not self.pr_all.isChecked() and not self.pr_sel.isChecked():
            (self.pr_all if sel is None else self.pr_sel).setChecked(True)
        self.pr_list.setEnabled(self.pr_sel.isChecked())

    def _prior_checked(self) -> list[int]:
        return [self.pr_list.item(i).data(Qt.UserRole) for i in range(self.pr_list.count())
                if self.pr_list.item(i).checkState() == Qt.Checked]

    def _fill_nodes(self) -> None:
        from ipe.auth import visibilidade as V
        nodes = self.repo.nodes(gerenciar=True)
        self.t_nodes.setRowCount(len(nodes))
        for r, n in enumerate(nodes):
            vals = [n["name"], n["ae_title"], n["host"], str(n["port"]), n["retrieve"].upper(),
                    "sim" if n["use_in_search"] else "", "sim" if n["use_in_priors"] else "",
                    "sim" if n["use_in_send"] else "", "sim" if n["active"] else "não", V.rotulo(n)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, n["id"])
                self.t_nodes.setItem(r, c, it)
        self._fill_prior_choice()

    def _selected_node(self) -> dict | None:
        r = self.t_nodes.currentRow()
        if r < 0 or self.t_nodes.item(r, 0) is None:
            return None
        return self.repo.node(self.t_nodes.item(r, 0).data(Qt.UserRole))

    def pode_mexer(self, item: dict | None) -> bool:
        """No modo pessoal, os itens do serviço e os dos outros só se olham (0.99.26)."""
        if item is None or not self.so_pessoal:
            return True
        from ipe.auth import visibilidade as V
        v = V.visao_atual()
        dono = str(item.get("dono") or "")
        if v is not None and dono and dono.lower() == v.usuario.lower():
            return True
        QMessageBox.information(self, "Nó DICOM", "Este item é " + ("do serviço" if not dono else f"de {dono}")
                                + ": só quem configura o computador pode mudá-lo.")
        return False

    def _edit_node(self, new: bool = False) -> None:
        node = None if new else self._selected_node()
        if not new and node is None:
            return
        if not self.pode_mexer(node):
            return
        dlg = NodeDialog(node, self, getattr(self, "net", None), getattr(self, "settings", None),
                         repo=self.repo)
        if dlg.exec():
            nid = self.repo.save_node(dlg.data)
            self._fill_nodes()
            self._selecionar_no(nid)
            self._nos_mudaram()

    def _delete_node(self) -> None:
        n = self._selected_node()
        if n and not self.pode_mexer(n):
            return
        if n and QMessageBox.question(self, "Excluir", f"Excluir o nó {n['name']}?") == QMessageBox.Yes:
            self.repo.delete_node(n["id"])
            self._fill_nodes()
            self._nos_mudaram()

    def _selecionar_no(self, nid) -> None:
        for r in range(self.t_nodes.rowCount()):
            it = self.t_nodes.item(r, 0)
            if it is not None and it.data(Qt.UserRole) == nid:
                self.t_nodes.selectRow(r)
                return

    def _nos_mudaram(self) -> None:
        """Bug relatado (27/10): *"quando acrescento um nó DICOM, ao testar dá erro. tenho que salvar,
        fechar e abrir a janela para aparecer"*. O nó era gravado na hora, mas a lista de quem pode
        conectar neste programa (e a do PACS, da Gestão, do "Enviar para") só se refazia ao fechar a
        janela. Agora se refaz a cada nó salvo ou excluído."""
        if self.net is not None:
            try:
                self.net.refresh_acl()
            except Exception:  # noqa: BLE001
                pass
        if callable(self.ao_mudar):
            try:
                self.ao_mudar()
            except Exception:  # noqa: BLE001
                pass

    def _test_node(self) -> None:
        n = self._selected_node()
        if n is None:
            return
        self.node_status.setText(f"Testando {n['name']}…")

        def done(res, err) -> None:
            if err is not None:
                self.node_status.setText(f"✗ {n['name']}: {err}")
            else:
                ok, msg = res
                self.node_status.setText(("✓ " if ok else "✗ ") + f"{n['name']}: {msg}")
        self.net.echo(n, None, done)

    # ------------------------------------------------------------ identidades
    def _ident_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Identidades são AE Titles que o programa pode assumir numa busca, download "
                             "ou envio (ex.: buscar no PACS como se fosse a estação de mama)."))
        self.t_ids = QTableWidget(0, 5)
        self.t_ids.setHorizontalHeaderLabels(["Nome", "AE Title", "Destino C-MOVE", "Nós", "Visível para"])
        self.t_ids.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_ids.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_ids.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.t_ids.verticalHeader().setVisible(False)
        self.t_ids.doubleClicked.connect(lambda _: self._edit_ident())
        colunas_ajustaveis(self.t_ids)
        btns = QHBoxLayout()
        for text, fn in (("Adicionar…", lambda: self._edit_ident(new=True)), ("Editar…", self._edit_ident),
                         ("Excluir", self._delete_ident)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addWidget(self.t_ids, 1)
        lay.addLayout(btns)
        self._fill_ids()
        return w

    def _fill_ids(self) -> None:
        from ipe.auth import visibilidade as V
        ids = self.repo.identities(gerenciar=True)
        names = {str(n["id"]): n["name"] for n in self.repo.nodes(gerenciar=True)}
        self.t_ids.setRowCount(len(ids))
        for r, i in enumerate(ids):
            allowed = [names.get(x, x) for x in str(i["allowed_nodes"]).split(",") if x]
            vals = [i["name"], i["ae_title"], i["move_destination"] or "(este programa)",
                    ", ".join(allowed) or "todos", V.rotulo(i)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, i["id"])
                self.t_ids.setItem(r, c, it)

    def _selected_ident(self) -> dict | None:
        r = self.t_ids.currentRow()
        if r < 0 or self.t_ids.item(r, 0) is None:
            return None
        return self.repo.identity(self.t_ids.item(r, 0).data(Qt.UserRole))

    def _edit_ident(self, new: bool = False) -> None:
        ident = None if new else self._selected_ident()
        if not new and ident is None:
            return
        if not self.pode_mexer(ident):
            return
        dlg = IdentityDialog(ident, self.repo.nodes(gerenciar=True), self, repo=self.repo,
                             settings=getattr(self, "settings", None))
        if dlg.exec():
            self.repo.save_identity(dlg.data)
            self._fill_ids()
            self._nos_mudaram()

    def _delete_ident(self) -> None:
        i = self._selected_ident()
        if i and not self.pode_mexer(i):
            return
        if i and QMessageBox.question(self, "Excluir", f"Excluir a identidade {i['name']}?") == QMessageBox.Yes:
            self.repo.delete_identity(i["id"])
            self._fill_ids()
            self._nos_mudaram()

    # ------------------------------------------------------------ auditoria
    def _audit_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        rows = self.repo.audit_entries(300)
        t = QTableWidget(len(rows), 4)
        t.setHorizontalHeaderLabels(["Quando", "Usuário", "Ação", "Detalhe"])
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, (at, user, action, detail) in enumerate(rows):
            for c, v in enumerate((f"{at:%d/%m/%Y %H:%M:%S}", user, action, detail)):
                t.setItem(r, c, QTableWidgetItem(v))
        lay.addWidget(t)
        colunas_ajustaveis(t)
        return w

    # ------------------------------------------------------------ salvar
    def _save(self) -> None:
        if not _check_ae(self, self.ae.text()):
            return
        ips = [x.strip() for x in self.ips.text().replace(";", ",").split(",") if x.strip()]
        c = dict(self.settings.get("dicom", {}) or {})
        c.update({"enabled": self.enabled.isChecked(), "ae_title": self.ae.text().strip(),
                  "port": self.port.value(), "accept": self.accept_c.currentData(),
                  "timeout": self.timeout.value(), "max_parallel": self.parallel.value(),
                  "http_enabled": self.http.isChecked(), "http_port": self.http_port.value(),
                  "http_token": self.token.text(), "http_allow_remote": self.remote.isChecked(),
                  "external_viewer_only": self.so_viewer.isChecked(),
                  "http_allowed_ips": ips, "link_sem_token": self.link_sem.currentData()})
        self.settings.set("dicom", c)
        self.settings.set("viewer.outro_paciente_externo", self.outro_pac.currentData())
        self.settings.set("network.stream_default", self.stream_default.isChecked())
        self.settings.set("network.stream_external", self.stream_ext.isChecked())
        self.settings.set("network.stream_ask", self.stream_ask.isChecked())
        self.settings.set("network.stream_suggest_seconds", self.stream_secs.value())
        from ipe.network.nodes import set_prior_selection
        set_prior_selection(self.settings, None if self.pr_all.isChecked() else self._prior_checked())
        self.settings.save()
        self.accept()
