"""Trava de leitura do laudo no servidor central (0.99.31, onda A1 — ideia da Eden).

Quem abre o laudo de um exame passa a ser "quem está laudando" até fechar a janela do laudo (o cliente
avisa a cada 2 minutos que continua; sem aviso por 10 minutos, a trava cai sozinha — o computador
travou, a rede caiu). Enquanto isso, quem abrir o laudo do mesmo exame é avisado e escolhe entre só ler
ou assumir (o assumir fica no registro de acesso), e o servidor recusa gravar ou assinar o laudo de
quem não é o dono da trava.
"""
from __future__ import annotations

import threading
import time

VALIDADE_S = 10 * 60


class Leituras:
    def __init__(self, validade_s: int = VALIDADE_S):
        self.validade_s = validade_s
        self._d: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _limpa(self) -> None:
        agora = time.time()
        for uid in [u for u, x in self._d.items() if agora - x["visto"] > self.validade_s]:
            self._d.pop(uid, None)

    def quem(self, study_uid: str) -> dict | None:
        with self._lock:
            self._limpa()
            x = self._d.get(study_uid)
            return dict(x) if x else None

    def comecar(self, study_uid: str, usuario: str, nome: str = "", forcar: bool = False) -> dict:
        with self._lock:
            self._limpa()
            x = self._d.get(study_uid)
            if x and x["usuario"].lower() != usuario.lower() and not forcar:
                return {"ok": False, "de": x["nome"] or x["usuario"], "usuario": x["usuario"],
                        "desde": time.strftime("%H:%M", time.localtime(x["desde"]))}
            antes = x["usuario"] if x and x["usuario"].lower() != usuario.lower() else ""
            agora = time.time()
            self._d[study_uid] = {"usuario": usuario, "nome": nome or usuario,
                                  "desde": x["desde"] if x and not antes else agora, "visto": agora}
            return {"ok": True, "assumiu_de": antes}

    def manter(self, study_uids, usuario: str) -> int:
        with self._lock:
            n = 0
            for uid in study_uids or []:
                x = self._d.get(uid)
                if x and x["usuario"].lower() == usuario.lower():
                    x["visto"] = time.time()
                    n += 1
            return n

    def terminar(self, study_uid: str, usuario: str) -> bool:
        with self._lock:
            x = self._d.get(study_uid)
            if x and x["usuario"].lower() == usuario.lower():
                self._d.pop(study_uid, None)
                return True
            return False

    def ativas(self) -> dict[str, dict]:
        with self._lock:
            self._limpa()
            return {u: {"usuario": x["usuario"], "nome": x["nome"],
                        "desde": time.strftime("%H:%M", time.localtime(x["desde"]))} for u, x in self._d.items()}

    def bloqueia(self, study_uid: str, usuario: str) -> str:
        """"" se pode gravar; senão o texto do motivo."""
        x = self.quem(study_uid)
        if x and x["usuario"].lower() != usuario.lower():
            return f"{x['nome'] or x['usuario']} está laudando este exame desde " \
                   f"{time.strftime('%H:%M', time.localtime(x['desde']))}"
        return ""
