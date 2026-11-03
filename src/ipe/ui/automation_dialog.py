"""Automação: buscas agendadas, pré-busca de anteriores, roteamento, limpeza e histórico."""

from __future__ import annotations

import copy

from PySide6.QtCore import QDateTime, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from ipe.automation import retention
from ipe.automation.rules import (
    DEFAULT_DINAMICA, DEFAULT_QUERY, DEFAULT_RETENTION, DEFAULT_ROUTE, describe_schedule, next_run,
)
from ipe.ui.tabelas import colunas_ajustaveis

MODS = ["", "CT", "MR", "MG", "US", "CR", "DX", "PT", "NM", "XA", "OT"]
DAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _table(headers: list[str], stretch: int = 0) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(stretch, QHeaderView.Stretch)
    return t
    colunas_ajustaveis(t)


def _fill(t: QTableWidget, rows: list[list[str]], ids: list | None = None) -> None:
    t.setRowCount(len(rows))
    for r, vals in enumerate(rows):
        for c, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            if ids is not None:
                it.setData(Qt.UserRole, ids[r])
            t.setItem(r, c, it)
    t.resizeColumnsToContents()


def _selected_id(t: QTableWidget):
    r = t.currentRow()
    return t.item(r, 0).data(Qt.UserRole) if r >= 0 and t.item(r, 0) else None


def _fmt(dt) -> str:
    return f"{dt:%d/%m %H:%M}" if dt else ""


def _node_combo(repo, current, all_label: str | None = "Todos os nós de busca") -> QComboBox:
    c = QComboBox()
    if all_label:
        c.addItem(all_label, None)
    for n in repo.nodes():
        c.addItem(f"{n['name']} ({n['ae_title']})", n["id"])
    c.setCurrentIndex(max(0, c.findData(current)))
    return c


def _ident_combo(repo, current) -> QComboBox:
    c = QComboBox()
    c.addItem("Este programa", None)
    for i in repo.identities():
        c.addItem(f"{i['name']} ({i['ae_title']})", i["id"])
    c.setCurrentIndex(max(0, c.findData(current)))
    return c


def _ok_cancel(dlg, form) -> None:
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    form.addRow(bb)


# ---------------------------------------------------------------------------
class QueryRuleDialog(QDialog):
    def __init__(self, repo, rule: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Busca agendada")
        self.rule = copy.deepcopy(rule) if rule else {"kind": "query", "name": "", "active": True,
                                                        "config": copy.deepcopy(DEFAULT_QUERY)}
        c = self.rule["config"]
        f = QFormLayout(self)
        self.name = QLineEdit(self.rule["name"], placeholderText="Ex.: Mamografias do dia")
        self.active = QCheckBox("Ativa")
        self.active.setChecked(self.rule.get("active", True))
        self.node = _node_combo(repo, c.get("node_id"))
        self.ident = _ident_combo(repo, c.get("identity_id"))
        fl = c.get("filters", {})
        self.pname = QLineEdit(fl.get("name", ""))
        self.pid = QLineEdit(fl.get("patient_id", ""))
        self.acc = QLineEdit(fl.get("accession", ""))
        self.desc = QLineEdit(fl.get("description", ""), placeholderText="Ex.: *MAMA*")
        self.mod = QComboBox()
        self.mod.addItems([m or "Todas" for m in MODS])
        self.mod.setCurrentIndex(max(0, MODS.index(fl.get("modality", "")) if fl.get("modality", "") in MODS else 0))
        self.period = QComboBox()
        for label, data in (("Hoje", "today"), ("Últimas N horas", "last_hours"), ("Últimos N dias", "last_days"),
                            ("Qualquer data", "any")):
            self.period.addItem(label, data)
        spec = c.get("date", "today")
        self.period.setCurrentIndex(max(0, self.period.findData(spec.split(":")[0])))
        self.period_n = QSpinBox(minimum=1, maximum=3650, value=int(spec.split(":")[1]) if ":" in spec else 24)
        sc = c.get("schedule", {})
        self.stype = QComboBox()
        for label, data in (("A cada N minutos, numa janela de horário", "interval"),
                            ("Diariamente num horário", "daily"), ("Uma vez", "once")):
            self.stype.addItem(label, data)
        self.stype.setCurrentIndex(max(0, self.stype.findData(sc.get("type", "interval"))))
        self.minutes = QSpinBox(minimum=1, maximum=1440, value=int(sc.get("minutes", 10)), suffix=" min")
        self.t_from = QTimeEdit(QTime.fromString(sc.get("from", "07:00"), "HH:mm"))
        self.t_to = QTimeEdit(QTime.fromString(sc.get("to", "19:00"), "HH:mm"))
        self.at = QTimeEdit(QTime.fromString(sc.get("at", "06:00") if sc.get("type") == "daily" else "06:00", "HH:mm"))
        self.once = QDateTimeEdit(QDateTime.fromString(sc.get("at", ""), "yyyy-MM-dd HH:mm")
                                  if sc.get("type") == "once" else QDateTime.currentDateTime().addSecs(3600))
        self.once.setDisplayFormat("dd/MM/yyyy HH:mm")
        days_w = QWidget()
        dl = QHBoxLayout(days_w)
        dl.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for i, d in enumerate(DAYS):
            cb = QCheckBox(d)
            cb.setChecked(i in (sc.get("weekdays") or range(7)))
            dl.addWidget(cb)
            self.days.append(cb)
        self.action = QComboBox()
        self.action.addItem("Baixar os exames novos", "download")
        self.action.addItem("Só avisar", "notify")
        self.action.setCurrentIndex(max(0, self.action.findData(c.get("action", "download"))))
        self.to_list = QComboBox()
        self.to_list.addItem("(nenhuma)", None)
        for lid, name, _k, _n in repo.case_lists():
            self.to_list.addItem(name, lid)
        self.to_list.setCurrentIndex(max(0, self.to_list.findData(c.get("add_to_list"))))
        self.max = QSpinBox(minimum=1, maximum=1000, value=int(c.get("max_studies", 50)))
        per = QHBoxLayout()
        per.addWidget(self.period, 1)
        per.addWidget(self.period_n)
        win = QHBoxLayout()
        win.addWidget(self.minutes)
        win.addWidget(QLabel("das"))
        win.addWidget(self.t_from)
        win.addWidget(QLabel("às"))
        win.addWidget(self.t_to)
        for lab, w in (("Nome:", self.name), ("", self.active), ("Nó:", self.node), ("Buscar como:", self.ident),
                       ("Paciente:", self.pname), ("ID:", self.pid), ("Accession:", self.acc),
                       ("Descrição:", self.desc), ("Modalidade:", self.mod), ("Período do exame:", per),
                       ("Quando:", self.stype), ("Intervalo:", win), ("Diariamente às:", self.at),
                       ("Uma vez em:", self.once), ("Dias da semana:", days_w), ("Ação:", self.action),
                       ("Pôr na lista:", self.to_list), ("Máximo de exames por vez:", self.max)):
            f.addRow(lab, w) if not isinstance(w, (QHBoxLayout,)) else f.addRow(lab, w)
        f.addRow(QLabel("<i>Só baixa o que ainda não está no computador. As buscas rodam com o "
                        "programa aberto (ou minimizado na bandeja).</i>"))
        _ok_cancel(self, f)

    def result_rule(self) -> dict:
        c = self.rule["config"]
        c["node_id"] = self.node.currentData()
        c["identity_id"] = self.ident.currentData()
        mod = MODS[self.mod.currentIndex()]
        c["filters"] = {"name": self.pname.text().strip(), "patient_id": self.pid.text().strip(),
                        "accession": self.acc.text().strip(), "description": self.desc.text().strip(),
                        "modality": mod}
        p = self.period.currentData()
        c["date"] = f"{p}:{self.period_n.value()}" if p in ("last_hours", "last_days") else p
        st = self.stype.currentData()
        wd = [i for i, cb in enumerate(self.days) if cb.isChecked()]
        if st == "interval":
            c["schedule"] = {"type": "interval", "minutes": self.minutes.value(),
                             "from": self.t_from.time().toString("HH:mm"), "to": self.t_to.time().toString("HH:mm"),
                             "weekdays": wd}
        elif st == "daily":
            c["schedule"] = {"type": "daily", "at": self.at.time().toString("HH:mm"), "weekdays": wd}
        else:
            c["schedule"] = {"type": "once", "at": self.once.dateTime().toString("yyyy-MM-dd HH:mm")}
        c["action"] = self.action.currentData()
        c["add_to_list"] = self.to_list.currentData()
        c["max_studies"] = self.max.value()
        self.rule["name"] = self.name.text().strip() or "Busca agendada"
        self.rule["active"] = self.active.isChecked()
        from datetime import datetime
        self.rule["next_run"] = next_run(c["schedule"], datetime.now())
        return self.rule


class PriorRuleDialog(QDialog):
    def __init__(self, rule: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regra de pré-busca de anteriores")
        self.rule = copy.deepcopy(rule) if rule else {
            "kind": "prior", "name": "", "active": True,
            "config": {"current": [], "fetch": [], "count": 1, "years": 3, "keywords": [],
                       "on_receive": True, "on_open": True}}
        c = self.rule["config"]
        f = QFormLayout(self)
        self.name = QLineEdit(self.rule["name"])
        self.active = QCheckBox("Ativa")
        self.active.setChecked(self.rule.get("active", True))
        self.current = QLineEdit(", ".join(c.get("current", [])), placeholderText="Ex.: MR")
        self.fetch = QLineEdit(", ".join(c.get("fetch", [])), placeholderText="Ex.: MR, MG")
        self.count = QSpinBox(minimum=1, maximum=20, value=int(c.get("count", 1)))
        self.years = QSpinBox(minimum=1, maximum=30, value=int(float(c.get("years", 3))), suffix=" anos")
        self.kw = QLineEdit(", ".join(c.get("keywords", [])), placeholderText="Ex.: mama (vale para a mesma modalidade)")
        self.on_recv = QCheckBox("Quando o exame chega (recebido ou baixado)")
        self.on_recv.setChecked(bool(c.get("on_receive", True)))
        self.on_open = QCheckBox("Quando o exame é aberto")
        self.on_open.setChecked(bool(c.get("on_open", True)))
        for lab, w in (("Nome:", self.name), ("", self.active), ("Exame atual (modalidades):", self.current),
                       ("Buscar anteriores de:", self.fetch), ("Quantos de cada modalidade:", self.count),
                       ("Até:", self.years), ("Palavras-chave na descrição:", self.kw),
                       ("", self.on_recv), ("", self.on_open)):
            f.addRow(lab, w)
        _ok_cancel(self, f)

    def result_rule(self) -> dict:
        split = lambda s: [x.strip().upper() for x in s.replace(";", ",").split(",") if x.strip()]  # noqa: E731
        self.rule["name"] = self.name.text().strip() or "Anteriores"
        self.rule["active"] = self.active.isChecked()
        self.rule["config"].update({"current": split(self.current.text()), "fetch": split(self.fetch.text()),
                                    "count": self.count.value(), "years": self.years.value(),
                                    "keywords": [k.strip() for k in self.kw.text().split(",") if k.strip()],
                                    "on_receive": self.on_recv.isChecked(), "on_open": self.on_open.isChecked()})
        return self.rule


class DinamicaRuleDialog(QDialog):
    """Regra de dinâmica pronta: só filtro. Não há destino, porque nada sai daqui."""

    def __init__(self, rule: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dinâmica pronta na chegada")
        self.rule = copy.deepcopy(rule) if rule else {"kind": "dinamica", "name": "", "active": True,
                                                      "config": copy.deepcopy(DEFAULT_DINAMICA)}
        c = self.rule["config"]
        f = QFormLayout(self)
        self.name = QLineEdit(self.rule["name"], placeholderText="Ex.: RM de mama pronta para abrir")
        self.active = QCheckBox("Ativa")
        self.active.setChecked(self.rule.get("active", True))
        self.mods = QLineEdit(", ".join(c.get("modalities", [])), placeholderText="vazio = todas")
        self.desc = QLineEdit(c.get("description_contains", ""), placeholderText="Ex.: mama")
        aviso = QLabel("Nada é gravado como série e nada é enviado: o programa só adianta a "
                       "leitura dos arquivos.")
        aviso.setWordWrap(True)
        for lab, w in (("Nome:", self.name), ("", self.active), ("Modalidades:", self.mods),
                       ("Descrição contém:", self.desc), ("", aviso)):
            f.addRow(lab, w)
        _ok_cancel(self, f)

    def result_rule(self) -> dict:
        self.rule["name"] = self.name.text().strip() or "Dinâmica pronta"
        self.rule["active"] = self.active.isChecked()
        self.rule["config"].update({
            "modalities": [m.strip().upper() for m in self.mods.text().split(",") if m.strip()],
            "description_contains": self.desc.text().strip()})
        return self.rule


class RouteRuleDialog(QDialog):
    def __init__(self, repo, rule: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regra de roteamento")
        self.rule = copy.deepcopy(rule) if rule else {"kind": "route", "name": "", "active": True,
                                                        "config": copy.deepcopy(DEFAULT_ROUTE)}
        c = self.rule["config"]
        f = QFormLayout(self)
        self.name = QLineEdit(self.rule["name"], placeholderText="Ex.: RM de mama para a estação de IA")
        self.active = QCheckBox("Ativa")
        self.active.setChecked(self.rule.get("active", True))
        self.mods = QLineEdit(", ".join(c.get("modalities", [])), placeholderText="vazio = todas")
        self.desc = QLineEdit(c.get("description_contains", ""), placeholderText="Ex.: mama")
        self.recv = QCheckBox("Exames recebidos (enviados por outros nós)")
        self.recv.setChecked("received" in c.get("origins", []))
        self.retr = QCheckBox("Exames baixados por este programa")
        self.retr.setChecked("retrieved" in c.get("origins", []))
        self.node = _node_combo(repo, c.get("node_id"), None)
        self.ident = _ident_combo(repo, c.get("identity_id"))
        for lab, w in (("Nome:", self.name), ("", self.active), ("Modalidades:", self.mods),
                       ("Descrição contém:", self.desc), ("Origem:", self.recv), ("", self.retr),
                       ("Enviar para:", self.node), ("Enviar como:", self.ident)):
            f.addRow(lab, w)
        _ok_cancel(self, f)

    def result_rule(self) -> dict:
        self.rule["name"] = self.name.text().strip() or "Roteamento"
        self.rule["active"] = self.active.isChecked()
        self.rule["config"].update({
            "modalities": [m.strip().upper() for m in self.mods.text().split(",") if m.strip()],
            "description_contains": self.desc.text().strip(),
            "origins": [o for o, cb in (("received", self.recv), ("retrieved", self.retr)) if cb.isChecked()],
            "node_id": self.node.currentData(), "identity_id": self.ident.currentData()})
        return self.rule


# ---------------------------------------------------------------------------
class AutomationDialog(QDialog):
    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main, self.repo, self.auto = main, main.repo, main.auto
        self.setWindowTitle("Automação")
        self.resize(1000, 640)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._rules_tab("query"), "Buscas agendadas")
        self.tabs.addTab(self._rules_tab("prior"), "Anteriores")
        self.tabs.addTab(self._rules_tab("route"), "Roteamento")
        self.tabs.addTab(self._rules_tab("dinamica"), "Dinâmica pronta")
        self.tabs.addTab(self._clean_tab(), "Limpeza")
        self.tabs.addTab(self._history_tab(), "Histórico")
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        from ipe.ui.janelas import rolar_abas
        rolar_abas(self.tabs)                  # 0.99.32: a janela diminui (cada aba rola)
        lay.addWidget(self.tabs)
        lay.addWidget(bb)
        self.auto.changed.connect(self._refresh_all)

    # ------------------------------------------------------------ regras
    HEADERS = {
        "query": ["Nome", "Nó", "Filtro", "Quando", "Ação", "Ativa", "Próxima", "Última"],
        "prior": ["Nome", "Exame atual", "Buscar", "Qtde", "Anos", "Palavras-chave", "Ao chegar", "Ao abrir", "Ativa"],
        "route": ["Nome", "Modalidades", "Descrição contém", "Origem", "Destino", "Ativa"],
        "dinamica": ["Nome", "Modalidades", "Descrição contém", "Ativa"],
    }
    DICA_DINAMICA = ("Exame que chega e bate com o filtro tem as fases da dinâmica detectadas e os "
                     "quadros decodificados em segundo plano, para a dinâmica abrir na hora. "
                     "Nada é gravado como série e nada é enviado: é só trabalho adiantado. O "
                     "pré-cálculo para sozinho quando enche a parte reservada do cache de imagens, "
                     "para não expulsar o exame que você está lendo.")

    def _rules_tab(self, kind: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        hint = {"query": "Buscas feitas sozinhas no PACS, no horário escolhido. Ex.: mamografias do dia a cada 10 min.",
                "prior": "Ao chegar ou abrir um exame, o programa busca no PACS os exames anteriores do paciente "
                         "segundo estas regras (a primeira que servir). Os anteriores trazidos assim podem ter "
                         "prazo próprio na limpeza.",
                "route": "Exames que chegam e batem com o filtro são reenviados para outro nó "
                         "(ex.: estação de IA).",
                "dinamica": self.DICA_DINAMICA}[kind]
        lab = QLabel(hint)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        t = _table(self.HEADERS[kind])
        t.doubleClicked.connect(lambda _: self._edit(kind))
        setattr(self, f"t_{kind}", t)
        lay.addWidget(t, 1)
        row = QHBoxLayout()
        buttons = [("Adicionar…", lambda: self._edit(kind, new=True)), ("Editar…", lambda: self._edit(kind)),
                   ("Excluir", lambda: self._delete(kind)), ("Ativar / pausar", lambda: self._toggle(kind))]
        if kind == "query":
            buttons.append(("Executar agora", self._run_now))
        for text, fn in buttons:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self._fill_rules(kind)
        return w

    def _fill_rules(self, kind: str) -> None:
        rules = self.repo.rules(kind)
        nodes = {n["id"]: n["name"] for n in self.repo.nodes()}
        rows = []
        for r in rules:
            c = r["config"]
            on = "sim" if r["active"] else "pausada"
            if kind == "query":
                fl = ", ".join(f"{v}" for v in (c.get("filters") or {}).values() if v) or "—"
                per = {"today": "hoje", "any": "qualquer data"}.get(c.get("date", ""), c.get("date", ""))
                rows.append([r["name"], nodes.get(c.get("node_id"), "todos de busca"), f"{fl}; {per}",
                             describe_schedule(c.get("schedule", {})),
                             "baixar" if c.get("action") == "download" else "avisar", on,
                             _fmt(r["next_run"]) if r["active"] else "", _fmt(r["last_run"])])
            elif kind == "prior":
                rows.append([r["name"], ", ".join(c.get("current", [])), ", ".join(c.get("fetch", [])),
                             c.get("count", 1), c.get("years", ""), ", ".join(c.get("keywords", [])),
                             "sim" if c.get("on_receive", True) else "", "sim" if c.get("on_open", True) else "", on])
            elif kind == "dinamica":
                rows.append([r["name"], ", ".join(c.get("modalities", [])) or "todas",
                             c.get("description_contains", ""), on])
            else:
                rows.append([r["name"], ", ".join(c.get("modalities", [])) or "todas",
                             c.get("description_contains", ""),
                             ", ".join({"received": "recebidos", "retrieved": "baixados"}[o] for o in c.get("origins", [])),
                             nodes.get(c.get("node_id"), "?"), on])
        _fill(getattr(self, f"t_{kind}"), rows, [r["id"] for r in rules])

    def _edit(self, kind: str, new: bool = False) -> None:
        rid = None if new else _selected_id(getattr(self, f"t_{kind}"))
        if not new and rid is None:
            return
        rule = self.repo.rule(rid) if rid else None
        dlg = {"query": lambda: QueryRuleDialog(self.repo, rule, self),
               "prior": lambda: PriorRuleDialog(rule, self),
               "route": lambda: RouteRuleDialog(self.repo, rule, self),
               "dinamica": lambda: DinamicaRuleDialog(rule, self)}[kind]()
        if dlg.exec():
            r = dlg.result_rule()
            if kind == "route" and not r["config"].get("node_id"):
                QMessageBox.warning(self, "Roteamento", "Escolha o nó de destino.")
                return
            self.repo.save_rule(r)
            self._fill_rules(kind)

    def _delete(self, kind: str) -> None:
        rid = _selected_id(getattr(self, f"t_{kind}"))
        if rid and QMessageBox.question(self, "Excluir", "Excluir esta regra?") == QMessageBox.Yes:
            self.repo.delete_rule(rid)
            self._fill_rules(kind)

    def _toggle(self, kind: str) -> None:
        rid = _selected_id(getattr(self, f"t_{kind}"))
        r = self.repo.rule(rid) if rid else None
        if r is None:
            return
        from datetime import datetime
        upd = {"id": rid, "active": not r["active"]}
        if kind == "query" and not r["active"]:
            upd["next_run"] = next_run(r["config"].get("schedule", {}), datetime.now())
        self.repo.save_rule(upd)
        self._fill_rules(kind)

    def _run_now(self) -> None:
        rid = _selected_id(self.t_query)
        r = self.repo.rule(rid) if rid else None
        if r is not None:
            self.auto.run_query(r)
            self._fill_rules("query")

    # ------------------------------------------------------------ limpeza
    def _clean_tab(self) -> QWidget:
        pol = self.auto.policy
        w = QWidget()
        lay = QHBoxLayout(w)
        form_w = QWidget()
        f = QFormLayout(form_w)
        self.r_enabled = QCheckBox("Limpeza automática ligada (uma vez por dia e quando o disco enche)")
        self.r_enabled.setChecked(bool(pol.get("enabled")))
        self.r_only_net = QCheckBox("Só exames que vieram da rede (não os importados à mão)")
        self.r_only_net.setChecked(bool(pol.get("only_network", True)))
        self.r_age = QSpinBox(minimum=0, maximum=3650, value=int(pol.get("max_age_days") or 0), suffix=" dias")
        self.r_age.setSpecialValueText("não usar")
        self.r_unopened = QSpinBox(minimum=0, maximum=3650, value=int(pol.get("not_opened_days") or 0), suffix=" dias")
        self.r_unopened.setSpecialValueText("não usar")
        self.r_prefetch = QSpinBox(minimum=0, maximum=3650, value=int(pol.get("prefetch_days") or 0), suffix=" dias")
        self.r_prefetch.setSpecialValueText("não usar")
        self.r_mod = QLineEdit(", ".join(f"{k}={v}" for k, v in (pol.get("per_modality_days") or {}).items()),
                               placeholderText="Ex.: CT=7, MG=90")
        self.r_high = QSpinBox(minimum=0, maximum=99, value=int(pol.get("disk_high_pct") or 0), suffix=" %")
        self.r_low = QSpinBox(minimum=0, maximum=99, value=int(pol.get("disk_low_pct") or 0), suffix=" %")
        self.r_max = QSpinBox(minimum=0, maximum=100000, value=int(pol.get("max_storage_gb") or 0), suffix=" GB")
        self.r_max.setSpecialValueText("sem teto")
        self.r_trash = QSpinBox(minimum=0, maximum=365, value=int(pol.get("trash_days") or 7), suffix=" dias")
        pct, _t = retention.disk_usage(self.main.paths.storage)
        for lab, wd in (("", self.r_enabled), ("", self.r_only_net), ("Recebidos há mais de:", self.r_age),
                        ("Não abertos há mais de:", self.r_unopened), ("Anteriores da pré-busca após:", self.r_prefetch),
                        ("Por modalidade (dias):", self.r_mod), ("Disco acima de:", self.r_high),
                        ("…apagar até voltar a:", self.r_low), ("Teto do armazenamento:", self.r_max),
                        ("Lixeira guarda por:", self.r_trash)):
            f.addRow(lab, wd)
        f.addRow(QLabel(f"Disco agora: {pct:.0f}% usado"))
        f.addRow(QLabel("<b>Nunca apaga:</b> estudos protegidos (cadeado), em listas, com comentário, "
                        "imagem-chave, medidas ou diagnóstico, e os que estão abertos."))
        f.itemAt(f.rowCount() - 1, QFormLayout.SpanningRole).widget().setWordWrap(True)
        b_save = QPushButton("Salvar política")
        b_save.clicked.connect(self._save_policy)
        b_sim = QPushButton("Simular agora")
        b_sim.clicked.connect(self._simulate)
        b_run = QPushButton("Limpar agora…")
        b_run.clicked.connect(self._clean_now)
        row = QHBoxLayout()
        for b in (b_save, b_sim, b_run):
            row.addWidget(b)
        f.addRow(row)
        lay.addWidget(form_w, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Simulação</b> (o que seria apagado)"))
        self.t_sim = _table(["Paciente", "Descrição", "Tamanho", "Motivo"], 3)
        right.addWidget(self.t_sim, 1)
        right.addWidget(QLabel("<b>Lixeira</b>"))
        self.t_trash = _table(["Quando", "Paciente", "Descrição", "Motivo"], 3)
        right.addWidget(self.t_trash, 1)
        tr = QHBoxLayout()
        b_rest = QPushButton("Restaurar selecionado")
        b_rest.clicked.connect(self._restore)
        b_empty = QPushButton("Esvaziar lixeira…")
        b_empty.clicked.connect(self._empty_trash)
        tr.addWidget(b_rest)
        tr.addWidget(b_empty)
        tr.addStretch(1)
        right.addLayout(tr)
        rw = QWidget()
        rw.setLayout(right)
        lay.addWidget(rw, 1)
        self._fill_trash()
        return w

    def _policy_from_form(self) -> dict:
        per = {}
        for part in self.r_mod.text().replace(";", ",").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    per[k.strip().upper()] = int(v.strip())
                except ValueError:
                    pass
        return {**DEFAULT_RETENTION, "enabled": self.r_enabled.isChecked(), "only_network": self.r_only_net.isChecked(),
                "max_age_days": self.r_age.value(), "not_opened_days": self.r_unopened.value(),
                "prefetch_days": self.r_prefetch.value(), "per_modality_days": per,
                "disk_high_pct": self.r_high.value(), "disk_low_pct": self.r_low.value(),
                "max_storage_gb": self.r_max.value(), "trash_days": self.r_trash.value()}

    def _save_policy(self) -> None:
        self.main.settings.set("retention", self._policy_from_form())
        self.main.settings.save()
        QMessageBox.information(self, "Limpeza", "Política salva.")

    def _simulate(self) -> None:
        self.main.settings.set("retention", self._policy_from_form())
        items = self.auto.preview_retention()
        _fill(self.t_sim, [[s.patient, s.description, f"{s.size_bytes / 1024 ** 2:.0f} MB", reason]
                           for s, reason in items])
        if not items:
            QMessageBox.information(self, "Simulação", "Nada seria apagado com esta política.")

    def _clean_now(self) -> None:
        self.main.settings.set("retention", self._policy_from_form())
        items = self.auto.preview_retention()
        if not items:
            QMessageBox.information(self, "Limpeza", "Nada a apagar com esta política.")
            return
        if QMessageBox.question(self, "Limpeza", f"Mover {len(items)} estudo(s) para a lixeira?") != QMessageBox.Yes:
            return
        n = self.auto.run_retention(force=True)
        self.main.settings.save()
        self._simulate()
        self._fill_trash()
        self.main.statusBar().showMessage(f"{n} estudo(s) movido(s) para a lixeira.", 8000)

    def _fill_trash(self) -> None:
        self._trash = retention.trash_entries(self.auto.trash_root)
        _fill(self.t_trash, [[e.get("at", "")[:16].replace("T", " "), e.get("patient", ""), e.get("description", ""),
                              e.get("reason", "")] for e in self._trash], list(range(len(self._trash))))

    def _restore(self) -> None:
        i = _selected_id(self.t_trash)
        if i is None:
            return
        n = retention.restore(self.repo, self.main.db, self.main.paths.storage, self._trash[i])
        self._fill_trash()
        self.main.browser.refresh()
        QMessageBox.information(self, "Lixeira", f"{n} imagem(ns) restaurada(s).")

    def _empty_trash(self) -> None:
        if QMessageBox.question(self, "Lixeira", "Apagar de vez tudo o que está na lixeira?") == QMessageBox.Yes:
            retention.purge(self.repo, self.auto.trash_root, -1)
            self._fill_trash()

    # ------------------------------------------------------------ histórico
    def _history_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<b>Execuções</b>"))
        self.t_runs = _table(["Início", "Tipo", "Regra", "Situação", "Itens", "Detalhe"], 5)
        lay.addWidget(self.t_runs, 2)
        lay.addWidget(QLabel("<b>Exclusões</b>"))
        self.t_del = _table(["Quando", "Ação", "Paciente", "Descrição", "Motivo"], 4)
        lay.addWidget(self.t_del, 1)
        self._fill_history()
        return w

    def _fill_history(self) -> None:
        kinds = {"query": "busca", "prior": "anteriores", "route": "roteamento", "clean": "limpeza",
                 "dinamica": "dinâmica pronta"}
        _fill(self.t_runs, [[f"{r['started']:%d/%m %H:%M:%S}", kinds.get(r["kind"], r["kind"]), r["name"],
                             "ok" if r["status"] == "ok" else "erro", r["items"], r["message"]]
                            for r in self.repo.job_runs()])
        acts = {"trash": "lixeira", "purge": "apagado", "restore": "restaurado"}
        _fill(self.t_del, [[f"{d['at']:%d/%m %H:%M}", acts.get(d["action"], d["action"]), d["patient"],
                            d["description"], d["reason"]] for d in self.repo.deletion_log()])

    def _refresh_all(self) -> None:
        if not self.isVisible():
            return
        for k in ("query", "prior", "route", "dinamica"):
            self._fill_rules(k)
        self._fill_history()
