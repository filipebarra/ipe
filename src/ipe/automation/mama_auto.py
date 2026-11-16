"""0.100.57: densidade mamária e calcificações vasculares automáticas, como as outras IAs.

Pedido dele: "quero automatizar, como a IA. fazer para todas as mamografias que entrarem no sistema (via Q/R,
importação…). faça e deixe para eu confirmar ao abrir o exame. depois que confirmar, salve um SR, com tudo … ao
abrir o programa na próxima versão, o sistema vai verificar todas as mamografias que estiverem no banco e rodar".

- Na chegada (recebido, baixado, importado), a mamografia entra numa fila de um exame por vez: mede a densidade
  (rede da NYU) e as calcificações vasculares (SCU-Net) e guarda no exame, sem confirmar (estado "auto").
- Ao abrir, o Ipê pergunta (`pendentes`): a janela da densidade e a das calcificações abrem para confirmar.
- Confirmadas, `ipe.ai.mama_sr` grava no exame o SR e as imagens com as calcificações marcadas.
- Uma vez por versão do método (`VARREDURA`), o banco inteiro é varrido em segundo plano: toda mamografia sem a
  medida (ou com a medida de um método mais antigo, ainda não confirmada) entra na fila.

Só onde as imagens estão: no cliente de um servidor central não roda (o servidor faz para todos).
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

CHAVE = "mg.ia_na_chegada"                  # Preferências ▸ Mamografia: medir sozinho na chegada
CHAVE_ABRIR = "mg.ia_confirmar_ao_abrir"    # abrir as janelas de confirmação ao abrir o exame
CHAVE_VARREDURA = "mg.ia_varredura"         # a última varredura do banco terminada (número do método)
#: muda quando o método muda e o banco precisa ser varrido de novo
VARREDURA = 2
TITULO = "Densidade e calcificações vasculares"


def _cfg(settings, chave: str, padrao):
    if settings is None:
        return padrao
    try:
        v = settings.get(chave, padrao)
    except Exception:  # noqa: BLE001
        return padrao
    return padrao if v is None else v


def ligado(settings) -> bool:
    import os
    if os.environ.get("IPE_SEM_MAMA_AUTO"):             # testes de outras coisas
        return False
    return bool(_cfg(settings, CHAVE, True))


def confirmar_ao_abrir(settings) -> bool:
    return bool(_cfg(settings, CHAVE_ABRIR, True))


def local(repo) -> bool:
    """As imagens estão aqui (banco próprio ou servidor), não num servidor central do qual este é cliente."""
    return not hasattr(repo, "is_cached")


def e_mamografia(info: dict | None) -> bool:
    return bool(info) and "MG" in str(info.get("modalities") or "").upper()


def _modulos():
    from ipe.ai import calc_vascular as C
    from ipe.imaging import densidade_revisao as R
    return R, C


def falta(repo, study_uid: str) -> list[str]:
    """O que falta medir no exame: "densidade" e/ou "calc_vascular" (sem medida, ou de um método antigo e sem
    confirmação)."""
    R, C = _modulos()
    out = []
    for nome, mod in (("densidade", R), ("calc_vascular", C)):
        g = mod.guardada(repo, study_uid)
        if g is None:
            out.append(nome)
        elif (g.get("estado") or "auto") == "auto" and int(g.get("versao") or 0) < mod.VERSAO:
            out.append(nome)
    return out


def pendentes(repo, study_uid: str) -> dict:
    """O que está medido e ainda não foi confirmado: {"densidade": medida, "calc_vascular": medida}."""
    R, C = _modulos()
    out = {}
    d = R.guardada(repo, study_uid)
    if d and (d.get("estado") or "auto") == "auto" and d.get("nyu"):
        out["densidade"] = d
    c = C.guardada(repo, study_uid)
    if c and (c.get("estado") or "auto") == "auto" and not c.get("aviso") and c.get("imagens"):
        out["calc_vascular"] = c
    return out


def medir(repo, study_uid: str, stop=None, o_que: list[str] | None = None) -> dict:
    """Mede e guarda (sem confirmar). Devolve {"densidade": resumo, "calc_vascular": resumo, "erros": [...]}."""
    R, C = _modulos()
    o_que = o_que if o_que is not None else falta(repo, study_uid)
    out: dict = {"erros": []}
    if "densidade" in o_que:
        try:
            m = R.medir_exame(repo, study_uid, None, stop)
            if not (stop is not None and stop.is_set()):
                R.guardar_medida(repo, study_uid, m)
                out["densidade"] = (m.get("nyu") or "").upper() or (m.get("nyu_aviso") or "sem categoria")
        except Exception as e:  # noqa: BLE001
            log.warning("densidade automática %s: %s", study_uid, e)
            out["erros"].append(f"densidade: {e}")
    if stop is not None and stop.is_set():
        return out
    if "calc_vascular" in o_que:
        try:
            m = C.medir_exame(repo, study_uid, None, stop)
            if not (stop is not None and stop.is_set()):
                C.guardar_medida(repo, study_uid, m)
                out["calc_vascular"] = m.get("aviso") or (m.get("sugestao") or "sem sugestão")
        except Exception as e:  # noqa: BLE001
            log.warning("calcificações automáticas %s: %s", study_uid, e)
            out["erros"].append(f"calcificações: {e}")
    return out


def resumo(out: dict) -> str:
    partes = []
    if out.get("densidade"):
        partes.append(f"densidade {out['densidade']}")
    if out.get("calc_vascular"):
        partes.append(f"calcificações: {out['calc_vascular']}")
    partes += out.get("erros") or []
    return "; ".join(partes) or "nada a medir"


def mamografias_do_banco(repo) -> list[str]:
    """Todas as mamografias do banco, das mais novas para as mais antigas."""
    try:
        linhas = repo.search_studies(modality="MG", limit=10_000_000, banco="todos")
    except TypeError:
        linhas = repo.search_studies(modality="MG", limit=10_000_000)
    linhas = sorted(linhas, key=lambda r: (r.study_date or "", r.study_time or ""), reverse=True)
    return [r.study_uid for r in linhas]


class Fila:
    """Um exame por vez, numa linha só (as redes usam a CPU inteira). A chegada passa na frente da varredura."""

    def __init__(self, repo, aviso=None, settings=None) -> None:
        self.repo = repo
        self.settings = settings
        self.aviso = aviso                      # callable(study_uid, out) quando um exame termina
        self._lock = threading.Lock()
        self._chegada: list[str] = []
        self._varredura: list[str] = []
        self._na_fila: set[str] = set()
        self._linha: threading.Thread | None = None
        self.stop = threading.Event()
        self.tarefa_varredura = None            # id em ai.tarefas
        self.feitos_varredura = 0
        self.total_varredura = 0

    def pedir(self, study_uid: str, varredura: bool = False) -> bool:
        with self._lock:
            if study_uid in self._na_fila:
                if not varredura and study_uid in self._varredura:     # chegou de novo: passa à frente
                    self._varredura.remove(study_uid)
                    self._chegada.append(study_uid)
                return False
            self._na_fila.add(study_uid)
            (self._varredura if varredura else self._chegada).append(study_uid)
            if self._linha is None or not self._linha.is_alive():
                self.stop.clear()
                self._linha = threading.Thread(target=self._rodar, name="mama-ia", daemon=True)
                self._linha.start()
        return True

    def vazia(self) -> bool:
        with self._lock:
            return not self._na_fila

    def cancelar_varredura(self) -> None:
        """Cancelada na janela "Tarefas de IA": não volta a varrer nesta versão (os que chegarem, sim)."""
        from ipe.ai import tarefas as TA
        with self._lock:
            for u in self._varredura:
                self._na_fila.discard(u)
            self._varredura.clear()
        if self.tarefa_varredura is not None:
            TA.REGISTRO.mudar(self.tarefa_varredura, TA.CANCELADO,
                              mensagem=f"{self.feitos_varredura} de {self.total_varredura} conferida(s)")
            self.tarefa_varredura = None
        varredura_terminada(self.settings)

    def parar(self) -> None:
        self.stop.set()
        with self._lock:
            self._chegada.clear()
            self._varredura.clear()
            self._na_fila.clear()

    def _proximo(self) -> tuple[str, bool] | None:
        with self._lock:
            if self._chegada:
                return self._chegada.pop(0), False
            if self._varredura:
                return self._varredura.pop(0), True
            return None

    def _rodar(self) -> None:
        from ipe.ai import tarefas as TA
        try:
            import os
            os.nice(5)                          # Linux/Mac: a tela continua leve
        except Exception:  # noqa: BLE001
            pass
        while not self.stop.is_set():
            prox = self._proximo()
            if prox is None:
                return
            uid, da_varredura = prox
            tid = None
            try:
                if not da_varredura:
                    info = self.repo.study_info(uid) or {}
                    nome = f"{info.get('patient_name', '')} {info.get('description', '')}".strip()
                    tid = TA.REGISTRO.nova(TITULO, uid, nome, "automática", TA.RODANDO).id
                if not falta(self.repo, uid):
                    out = {}
                    if tid is not None:
                        TA.REGISTRO.mudar(tid, TA.VAZIO, mensagem="já medido")
                else:
                    out = medir(self.repo, uid, self.stop)
                    if tid is not None:
                        TA.REGISTRO.mudar(tid, TA.ERRO if out.get("erros") else TA.PRONTO, mensagem=resumo(out))
                if da_varredura:
                    self.feitos_varredura += 1
                    if self.tarefa_varredura is not None:
                        TA.REGISTRO.mudar(self.tarefa_varredura, TA.RODANDO,
                                          etapa=f"{self.feitos_varredura} de {self.total_varredura}")
                if self.aviso and out:
                    try:
                        self.aviso(uid, out)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                log.exception("mama automática %s", uid)
                if tid is not None:
                    TA.REGISTRO.mudar(tid, TA.ERRO, mensagem=str(e))
            finally:
                with self._lock:
                    self._na_fila.discard(uid)
            if da_varredura and self.tarefa_varredura is not None and not self._varredura:
                TA.REGISTRO.mudar(self.tarefa_varredura, TA.PRONTO,
                                  mensagem=f"{self.feitos_varredura} mamografia(s) conferida(s)")
                self.tarefa_varredura = None
                varredura_terminada(self.settings)


def varredura_terminada(settings) -> None:
    if settings is None:
        return
    try:
        settings.set_do_computador(CHAVE_VARREDURA, VARREDURA)
        settings.save()
    except Exception:  # noqa: BLE001
        log.debug("guardar a varredura", exc_info=True)


def varrer_banco(fila: Fila, settings) -> int:
    """Uma vez por versão do método (até terminar): põe na fila as mamografias do banco que faltam medir.
    Devolve quantas. O que ficar para trás numa saída do programa volta na próxima abertura."""
    from ipe.ai import tarefas as TA
    if settings is not None and int(_cfg(settings, CHAVE_VARREDURA, 0) or 0) >= VARREDURA:
        return 0
    uids = [u for u in mamografias_do_banco(fila.repo) if falta(fila.repo, u)]
    if not uids:
        varredura_terminada(settings)
        return 0
    fila.total_varredura, fila.feitos_varredura = len(uids), 0
    t = TA.REGISTRO.nova(f"{TITULO} — mamografias do banco", "", f"{len(uids)} exame(s)", "automática", TA.RODANDO,
                         cancelar=fila.cancelar_varredura)
    fila.tarefa_varredura = t.id
    for u in uids:
        fila.pedir(u, varredura=True)
    return len(uids)
