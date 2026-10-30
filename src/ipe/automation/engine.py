"""Motor de automação: roda enquanto o programa está aberto (também minimizado na bandeja).

- a cada 30 s confere as buscas agendadas vencidas;
- exames que chegam (C-STORE) ou terminam de baixar disparam a pré-busca de
  anteriores e o roteamento (esperando o exame terminar de chegar);
- abrir um exame também dispara a pré-busca;
- a limpeza roda uma vez por dia e sempre que o disco passar do limite (checado a cada hora).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

from PySide6.QtCore import QObject, QTimer, Signal

from ipe.network import nodes as NODES
from ipe.automation import retention
from ipe.automation.rules import (
    DEFAULT_PRIORS, DEFAULT_RETENTION, date_range, next_run, prior_rule_for, route_matches, select_priors,
)

log = logging.getLogger(__name__)
QUIET_SECONDS = 15          # exame "terminou de chegar" depois deste tempo sem imagens novas


class AutomationEngine(QObject):
    notify = Signal(str, str)        # título, texto
    changed = Signal()
    implante_corrigido = Signal(str)   # estudo que ganhou cópias sem implante (0.97)
    segmentacao_pronta = Signal(str, object)   # estudo, saída da segmentação de órgãos automática (0.99)
    gestao_mudou = Signal()                    # 0.99.6: uma regra da gestão automática rodou ou começou

    def __init__(self, repo, db, net, settings, paths, open_uids=lambda: set(), parent=None,
                 cache=None):
        super().__init__(parent)
        self.repo, self.db, self.net, self.settings, self.paths = repo, db, net, settings, paths
        self.open_uids = open_uids
        self.cache = cache               # cache de quadros do visualizador (pré-cálculo da dinâmica)
        self.trash_root = paths.data / "Lixeira"
        self._arriving: dict[str, float] = {}         # estudo -> última imagem recebida
        self._recent_prefetch: dict[str, float] = {}  # estudo -> quando buscou anteriores
        self._job_tags: dict[int, dict] = {}          # tarefa de download -> o que fazer ao terminar
        self._implante_rodando: set[str] = set()      # exames com a correção do implante em curso
        self._seg_fila: list[tuple] = []               # (exame, "abdome"|"coluna") esperando o TotalSegmentator
        self._seg_simular = False                      # testes: o trabalhador devolve rótulos conhecidos
        self._gestao_rodando: set[int] = set()        # regras da gestão automática em curso (0.99.6)
        self._gestao_tentativas: dict[int, int] = {}  # regra -> repetições depois de erro
        self._last_retention = 0.0
        self._last_disk_check = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(30_000)
        self.timer.timeout.connect(self.tick)
        net.received.connect(self.on_received)
        net.job_finished.connect(self.on_job_finished)
        self._ensure_defaults()

    # ------------------------------------------------------------ configuração

    def set_source(self, repo, db, trash_root=None) -> None:
        """Troca o banco (troca de local); a lixeira passa a ser a do local."""
        self.repo, self.db = repo, db
        if trash_root is not None:
            self.trash_root = trash_root

    def _ensure_defaults(self) -> None:
        if not self.repo.rules("prior"):
            for name, cfg in DEFAULT_PRIORS:
                self.repo.save_rule({"kind": "prior", "name": name, "active": False,
                                     "config": {**cfg, "on_receive": True, "on_open": True}})

    @property
    def policy(self) -> dict:
        return {**DEFAULT_RETENTION, **(self.settings.get("retention") or {})}

    def start(self) -> None:
        now = datetime.now()
        for r in self.repo.rules("query") + self.repo.rules("gestao"):
            if r["active"] and (r["next_run"] is None or r["next_run"] < now):
                self.repo.save_rule({"id": r["id"], "next_run": next_run(r["config"].get("schedule", {}), now)})
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def _search_nodes(self, node_id=None) -> list[dict]:
        nodes = [n for n in self.repo.nodes(only_active=True) if n["kind"] in NODES.CONSULTA]
        if node_id:
            return [n for n in nodes if n["id"] == node_id]
        return [n for n in nodes if n["use_in_search"]]

    # ------------------------------------------------------------ relógio
    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        for r in self.repo.rules("query"):
            if r["active"] and r["next_run"] is not None and r["next_run"] <= now:
                self.run_query(r, now)
        for r in self.repo.rules("gestao"):
            if r["active"] and r["next_run"] is not None and r["next_run"] <= now:
                self.rodar_gestao(r, now)
        # exames que terminaram de chegar
        t = time.monotonic()
        for uid, last in list(self._arriving.items()):
            if t - last >= QUIET_SECONDS:
                del self._arriving[uid]
                self.study_arrived(uid, "received")
        pol = self.policy
        if pol.get("enabled"):
            if time.time() - self._last_retention > 24 * 3600:
                self.run_retention()
            elif time.time() - self._last_disk_check > 3600:
                self._last_disk_check = time.time()
                pct, _t = retention.disk_usage(self.paths.storage)
                if pct > float(pol.get("disk_high_pct") or 101):
                    self.run_retention()

    # ------------------------------------------------------------ buscas agendadas
    def run_query(self, rule: dict, now: datetime | None = None) -> None:
        now = now or datetime.now()
        cfg = rule["config"]
        self.repo.save_rule({"id": rule["id"], "last_run": now,
                             "next_run": next_run(cfg.get("schedule", {}), now)})
        nodes = self._search_nodes(cfg.get("node_id"))
        if not nodes:
            self.repo.add_job_run("query", rule["name"], "error", 0, "nenhum nó de busca ativo", rule["id"])
            self.changed.emit()
            return
        d_from, d_to = date_range(cfg.get("date", "today"), now)
        filters = {k: v for k, v in (cfg.get("filters") or {}).items() if v}
        filters.update({"date_from": d_from, "date_to": d_to})
        ident = self.repo.identity(cfg.get("identity_id"))
        started = datetime.now()

        def done(res, err) -> None:
            if err is not None:
                self.repo.add_job_run("query", rule["name"], "error", 0, str(err), rule["id"], started)
                self.changed.emit()
                return
            rows, errors = res
            local = self.repo.instance_counts([r["study_uid"] for r in rows])
            new = [r for r in rows if local.get(r["study_uid"], 0) < max(1, r["num_images"] or 1)]
            new = new[: int(cfg.get("max_studies", 50))]
            if cfg.get("action", "download") == "download":
                for r in new:
                    job = self.net.retrieve(self.repo.node(r["node_id"]), ident, r["study_uid"],
                                            f"{rule['name']}: {r['patient_name']} {r['modalities']} {r['description']}")
                    self._job_tags[job.id] = {"list": cfg.get("add_to_list"), "unread": True}
            msg = f"{len(rows)} encontrado(s), {len(new)} novo(s)" + (f"; {'; '.join(errors)}" if errors else "")
            self.repo.add_job_run("query", rule["name"], "error" if errors and not rows else "ok",
                                  len(new), msg, rule["id"], started)
            if new:
                verb = "baixando" if cfg.get("action", "download") == "download" else "no PACS"
                self.notify.emit(rule["name"], f"{len(new)} exame(s) novo(s) — {verb}")
            self.changed.emit()
        self.net.search(nodes, ident, filters, done)

    # ------------------------------------------------------------ chegada de exames
    def on_received(self, result, origin: str) -> None:
        if origin != "received":
            return                              # downloads são tratados quando a tarefa termina
        now = time.monotonic()
        for uid in result.new_studies:
            self._arriving[uid] = now

    def on_job_finished(self, job) -> None:
        if job.kind != "retrieve" or job.status != "done":
            self._job_tags.pop(job.id, None)
            return
        uid = job.study_uids[0]
        tag = self._job_tags.pop(job.id, {})
        if tag.get("prefetch"):
            if tag.get("was_new"):
                self.repo.set_study_origin(uid, "prefetch")
            # o anterior também abre lado a lado no protocolo: chega já com o implante corrigido
            from ipe.automation import implante as IMP
            if IMP.config(self.settings, IMP.CHAVE_ANTERIORES):
                self.corrigir_implantes(uid)
            return                              # anterior não dispara nova pré-busca
        if tag.get("list"):
            self.repo.add_to_case_list(int(tag["list"]), uid)
        self.study_arrived(uid, "retrieved")

    def study_arrived(self, study_uid: str, origin: str) -> None:
        info = self.repo.study_info(study_uid)
        if info is None:
            return
        for r in self.repo.rules("route"):
            cfg = r["config"]
            if not r["active"] or not cfg.get("node_id") or not route_matches(cfg, info, origin):
                continue
            node = self.repo.node(cfg["node_id"])
            if node is None:
                continue
            try:
                self.net.send(node, self.repo.identity(cfg.get("identity_id")), [study_uid],
                              f"Roteamento {r['name']}: {info.get('patient_name', '')} {info.get('description', '')}")
                self.repo.add_job_run("route", r["name"], "ok", 1, f"{info.get('description', '')} → {node['name']}",
                                      r["id"])
            except Exception as e:  # noqa: BLE001
                self.repo.add_job_run("route", r["name"], "error", 0, str(e), r["id"])
        self.prefetch(study_uid, "receive")
        self.precalcular_dinamica(study_uid, info)
        self.corrigir_implantes(study_uid, info)
        self.segmentar_orgaos(study_uid, info)
        self.segmentar_coluna(study_uid, info)
        self.changed.emit()

    # ------------------------------------------------------------ exames importados (0.99.1)
    def cad_ia_importados(self, resultado) -> list[str]:
        """Importação pela tela (pasta, arquivos, ZIP, arrastar): o CAD/IA da chegada vale também.

        Até a 0.99.0 o implante e a segmentação automáticos só rodavam no exame que chegava pela rede
        (recebido ou baixado). Aqui roda só o CAD/IA — o roteamento e a pré-busca continuam sendo da
        chegada pela rede. Só os exames que ganharam imagens novas; os repetidos não."""
        novas = set(getattr(resultado, "new_series", None) or [])
        if not novas:
            return []
        feitos = []
        for uid in sorted(getattr(resultado, "studies", None) or []):
            try:
                if not novas & {s.series_uid for s in self.repo.series_for_study(uid)}:
                    continue
            except Exception:  # noqa: BLE001
                continue
            info = self.repo.study_info(uid)
            if info is None:
                continue
            self.corrigir_implantes(uid, info)
            self.segmentar_orgaos(uid, info)
            self.segmentar_coluna(uid, info)
            feitos.append(uid)
        return feitos

    # ------------------------------------------------------------ implante corrigido na chegada
    def corrigir_implantes(self, study_uid: str, info: dict | None = None) -> bool:
        """Mamografia com prótese: grava, no banco local, a cópia com o implante corrigido (0.97).

        Roda em segundo plano. A original fica como chegou; a cópia não vai ao PACS. Desliga em
        Preferências ▸ Mamografia."""
        from ipe.automation import implante as IMP
        if not IMP.ligado(self.settings) or study_uid in self._implante_rodando:
            return False
        info = info if info is not None else self.repo.study_info(study_uid)
        if info is None or "MG" not in (info.get("modalities") or "").upper():
            return False
        self._implante_rodando.add(study_uid)
        inicio = datetime.now()
        repo, db, storage = self.repo, self.db, self.paths.storage
        so_marca = bool(IMP.config(self.settings, IMP.CHAVE_SO_COM_MARCA))

        def trabalho():
            return IMP.processar(repo, db, storage, study_uid, so_com_marca=so_marca)

        def pronto(out, err) -> None:
            self._implante_rodando.discard(study_uid)
            nome = f"{info.get('patient_name', '')} {info.get('description', '')}".strip()
            if err is not None:
                self.repo.add_job_run("implante", "Implante na chegada", "error", 0, f"{nome}: {err}",
                                      None, inicio)
            elif out.get("vistas"):
                self.repo.add_job_run("implante", "Implante na chegada",
                                      "ok" if out["corrigidas"] else "vazio", out["corrigidas"],
                                      f"{nome}: {IMP.resumo(out)}", None, inicio)
            if out and out.get("corrigidas"):
                self.implante_corrigido.emit(study_uid)
                from ipe.automation import destinos as DEST
                DEST.enviar(self.net, self.repo, study_uid, out.get("series"),
                            IMP.config(self.settings, IMP.CHAVE_DESTINOS), f"Sem implante: {nome}")
            self.changed.emit()

        self.net.run_async(trabalho, pronto)
        return True

    # ------------------------------------------------------------ dinâmica pronta na chegada
    def precalcular_dinamica(self, study_uid: str, info: dict | None = None) -> bool:
        """Deixa a dinâmica do exame pronta para abrir: detecta as fases e decodifica os quadros.

        Nada é gravado como série e nada é enviado — a escolha do usuário foi essa. O trabalho
        roda em segundo plano; se não houver cache de quadros (modo cliente, teste), não faz nada.
        """
        from ipe.automation import dinamica as D
        if self.cache is None:
            return False
        info = info if info is not None else self.repo.study_info(study_uid)
        if info is None:
            return False
        regra = next((r for r in self.repo.rules("dinamica")
                      if r["active"] and D.regra_serve(r["config"], info)), None)
        if regra is None:
            return False
        inicio = datetime.now()
        repo, cache = self.repo, self.cache

        def trabalho():
            return D.aquecer(repo, cache, study_uid)

        def pronto(out, err) -> None:
            if err is not None:
                self.repo.add_job_run("dinamica", regra["name"], "error", 0, str(err), regra["id"], inicio)
            else:
                nome = f"{info.get('patient_name', '')} {info.get('description', '')}".strip()
                self.repo.add_job_run("dinamica", regra["name"],
                                      "ok" if out["fases"] else "vazio", out["quadros"],
                                      f"{nome}: {D.resumo(out)}", regra["id"], inicio)
            self.changed.emit()

        self.net.run_async(trabalho, pronto)
        return True

    # ------------------------------------------------------------ TotalSegmentator na chegada (0.99, 0.99.2)
    def segmentar_orgaos(self, study_uid: str, info: dict | None = None) -> bool:
        """Preferências ▸ CAD/IA ▸ Segmentação abdominal ▸ automático."""
        return self._enfileirar(study_uid, "abdome", info)

    def segmentar_coluna(self, study_uid: str, info: dict | None = None) -> bool:
        """Preferências ▸ CAD/IA ▸ Níveis da coluna ▸ automático (0.99.2)."""
        return self._enfileirar(study_uid, "coluna", info)

    def _enfileirar(self, study_uid: str, tipo: str, info: dict | None) -> bool:
        """Escolhe a série pela lista de prioridade e roda em segundo plano. **Um exame por vez** — os
        outros esperam na fila. Exame que já tem o resultado daquela ferramenta não é refeito."""
        from ipe.ai import coluna as COL
        from ipe.ai import totalseg as TS
        mod = COL if tipo == "coluna" else TS
        if not mod.config(self.settings, mod.CHAVE_AUTO):
            return False
        if not self._seg_simular and not TS.instalado(self.settings):
            return False
        info = info if info is not None else self.repo.study_info(study_uid)
        if info is None or not mod.exame_serve(info, self.settings):
            return False
        ja = COL.ja_identificado(self.repo, study_uid) if tipo == "coluna" else TS.ja_segmentado(self.repo, study_uid)
        if ja:
            return False
        if (study_uid, tipo) not in self._seg_fila:
            self._seg_fila.append((study_uid, tipo))
        self._seg_proximo()
        return True

    def _seg_proximo(self) -> None:
        from ipe.ai import coluna as COL
        from ipe.ai import totalseg as TS
        if not self._seg_fila or TS.EM_CURSO:
            if self._seg_fila and TS.EM_CURSO and not getattr(self, "_seg_esperando", False):
                self._seg_esperando = True                         # há uma rodando (talvez à mão)

                def de_novo():
                    self._seg_esperando = False
                    self._seg_proximo()
                QTimer.singleShot(30_000, de_novo)
            return
        study_uid, tipo = self._seg_fila.pop(0)
        coluna = tipo == "coluna"
        titulo = "Níveis da coluna" if coluna else "Órgãos abdominais"
        info = self.repo.study_info(study_uid) or {}
        nome = f"{info.get('patient_name', '')} {info.get('description', '')}".strip()
        serie, motivo = (COL.escolher_serie if coluna else TS.escolher_serie)(self.repo, study_uid, self.settings)
        if serie is None:
            self.repo.add_job_run("segmentacao", titulo, "vazio", 0, f"{nome}: {motivo}")
            self.changed.emit()
            QTimer.singleShot(0, self._seg_proximo)
            return
        from ipe.imaging.series import FrameCache
        t = TS.Trabalho(self.repo, FrameCache(256), self.settings, study_uid, serie, simular=self._seg_simular)
        if coluna:
            t.tarefas_proprias, t.min_cortes = COL.tarefas, COL.MIN_CORTES
        TS.EM_CURSO.add(study_uid)
        inicio = datetime.now()

        conf = {}

        def trabalho():
            t.preparar()                # volume montado aqui, fora da tela (cache próprio)
            t.rodar_aqui()
            if coluna:
                rotulos, versao, _s = t.ler_rotulos()
                niveis = COL.nomear(t.vol, rotulos)
                # 0.99.5: na RM, a mesma conta na outra sagital, para conferir as medidas
                if niveis.itens and COL.quer_conferencia(self.settings, t.modalidade):
                    outra = COL.segunda_serie(self.repo, study_uid, serie, self.settings)
                    if outra:
                        t2 = TS.Trabalho(self.repo, FrameCache(256), self.settings, study_uid, outra,
                                         simular=self._seg_simular)
                        t2.tarefas_proprias, t2.min_cortes = COL.tarefas, COL.MIN_CORTES
                        conf["t"] = t2
                        try:
                            t2.preparar()
                            t2.rodar_aqui()
                            r2, v2, _s2 = t2.ler_rotulos()
                            conf["niveis"], conf["versao"] = COL.nomear(t2.vol, r2), v2
                        except Exception as e:  # noqa: BLE001
                            log.warning("conferência da coluna em %s: %s", study_uid, e)
                return niveis, versao
            return t.ler()

        def pronto(res, err) -> None:
            try:
                if err is not None:
                    raise err
                if coluna:
                    niveis, versao = res
                    if not niveis.itens:
                        raise TS.Falhou("o TotalSegmentator não achou vértebras nesta série")
                    saida = COL.gravar(t, niveis, versao, self.db, self.paths.storage, repo=self.repo)
                    saida["niveis"] = niveis
                    resumo = COL.resumo(niveis)
                    if conf.get("niveis") is not None and conf["niveis"].itens:
                        try:
                            c = COL.gravar(conf["t"], conf["niveis"], conf["versao"], self.db, self.paths.storage,
                                           conferencia=True, repo=self.repo)
                            saida["series"] = list(saida.get("series") or []) + list(c.get("series") or [])
                        except Exception as e:  # noqa: BLE001
                            log.warning("gravar a conferência da coluna: %s", e)
                    if COL.config(self.settings, COL.CHAVE_MEDIR) and saida.get("seg_path"):
                        tab = COL.gravar_tabela(self.repo, self.db, self.paths.storage, study_uid, saida["seg_path"])
                        saida["series"] = list(saida.get("series") or []) + tab["series"]
                        saida["medidas"] = tab["medidas"]
                        if COL.resumo_tabelas(tab):
                            resumo += "; " + COL.resumo_tabelas(tab)
                    n_itens, destinos = len(niveis.itens), COL.config(self.settings, COL.CHAVE_DESTINOS)
                else:
                    from ipe.ai import totalseg_saida as SAIDA
                    saida = SAIDA.gravar(t, res, self.db, self.paths.storage)     # tabela: desenho na tela principal
                    saida["resultado"] = res
                    resumo, n_itens = SAIDA.resumo(res), len(res.estruturas)
                    destinos = TS.config(self.settings, TS.CHAVE_DESTINOS)
                self.repo.add_job_run("segmentacao", titulo, "ok", n_itens, f"{nome}: {resumo}", None, inicio)
                from ipe.automation import destinos as DEST
                DEST.enviar(self.net, self.repo, study_uid, saida.get("series"), destinos, f"{titulo}: {nome}")
                self.segmentacao_pronta.emit(study_uid, saida)
            except Exception as e:  # noqa: BLE001
                log.warning("%s automática de %s: %s", titulo, study_uid, e)
                self.repo.add_job_run("segmentacao", titulo, "error", 0, f"{nome}: {e}", None, inicio)
            finally:
                t.limpar()
                if conf.get("t") is not None:
                    conf["t"].limpar()
                TS.EM_CURSO.discard(study_uid)
                self.changed.emit()
                QTimer.singleShot(0, self._seg_proximo)

        self.net.run_async(trabalho, pronto, self._pool_ia())

    # ------------------------------------------------------------ gestão automática (0.99.6)
    def rodar_gestao(self, regra: dict, now: datetime | None = None, manual: bool = False,
                     espera: float = 2.0) -> bool:
        """Roda uma regra da gestão em segundo plano: confere, manda, confere de novo, grava o relatório
        na regra e no histórico; com erro ou nó fora do ar, marca a repetição para daqui a X minutos."""
        from ipe.network import gestao_auto as GA
        rid = regra["id"]
        if rid in self._gestao_rodando:
            return False
        now = now or datetime.now()
        cfg = regra["config"]
        normal = next_run(cfg.get("schedule", {}), now)
        if not manual:
            self.repo.save_rule({"id": rid, "last_run": now, "next_run": normal})
        else:
            self.repo.save_rule({"id": rid, "last_run": now})
        self._gestao_rodando.add(rid)
        self.gestao_mudou.emit()
        inicio = datetime.now()

        def trabalho():
            return GA.executar(regra, self.repo, self.net.client, self.net.target, sink=self.net.sink,
                               espera=espera)

        def pronto(rel, err) -> None:
            self._gestao_rodando.discard(rid)
            if err is not None:
                rel = GA.Relatorio(regra=regra.get("name", ""), erro=str(err))
            atual = self.repo.rule(rid) or regra
            nova = dict(atual.get("config") or {})
            d = rel.para_dict()
            tent = self._gestao_tentativas.get(rid, 0)
            prox = None
            if rel.precisa_repetir():
                prox = GA.proxima_tentativa(atual, datetime.now(), tent)
                if prox is not None:
                    self._gestao_tentativas[rid] = tent + 1
                    d["repeticao"] = f"tentativa {tent + 1} de {GA.config(atual)['repetir'].get('vezes')}"
            else:
                self._gestao_tentativas.pop(rid, None)
            nova["_ultimo"] = d
            dados = {"id": rid, "config": nova}
            proximo_normal = atual.get("next_run")
            if prox is not None and (proximo_normal is None or prox < proximo_normal):
                dados["next_run"] = prox
                d["proxima_por_erro"] = prox.isoformat(timespec="minutes")
            self.repo.save_rule(dados)
            status = {"ok": "ok", "erro": "error", "offline": "offline"}[rel.situacao]
            self.repo.add_job_run("gestao", regra.get("name", ""), status, len(rel.enviados),
                                  rel.resumo(), rid, inicio)
            if rel.situacao != "ok":
                self.notify.emit("Gestão DICOM", f"{regra.get('name', '')}: {rel.resumo()}")
            self.gestao_mudou.emit()
            self.changed.emit()

        self.net.run_async(trabalho, pronto, self.net.transfer_pool)
        return True

    def gestao_em_curso(self, rule_id: int) -> bool:
        return rule_id in self._gestao_rodando

    def _pool_ia(self):
        """Fila própria para o CAD/IA pesado: não ocupa as linhas das buscas e downloads."""
        if getattr(self, "_pool", None) is None:
            from PySide6.QtCore import QThreadPool
            self._pool = QThreadPool(self)
            self._pool.setMaxThreadCount(1)
        return self._pool

    # ------------------------------------------------------------ anteriores
    def on_study_opened(self, study_uid: str) -> None:
        self.prefetch(study_uid, "open")

    def _prior_nodes(self) -> list[dict]:
        from ipe.network.nodes import prior_nodes
        return prior_nodes(self.repo, self.settings)

    def prefetch(self, study_uid: str, trigger: str) -> bool:
        info = self.repo.study_info(study_uid)
        if info is None or not info.get("patient_id"):
            return False
        rule = prior_rule_for(self.repo.rules("prior"), info.get("modalities", ""), info.get("description", ""))
        if rule is None or not rule["config"].get("on_open" if trigger == "open" else "on_receive", True):
            return False
        if time.time() - self._recent_prefetch.get(study_uid, 0) < 600:
            return False
        nodes = self._prior_nodes()
        if not nodes:
            return False
        self._recent_prefetch[study_uid] = time.time()
        started = datetime.now()
        current = {**info, "study_uid": study_uid}

        def done(res, err) -> None:
            if err is not None:
                self.repo.add_job_run("prior", rule["name"], "error", 0, str(err), rule["id"], started)
                self.changed.emit()
                return
            rows, _errors = res
            chosen = select_priors(rule["config"], current, rows, date.today())
            local = self.repo.instance_counts([r["study_uid"] for r in chosen])
            todo = [r for r in chosen if local.get(r["study_uid"], 0) < max(1, r["num_images"] or 1)]
            for r in todo:
                job = self.net.retrieve(self.repo.node(r["node_id"]), None, r["study_uid"],
                                        f"Anterior (pré-busca): {r['study_date']} {r['modalities']} {r['description']}")
                self._job_tags[job.id] = {"prefetch": True, "was_new": r["study_uid"] not in local}
            self.repo.add_job_run("prior", rule["name"], "ok", len(todo),
                                  f"{info.get('patient_name', '')}: {len(chosen)} anterior(es), {len(todo)} a baixar",
                                  rule["id"], started)
            self.changed.emit()
        self.net.search(nodes, None, {"patient_id": info["patient_id"]}, done)
        return True

    # ------------------------------------------------------------ limpeza
    def preview_retention(self):
        return retention.plan(self.repo, self.paths.storage, {**self.policy, "enabled": True}, self.open_uids())

    def run_retention(self, force: bool = False) -> int:
        self._last_retention = self._last_disk_check = time.time()
        pol = self.policy
        if not pol.get("enabled") and not force:
            return 0
        started = datetime.now()
        items = retention.plan(self.repo, self.paths.storage, {**pol, "enabled": True}, self.open_uids())
        n = 0
        for stat, reason in items:
            try:
                retention.trash_study(self.repo, stat, self.paths.storage, self.trash_root, reason)
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Limpeza: não apagou %s: %s", stat.study_uid, e)
        purged = retention.purge(self.repo, self.trash_root, int(pol.get("trash_days") or 7))
        self.repo.add_job_run("clean", "Limpeza", "ok", n,
                              f"{n} estudo(s) para a lixeira; {purged} apagado(s) de vez", None, started)
        if n:
            self.notify.emit("Limpeza", f"{n} estudo(s) movido(s) para a lixeira")
        self.changed.emit()
        return n
