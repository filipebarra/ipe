"""0.100.78: na mamografia, as sincronias ficam desligadas de fábrica (janela, zoom/pan, rolagem) e o zoom por
quadrante tem quatro áreas (posterior/anterior × superior/inferior)."""
from types import SimpleNamespace


class _Prefs(dict):
    def get(self, k, padrao=None):
        return super().get(k, padrao)

    def set(self, k, v):
        self[k] = v


def test_sincronias_da_mamografia_desligadas(qapp):
    from ipe.ui.viewer.sync import SyncHub
    # quem tinha ligado a rolagem junta da MG (e a janela e o zoom das outras modalidades)
    prefs = _Prefs({"viewer.sync_auto_mod": {"MG": True, "CT": True}, "viewer.sync_wl": True, "viewer.sync_zoom": True})
    hub = SyncHub(settings=prefs)
    assert hub.auto_da_modalidade("MG") is False and hub.auto_da_modalidade("CT") is True
    assert prefs["viewer.mg_sync_padrao_v78"] is True and prefs["viewer.sync_auto_mod"]["MG"] is False
    assert hub.sync_wl and hub.sync_zoom and not hub.mg_sync_wl and not hub.mg_sync_zoom
    # depois da primeira vez, a escolha dele vale
    hub.set_auto_modalidade("MG", True) if hasattr(hub, "set_auto_modalidade") else prefs.__setitem__(
        "viewer.sync_auto_mod", {"MG": True})
    assert SyncHub(settings=prefs).auto_da_modalidade("MG") is True

    # a janela e o zoom de um quadro de mamografia não passam para os outros (com as da MG desligadas)
    mudou = []

    def quadro(mod, nome):
        q = SimpleNamespace(modality=mod, frames=[1], _img=SimpleNamespace(is_color=False), mg_cell=None,
                            state=SimpleNamespace(width=400, level=40, zoom=2.0, pan=0, cmap="", invert=False),
                            nome=nome)
        q.set_window = lambda w, lv, emit=False, q=q: mudou.append(("janela", q.nome))
        q.set_zoom_pan = lambda z, p, q=q: mudou.append(("zoom", q.nome))
        return q
    a, b, c = quadro("MG", "a"), quadro("MG", "b"), quadro("CT", "c")
    hub.viewports = lambda extra=None: [a, b, c]
    hub.view_changed(a, "window")
    hub.view_changed(a, "zoom")
    assert mudou == []
    hub.mg_sync_wl = True                       # ligada à mão pelo botão na mamografia
    hub.view_changed(a, "window")
    assert mudou == [("janela", "b")]
    mudou.clear()
    hub.view_changed(c, "zoom")                 # TC segue a sincronia geral (ligada)
    assert ("zoom", "a") in mudou and ("zoom", "b") in mudou


def test_quatro_quadrantes_na_ordem():
    from ipe.ui.viewer.mamografia_aba import MamografiaMixin
    from ipe.ui.viewer.mammo_view import QUAD_NAMES, QUAD_ORDEM
    assert QUAD_ORDEM == (0, 2, 1, 3) and len(QUAD_NAMES) == 4
    vp = SimpleNamespace(_img=object(), quad_idx=-1, state=SimpleNamespace(zoom=1.0))
    msgs = []
    tab = SimpleNamespace(status_message=SimpleNamespace(emit=msgs.append))

    def mg_quadrant(v, idx):
        v.quad_idx = idx
        v.state.zoom = 1.0 if idx < 0 else 2.0
    tab.mg_quadrant = mg_quadrant
    seq = []
    for _ in range(5):
        MamografiaMixin.mg_quadrant_cycle(tab, vp, 1)
        seq.append(vp.quad_idx)
    assert seq == [0, 2, 1, 3, -1]
    assert "anterior e superior" in msgs[1] and msgs[-1] == "Zoom: imagem inteira"
    MamografiaMixin.mg_quadrant_cycle(tab, vp, -1)          # Shift+Q: de volta para trás
    assert vp.quad_idx == 3


def test_quadrante_junto_de_fabrica_e_desligavel():
    from ipe.ui.viewer.mamografia_aba import MamografiaMixin
    msgs = []
    a, b, c = (SimpleNamespace(mg_cell=1, frames=[1]) for _ in range(3))
    tab = SimpleNamespace(mg_session=SimpleNamespace(proto={}), _shown=lambda: [a, b, c],
                          status_message=SimpleNamespace(emit=msgs.append))
    tab.mg_quadrante_junto = lambda: MamografiaMixin.mg_quadrante_junto(tab)
    assert MamografiaMixin.mg_quadrante_junto(tab) is True              # de fábrica: juntos
    assert MamografiaMixin.mg_cells(tab, a) == [a, b, c]
    MamografiaMixin.mg_set_quadrante_junto(tab, False)                  # desligado durante o exame
    assert MamografiaMixin.mg_cells(tab, a) == [a] and "só no quadro ativo" in msgs[-1]
    MamografiaMixin.mg_set_quadrante_junto(tab, True)
    assert MamografiaMixin.mg_cells(tab, a) == [a, b, c]
