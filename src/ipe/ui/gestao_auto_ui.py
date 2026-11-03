"""Gestão DICOM automática — a aba "Automático" da janela de Gestão e o editor de regra (0.99.6).

O painel mostra, para cada regra, quando rodou, o que completou, o que deu erro e quais modalidades ou
destinos estavam fora do ar; embaixo, o histórico das execuções.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTimeEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ipe.automation.rules import describe_schedule
from ipe.network import gestao as G
from ipe.network import gestao_auto as GA
from ipe.ui.tabelas import colunas_ajustaveis

PERIODOS_AUTO = [("Hoje", "hoje"), ("Ontem", "ontem"), ("Ontem e hoje", "2dias"), ("Últimos 7 dias", "7dias")]
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
SIMBOLO = {"ok": ("✔", "#7fd07f"), "erro": ("⚠", "#ff8a80"), "offline": ("⛔", "#ffb74d"),
           "rodando": ("➜", "#ffd166"), "": ("·", None)}


def _identidades(repo, net, no):
    out = [("Este programa" + (f" ({net.local_ae})" if net is not None else ""), None)]
    ids = net.identities_for(no) if (net is not None and no) else repo.identities()
    out += [(f"{i['name']} ({i['ae_title']})", i["id"]) for i in ids]
    return out


def _hora(s: str) -> QTime:
    t = QTime.fromString(s or "", "HH:mm")
    return t if t.isValid() else QTime(7, 0)


class RegraGestaoDialog(QDialog):
    """Uma regra: modalidades (e como), destino (e como), o que mandar, horário e repetição."""

    def __init__(self, repo, net, regra: dict | None = None, parent=None):
        super().__init__(parent)
        self.repo, self.net = repo, net
        self.regra = dict(regra or {"kind": GA.TIPO, "name": "", "active": True, "config": {}})
        cfg = GA.config(self.regra)
        self.setWindowTitle("Regra da gestão automática")
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        topo = QFormLayout()
        self.e_nome = QLineEdit(self.regra.get("name", ""))
        self.e_nome.setPlaceholderText("ex.: Ressonâncias no PACS")
        self.k_ativa = QCheckBox("Ligada")
        self.k_ativa.setChecked(bool(self.regra.get("active", True)))
        hn = QHBoxLayout()
        hn.addWidget(self.e_nome, 1)
        hn.addWidget(self.k_ativa)
        topo.addRow("Nome:", hn)
        # 0.99.36: quem vê a regra (some no modo "só eu")
        from ipe.ui.visivel_para import VisivelPara
        self.visivel = VisivelPara(self.regra if self.regra.get("id") else None, repo,
                                   getattr(net, "settings", None), self)
        if not self.visivel.isHidden():
            topo.addRow("Visível para:", self.visivel)
        lay.addLayout(topo)

        nos = [n for n in repo.nodes(only_active=True) if n.get("kind", "dimse") == "dimse"]
        self.nos = nos
        # --- modalidades
        g1 = QGroupBox("Modalidades (onde os exames foram feitos)")
        v1 = QVBoxLayout(g1)
        self.t_fontes = QTableWidget(len(nos), 3)
        self.t_fontes.setHorizontalHeaderLabels(["Conferir", "Nó", "Como (identidade)"])
        self.t_fontes.verticalHeader().hide()
        marcadas = {f.get("node_id"): f.get("identity_id") for f in cfg.get("fontes") or []}
        for r, n in enumerate(nos):
            it = QTableWidgetItem()
            it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(Qt.Checked if n["id"] in marcadas else Qt.Unchecked)
            it.setData(Qt.UserRole, n["id"])
            self.t_fontes.setItem(r, 0, it)
            self.t_fontes.setItem(r, 1, QTableWidgetItem(f"{n['name']} ({n['ae_title']})"))
            cb = QComboBox()
            for txt, iid in _identidades(repo, net, n):
                cb.addItem(txt, iid)
            cb.setCurrentIndex(max(0, cb.findData(marcadas.get(n["id"]))))
            self.t_fontes.setCellWidget(r, 2, cb)
        self.t_fontes.setColumnWidth(0, 70)
        self.t_fontes.setColumnWidth(1, 260)
        colunas_ajustaveis(self.t_fontes)
        v1.addWidget(self.t_fontes)
        lay.addWidget(g1, 1)

        # --- destino e envio
        g2 = QGroupBox("Para onde e como")
        f2 = QFormLayout(g2)
        self.c_destino = QComboBox()
        for n in nos:
            self.c_destino.addItem(f"{n['name']}  ({n['ae_title']}@{n['host']})", n["id"])
        d = cfg.get("destino") or {}
        alvo = d.get("node_id") or next((n["id"] for n in nos if "PACS" in (n["name"] + n["ae_title"]).upper()), None)
        self.c_destino.setCurrentIndex(max(0, self.c_destino.findData(alvo)))
        self.c_como = QComboBox()
        self.c_destino.currentIndexChanged.connect(lambda _i: self._encher_como(None))
        self._encher_como(d.get("identity_id"))
        self.e_move = QLineEdit(cfg.get("move_destination", ""))
        self.e_move.setPlaceholderText("vazio = o AE do destino")
        self.r_falta = QRadioButton("Só o que falta")
        self.r_inteiro = QRadioButton("O exame inteiro")
        self.r_inteiro.setToolTip("Reenvia o exame todo — só dos exames que não estão completos no destino")
        g_env = QButtonGroup(self)
        g_env.addButton(self.r_falta)
        g_env.addButton(self.r_inteiro)
        (self.r_inteiro if cfg.get("envio") == "inteiro" else self.r_falta).setChecked(True)
        he = QHBoxLayout()
        he.addWidget(self.r_falta)
        he.addWidget(self.r_inteiro)
        he.addWidget(QLabel("(dos exames incompletos ou que não chegaram)"))
        he.addStretch(1)
        self.c_modo = QComboBox()
        for k, txt in G.MODOS_ENVIO.items():
            self.c_modo.addItem(txt, k)
        self.c_modo.setCurrentIndex(max(0, self.c_modo.findData(cfg.get("modo", "auto"))))
        f2.addRow("Destino:", self.c_destino)
        f2.addRow("Enviar como:", self.c_como)
        f2.addRow("Destino do C-MOVE:", self.e_move)
        f2.addRow("Mandar:", he)
        f2.addRow("Como enviar:", self.c_modo)
        lay.addWidget(g2)

        # --- o que conferir
        g3 = QGroupBox("O que conferir")
        f3 = QFormLayout(g3)
        self.c_periodo = QComboBox()
        for txt, k in PERIODOS_AUTO:
            self.c_periodo.addItem(txt, k)
        self.c_periodo.setCurrentIndex(max(0, self.c_periodo.findData(cfg.get("periodo", "hoje"))))
        self.e_modalidade = QLineEdit(cfg.get("modalidade", ""))
        self.e_modalidade.setPlaceholderText("vazio = todas (ex.: MR)")
        self.e_ignorar = QLineEdit(cfg.get("ignorar", ""))
        self.e_ignorar.setPlaceholderText("ex.: Patient Protocol; ScreenCap")
        self.k_exato = QCheckBox("Conferir imagem por imagem (mais lento)")
        self.k_exato.setChecked(bool(cfg.get("exato")))
        hp = QHBoxLayout()
        hp.addWidget(self.c_periodo)
        hp.addWidget(QLabel("Modalidade:"))
        hp.addWidget(self.e_modalidade)
        hp.addStretch(1)
        f3.addRow("Período:", hp)
        f3.addRow("Ignorar séries:", self.e_ignorar)
        f3.addRow("", self.k_exato)
        lay.addWidget(g3)

        # --- horário e repetição
        g4 = QGroupBox("Quando")
        f4 = QFormLayout(g4)
        sch = cfg.get("schedule") or {}
        self.r_intervalo = QRadioButton("A cada")
        self.r_diario = QRadioButton("Todos os dias às")
        g_q = QButtonGroup(self)
        g_q.addButton(self.r_intervalo)
        g_q.addButton(self.r_diario)
        self.s_min = QSpinBox(minimum=5, maximum=1440, value=int(sch.get("minutes", 60)))
        self.s_min.setSuffix(" min")
        self.t_de = QTimeEdit(_hora(sch.get("from", "07:00")))
        self.t_ate = QTimeEdit(_hora(sch.get("to", "20:00")))
        self.t_as = QTimeEdit(_hora(sch.get("at", "19:00")))
        for t in (self.t_de, self.t_ate, self.t_as):
            t.setDisplayFormat("HH:mm")
        (self.r_diario if sch.get("type") == "daily" else self.r_intervalo).setChecked(True)
        h1 = QHBoxLayout()
        for w in (self.r_intervalo, self.s_min, QLabel("entre"), self.t_de, QLabel("e"), self.t_ate):
            h1.addWidget(w)
        h1.addStretch(1)
        h2 = QHBoxLayout()
        h2.addWidget(self.r_diario)
        h2.addWidget(self.t_as)
        h2.addStretch(1)
        dias = set(sch.get("weekdays") if sch.get("weekdays") is not None else range(7))
        self.k_dias = []
        h3 = QHBoxLayout()
        for i, nome in enumerate(DIAS):
            k = QCheckBox(nome)
            k.setChecked(i in dias)
            self.k_dias.append(k)
            h3.addWidget(k)
        h3.addStretch(1)
        rep = cfg.get("repetir") or {}
        self.k_repetir = QCheckBox("Se der erro ou algum nó estiver fora do ar, tentar de novo em")
        self.k_repetir.setChecked(int(rep.get("vezes") or 0) > 0)
        self.s_rep_min = QSpinBox(minimum=1, maximum=720, value=int(rep.get("minutos") or 15))
        self.s_rep_min.setSuffix(" min")
        self.s_rep_vezes = QSpinBox(minimum=1, maximum=20, value=max(1, int(rep.get("vezes") or 3)))
        self.s_rep_vezes.setSuffix(" vez(es)")
        h4 = QHBoxLayout()
        h4.addWidget(self.k_repetir)
        h4.addWidget(self.s_rep_min)
        h4.addWidget(QLabel(", até"))
        h4.addWidget(self.s_rep_vezes)
        h4.addStretch(1)
        f4.addRow(h1)
        f4.addRow(h2)
        f4.addRow("Dias:", h3)
        f4.addRow(h4)
        lay.addWidget(g4)

        bb = QDialogButtonBox()
        bb.addButton("Salvar", QDialogButtonBox.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _encher_como(self, atual) -> None:
        no = self.repo.node(self.c_destino.currentData()) if self.c_destino.currentData() else None
        self.c_como.clear()
        for txt, iid in _identidades(self.repo, self.net, no):
            self.c_como.addItem(txt, iid)
        self.c_como.setCurrentIndex(max(0, self.c_como.findData(atual)))

    def config(self) -> dict:
        fontes = []
        for r in range(self.t_fontes.rowCount()):
            it = self.t_fontes.item(r, 0)
            if it.checkState() == Qt.Checked:
                fontes.append({"node_id": it.data(Qt.UserRole),
                               "identity_id": self.t_fontes.cellWidget(r, 2).currentData()})
        dias = [i for i, k in enumerate(self.k_dias) if k.isChecked()]
        if self.r_diario.isChecked():
            sch = {"type": "daily", "at": self.t_as.time().toString("HH:mm"), "weekdays": dias}
        else:
            sch = {"type": "interval", "minutes": self.s_min.value(), "from": self.t_de.time().toString("HH:mm"),
                   "to": self.t_ate.time().toString("HH:mm"), "weekdays": dias}
        cfg = dict(self.regra.get("config") or {})
        cfg.update({
            "fontes": fontes,
            "destino": {"node_id": self.c_destino.currentData(), "identity_id": self.c_como.currentData()},
            "move_destination": self.e_move.text().strip(), "modalidade": self.e_modalidade.text().strip().upper(),
            "periodo": self.c_periodo.currentData(), "ignorar": self.e_ignorar.text().strip(),
            "exato": self.k_exato.isChecked(), "envio": "inteiro" if self.r_inteiro.isChecked() else "falta",
            "modo": self.c_modo.currentData(), "schedule": sch,
            "repetir": {"minutos": self.s_rep_min.value(),
                        "vezes": self.s_rep_vezes.value() if self.k_repetir.isChecked() else 0}})
        return cfg

    def _ok(self) -> None:
        cfg = self.config()
        if not self.e_nome.text().strip():
            QMessageBox.information(self, "Regra", "Dê um nome à regra.")
            return
        if not cfg["fontes"]:
            QMessageBox.information(self, "Regra", "Marque pelo menos uma modalidade.")
            return
        if not cfg["destino"]["node_id"]:
            QMessageBox.information(self, "Regra", "Escolha o destino.")
            return
        if cfg["destino"]["node_id"] in {f["node_id"] for f in cfg["fontes"]}:
            QMessageBox.information(self, "Regra", "O destino não pode ser uma das modalidades conferidas.")
            return
        if not cfg["schedule"]["weekdays"]:
            QMessageBox.information(self, "Regra", "Marque pelo menos um dia da semana.")
            return
        self.regra.update({"name": self.e_nome.text().strip(), "active": self.k_ativa.isChecked(), "config": cfg})
        if not self.visivel.isHidden():
            self.regra.update(self.visivel.valor())
        self.accept()


def _quando(v) -> str:
    if not v:
        return "—"
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return v
    hoje = datetime.now().date()
    return v.strftime("%H:%M") if v.date() == hoje else v.strftime("%d/%m %H:%M")


class PainelAutomatico(QWidget):
    """A aba "Automático": regras, o último relatório da regra escolhida e o histórico."""

    COLS = ["Ligada", "Regra", "Quando", "Destino", "Mandar", "Última", "Situação", "Próxima"]

    def __init__(self, net, auto, parent=None):
        super().__init__(parent)
        self.net, self.auto = net, auto
        lay = QVBoxLayout(self)
        aviso = QLabel("As regras rodam sozinhas enquanto o programa estiver aberto (também minimizado na "
                       "bandeja). Cada uma confere as modalidades no destino e manda o que não está completo.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color:#9a9a9a")
        lay.addWidget(aviso)
        self.t_regras = QTableWidget(0, len(self.COLS))
        self.t_regras.setHorizontalHeaderLabels(self.COLS)
        self.t_regras.verticalHeader().hide()
        self.t_regras.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_regras.setSelectionMode(QAbstractItemView.SingleSelection)
        self.t_regras.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_regras.itemSelectionChanged.connect(self._mostrar_relatorio)
        self.t_regras.itemChanged.connect(self._ligou)
        self.t_regras.doubleClicked.connect(lambda _i: self.editar())
        for i, w in enumerate((60, 200, 210, 150, 120, 90, 360, 90)):
            self.t_regras.setColumnWidth(i, w)
        colunas_ajustaveis(self.t_regras)
        hb = QHBoxLayout()
        self.b_nova = QPushButton("Nova regra…")
        self.b_nova.clicked.connect(self.nova)
        self.b_editar = QPushButton("Editar…")
        self.b_editar.clicked.connect(self.editar)
        self.b_duplicar = QPushButton("Duplicar")
        self.b_duplicar.clicked.connect(self.duplicar)
        self.b_excluir = QPushButton("Excluir")
        self.b_excluir.clicked.connect(self.excluir)
        self.b_rodar = QPushButton("Rodar agora")
        self.b_rodar.clicked.connect(self.rodar_agora)
        for b in (self.b_nova, self.b_editar, self.b_duplicar, self.b_excluir):
            hb.addWidget(b)
        hb.addStretch(1)
        hb.addWidget(self.b_rodar)
        self.l_estado = QLabel("")
        topo = QWidget()
        vt = QVBoxLayout(topo)
        vt.setContentsMargins(0, 0, 0, 0)
        vt.addWidget(self.t_regras, 1)
        vt.addLayout(hb)

        self.arv = QTreeWidget()
        self.arv.setHeaderLabels(["Última execução da regra escolhida", "Detalhe"])
        self.arv.setColumnWidth(0, 420)
        colunas_ajustaveis(self.arv)
        self.t_hist = QTableWidget(0, 4)
        self.t_hist.setHorizontalHeaderLabels(["Quando", "Regra", "Situação", "Resumo"])
        self.t_hist.verticalHeader().hide()
        self.t_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, w in enumerate((110, 200, 90, 600)):
            self.t_hist.setColumnWidth(i, w)
        colunas_ajustaveis(self.t_hist)
        baixo = QSplitter(Qt.Horizontal)
        baixo.addWidget(self.arv)
        g_h = QGroupBox("Histórico")
        vh = QVBoxLayout(g_h)
        vh.setContentsMargins(4, 4, 4, 4)
        vh.addWidget(self.t_hist)
        baixo.addWidget(g_h)
        split = QSplitter(Qt.Vertical)
        split.addWidget(topo)
        split.addWidget(baixo)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        lay.addWidget(self.l_estado)
        if auto is not None:
            auto.gestao_mudou.connect(self.recarregar)
        self._relogio = QTimer(self)
        self._relogio.setInterval(30_000)
        self._relogio.timeout.connect(self.recarregar)
        self._relogio.start()
        self._enchendo = False
        self.recarregar()

    @property
    def repo(self):
        return self.net.repo

    def regras(self) -> list[dict]:
        # 0.99.36: as do serviço, as suas e as compartilhadas com quem está logado (o administrador, todas)
        return self.repo.rules(GA.TIPO, visiveis=True, gerenciar=True)

    def _destino_txt(self, cfg) -> str:
        no = self.repo.node((cfg.get("destino") or {}).get("node_id"))
        if no is None:
            return "—"
        iid = (cfg.get("destino") or {}).get("identity_id")
        ident = self.repo.identity(iid) if iid else None
        return no["name"] + (f" como {ident['ae_title']}" if ident else "")

    def recarregar(self) -> None:
        atual = self.regra_escolhida()
        rid = atual["id"] if atual else None
        self._enchendo = True
        try:
            rs = self.regras()
            self.t_regras.setRowCount(len(rs))
            for r, regra in enumerate(rs):
                cfg = GA.config(regra)
                ult = cfg.get("_ultimo") or {}
                rodando = self.auto is not None and self.auto.gestao_em_curso(regra["id"])
                sit = "rodando" if rodando else ult.get("situacao", "")
                simb, cor = SIMBOLO.get(sit, ("·", None))
                texto_sit = "rodando agora…" if rodando else (ult.get("resumo") or "ainda não rodou")
                if ult.get("repeticao") and not rodando:
                    texto_sit += f" — nova {ult['repeticao']}"
                marca = QTableWidgetItem()
                marca.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                marca.setCheckState(Qt.Checked if regra["active"] else Qt.Unchecked)
                marca.setData(Qt.UserRole, regra["id"])
                self.t_regras.setItem(r, 0, marca)
                vals = [regra["name"], describe_schedule(cfg.get("schedule") or {}), self._destino_txt(cfg),
                        GA.ENVIOS.get(cfg.get("envio"), ""), _quando(regra.get("last_run")),
                        f"{simb} {texto_sit}", _quando(regra.get("next_run")) if regra["active"] else "desligada"]
                for c, v in enumerate(vals, start=1):
                    it = QTableWidgetItem(v)
                    it.setToolTip(v)
                    if c == 6 and cor:
                        it.setForeground(QBrush(QColor(cor)))
                    self.t_regras.setItem(r, c, it)
            if rid is not None:
                for r in range(self.t_regras.rowCount()):
                    if self.t_regras.item(r, 0).data(Qt.UserRole) == rid:
                        self.t_regras.selectRow(r)
            elif rs:
                self.t_regras.selectRow(0)
        finally:
            self._enchendo = False
        self._mostrar_relatorio()
        self._historico()
        self._botoes()

    def _historico(self) -> None:
        linhas = [j for j in self.repo.job_runs(500) if j["kind"] == "gestao"][:100]
        self.t_hist.setRowCount(len(linhas))
        nomes = {"ok": "✔ ok", "error": "⚠ erro", "offline": "⛔ fora do ar"}
        for r, j in enumerate(linhas):
            for c, v in enumerate((_quando(j["started"]), j["name"], nomes.get(j["status"], j["status"]),
                                   j["message"])):
                it = QTableWidgetItem(v)
                it.setToolTip(v)
                self.t_hist.setItem(r, c, it)

    def regra_escolhida(self) -> dict | None:
        r = self.t_regras.currentRow() if hasattr(self, "t_regras") else -1
        if r < 0 or self.t_regras.item(r, 0) is None:
            return None
        return self.repo.rule(self.t_regras.item(r, 0).data(Qt.UserRole))

    def _botoes(self) -> None:
        regra = self.regra_escolhida()
        for b in (self.b_editar, self.b_duplicar, self.b_excluir):
            b.setEnabled(regra is not None)
        rodando = regra is not None and self.auto is not None and self.auto.gestao_em_curso(regra["id"])
        self.b_rodar.setEnabled(regra is not None and self.auto is not None and not rodando)

    def _mostrar_relatorio(self) -> None:
        self.arv.clear()
        regra = self.regra_escolhida()
        self._botoes()
        if regra is None:
            return
        ult = GA.config(regra).get("_ultimo") or {}
        if not ult:
            QTreeWidgetItem(self.arv, ["Ainda não rodou.", ""])
            return
        cab = QTreeWidgetItem(self.arv, [f"{_quando(ult.get('inicio'))} — {ult.get('resumo', '')}", ""])
        cab.setToolTip(0, ult.get("resumo", ""))

        def grupo(titulo, itens, cor=None, detalhe=lambda d: d.get("mensagem", "")):
            g = QTreeWidgetItem(self.arv, [f"{titulo} ({len(itens)})", ""])
            if cor:
                g.setForeground(0, QBrush(QColor(cor)))
            for d in itens:
                if isinstance(d, str):
                    QTreeWidgetItem(g, [d.split(":")[0], d])
                    continue
                QTreeWidgetItem(g, [f"{d.get('paciente', '')}  {d.get('accession', '')}  ({d.get('fonte', '')})",
                                    detalhe(d)])
            g.setExpanded(bool(itens) and titulo != "Completados agora")
            return g
        if ult.get("destino_offline"):
            grupo("Destino fora do ar", [ult.get("erro", "")], "#ffb74d")
        grupo("Completados agora", ult.get("enviados") or [], "#7fd07f")
        grupo("Com erro", ult.get("falhas") or [], "#ff8a80")
        grupo("Modalidades fora do ar", ult.get("offline") or [], "#ffb74d")
        grupo("Mesmo accession com outro Study UID (não enviados)", ult.get("outro_uid") or [], None,
              lambda d: "confira no destino antes de mandar")
        self.arv.expandItem(cab)

    def _ligou(self, item) -> None:
        if self._enchendo or item.column() != 0:
            return
        rid = item.data(Qt.UserRole)
        on = item.checkState() == Qt.Checked
        dados = {"id": rid, "active": on}
        if on:
            from ipe.automation.rules import next_run
            regra = self.repo.rule(rid)
            dados["next_run"] = next_run((regra or {}).get("config", {}).get("schedule", {}), datetime.now())
        self.repo.save_rule(dados)
        self.recarregar()

    def _gravar(self, regra: dict) -> int:
        from ipe.automation.rules import next_run
        regra["kind"] = GA.TIPO
        if regra.get("active"):
            regra["next_run"] = next_run(regra["config"].get("schedule", {}), datetime.now())
        rid = self.repo.save_rule(regra)
        self.recarregar()
        return rid

    def nova(self):
        dlg = RegraGestaoDialog(self.repo, self.net, None, self)
        if dlg.exec():
            return self._gravar(dlg.regra)
        return None

    def editar(self):
        regra = self.regra_escolhida()
        if regra is None:
            return None
        dlg = RegraGestaoDialog(self.repo, self.net, regra, self)
        if dlg.exec():
            return self._gravar(dlg.regra)
        return None

    def duplicar(self):
        regra = self.regra_escolhida()
        if regra is None:
            return None
        from ipe.ui.print_settings import nome_de_copia
        from ipe.auth import visibilidade as V
        copia = {"kind": GA.TIPO, "name": nome_de_copia(regra["name"], [r["name"] for r in self.regras()]),
                 "active": False, "config": {k: v for k, v in regra["config"].items()
                                             if not k.startswith("_") and k not in ("dono", "visivel_para")},
                 **V.padrao_novo()}                       # a cópia é de quem copiou
        if V.visao_atual() is None:
            copia.pop("dono"), copia.pop("visivel_para")
        return self._gravar(copia)

    def excluir(self) -> None:
        regra = self.regra_escolhida()
        if regra is None:
            return
        if QMessageBox.question(self, "Gestão automática", f"Excluir a regra “{regra['name']}”?") \
                != QMessageBox.Yes:
            return
        self.repo.delete_rule(regra["id"])
        self.recarregar()

    def rodar_agora(self) -> None:
        regra = self.regra_escolhida()
        if regra is None or self.auto is None:
            return
        if self.auto.rodar_gestao(regra, manual=True):
            self.l_estado.setText(f"“{regra['name']}” rodando… o resultado aparece aqui quando terminar.")
        self.recarregar()
