"""0.100.79: RM de próstata — o PI-RADS v2.1 sem IA (regras, volume, densidade do PSA, setores, texto, SR), o volume
pela IA (TotalSegmentator simulado) e os modelos de pesquisa (zonas e PI-CAI simulados), com a licença e as marcas.

Os exames são fantomas: a glândula é tudo ≥ 800 (o trabalhador simulado devolve "prostate"), a zona periférica é
≥ 1500, e o foco "suspeito" do PI-CAI simulado é 2500–3500 (probabilidade 0,73).
"""
import json
import os

import numpy as np
import pytest

from ipe.reporting import pirads as P


# ---------------------------------------------------------------------- regras
@pytest.mark.parametrize("lesao, bip, esperado", [
    ({"zona": "PZ", "t2": 2, "dwi": 3, "dce": "+"}, False, "4"),       # PZ: DWI 3 + DCE+ → 4
    ({"zona": "PZ", "t2": 2, "dwi": 3, "dce": "+"}, True, "3"),        # biparamétrica: não sobe
    ({"zona": "PZ", "t2": 4, "dwi": 3, "dce": "-"}, False, "3"),
    ({"zona": "PZ", "t2": 4, "dwi": 5}, False, "5"),
    ({"zona": "PZ", "t2": 3, "dce": "+"}, False, "4"),                  # sem difusão: T2 3 + DCE+ → 4
    ({"zona": "TZ", "t2": 2, "dwi": 4}, False, "3"),                    # TZ: T2 2 + DWI ≥ 4 → 3
    ({"zona": "TZ", "t2": 2, "dwi": 3}, False, "2"),
    ({"zona": "TZ", "t2": 3, "dwi": 5}, False, "4"),                    # T2 3 + DWI 5 → 4
    ({"zona": "TZ", "t2": 3, "dwi": 4, "dce": "+"}, False, "3"),        # na TZ o DCE não muda
    ({"zona": "TZ", "t2": 5, "dwi": 2}, False, "5"),
    ({"zona": "TZ", "t2": 2, "dwi": 4, "categoria_manual": "4"}, False, "4"),
    ({"zona": "PZ", "t2": 4}, False, "4"),
    ({"zona": "", "t2": 4, "dwi": 4}, False, ""),
    ({"zona": "TZ", "dwi": 5}, False, ""),
])
def test_regras_do_pirads_v21(lesao, bip, esperado):
    assert P.categoria(P.normalizar_lesao(lesao, 1), bip)[0] == esperado


def test_avisos_de_tamanho_e_zonas_sem_tabela():
    _c, av = P.categoria(P.normalizar_lesao({"zona": "PZ", "dwi": 4, "tamanho_mm": 16}, 1))
    assert any("15 mm" in a for a in av)
    _c, av = P.categoria(P.normalizar_lesao({"zona": "PZ", "dwi": 5, "tamanho_mm": 9, "epe": "nao"}, 1))
    assert any("pede ≥ 15 mm" in a for a in av)
    _c, av = P.categoria(P.normalizar_lesao({"zona": "AS", "t2": 3}, 1))
    assert any("estroma" in a for a in av)


def test_setores_volume_psad_e_texto():
    sets = P.setores()
    assert len(sets) == 38 and {s["zona"] for s in sets} == {"PZ", "TZ", "CZ", "AS"}
    assert P.zona_do_setor("medio_PZpl_D") == "PZ" and P.zona_do_setor("VS_D") == ""
    x, y = P.centro_do_setor("medio_PZpl_D")
    assert 0 < x < 0.5 and 0.4 < y < 0.8                     # à direita do paciente (esquerda da figura), no meio
    d = {"psa": "6,2", "psa_data": "2026-10-12", "diametros": [45, 50, 38],
         "lesoes": [{"setores": ["medio_PZpl_D", "base_PZpl_D"], "tamanho_mm": 12, "t2": 4, "dwi": 3, "dce": "+",
                     "adc": 750, "epe": "nao"},
                    {"zona": "TZ", "setores": ["apice_TZa_E"], "tamanho_mm": 8, "t2": 2, "dwi": 4}]}
    c = P.calcular(d)
    assert c["volume_ml"] == pytest.approx(0.52 * 45 * 50 * 38 / 1000, abs=0.05) and c["volume_fonte"] == "elipsoide"
    assert c["psad"] == pytest.approx(6.2 / c["volume_ml"], abs=0.006)
    assert c["lesoes"][0]["zona"] == "PZ" and c["geral"] == "4"
    txt = P.texto_laudo(d)
    assert "zona periférica posterolateral direita, base e terço médio" in txt
    assert "T2 4, difusão 3, DCE positivo" in txt and "ADC médio de 750 × 10⁻⁶ mm²/s" in txt
    assert "PSA de 6,20 ng/mL (12/10/2026); densidade do PSA de 0,14 ng/mL/cm³" in txt
    assert "IMPRESSÃO:\nPI-RADS 4: probabilidade alta" in txt and "lesão 1" in txt
    assert P.MARCA_PESQUISA not in txt
    e = P.esquema(c)
    assert e["setores"] == {"medio_PZpl_D": "4", "base_PZpl_D": "4", "apice_TZa_E": "3"}
    assert [m["n"] for m in e["marcas"]] == [1, 2] and "PI-RADS 4 — 12 mm" == e["marcas"][0]["texto"]
    # sem lesão: a impressão diz isso; o volume automático vale no lugar do elipsoide
    vazio = P.calcular({"volume_auto": {"ml": 38.2, "fonte": "TotalSegmentator"}, "diametros": [45, 50, 38]})
    assert vazio["volume_ml"] == 38.2 and vazio["volume_fonte"] == "TotalSegmentator" and vazio["geral"] == ""
    assert "Sem lesão focal" in P.texto_impressao(vazio)
    assert P.calcular({"volume_auto": {"ml": 38.2}, "diametros": [45, 50, 38], "volume_usar": "elipsoide"})[
        "volume_fonte"] == "elipsoide"
    assert P.normalizar({"diametros": [45, 0, 0]})["diametros"] == [45.0, 0.0, 0.0]      # parcial fica
    assert P.calcular({"diametros": [45, 0, 0]})["volume_ml"] is None


def test_marca_de_pesquisa_no_texto():
    d = {"lesoes": [{"zona": "PZ", "setores": ["base_PZpl_E"], "tamanho_mm": 11, "origem": "picai",
                     "probabilidade": 0.7, "dwi": 4}]}
    c = P.calcular(d)
    assert c["pesquisa"] and c["a_conferir"] == 1 and c["lesoes"][0]["pesquisa"] and not c["lesoes"][0]["conferida"]
    txt = P.texto_laudo(d)
    assert P.MARCA_PESQUISA in txt and "ainda não conferida" in txt
    assert "a conferir" in P.esquema(c)["marcas"][0]["texto"]


# ---------------------------------------------------------------------- banco, laudo e SR
def _exame_mr(env, tmp_path, foco=True, descricao="RM PROSTATA MULTIPARAMETRICA", acesso="PR01"):
    """T2 axial (64 × 64 × 20, 1 × 1 × 3 mm) com a glândula, a zona periférica e um foco; ADC e DWI (b 0 e 1400)."""
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    zz, yy, xx = np.meshgrid(np.arange(20), np.arange(64), np.arange(64), indexing="ij")
    gl = ((xx - 32) / 14.0) ** 2 + ((yy - 30) / 11.0) ** 2 + ((zz - 10) / 5.0) ** 2 <= 1.0
    t2 = np.full(gl.shape, 100, np.int16)
    t2[gl] = 1000
    t2[gl & (yy > 33)] = 1600                                           # posterior: "zona periférica"
    foco_m = ((xx - 40) ** 2 + (yy - 36) ** 2 <= 9) & (np.abs(zz - 10) <= 1) & gl
    if foco:
        t2[foco_m] = 2600
    pat = {"name": "EXEMPLO^Prostata", "id": "PR1", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261120", "accession": acesso, "description": descricao,
             "for": generate_uid()}

    def serie(numero, desc, vol, extra=None):
        s = {"uid": generate_uid(), "number": numero, "description": desc}
        d = tmp_path / f"s{numero}_{acesso}"
        for k in range(vol.shape[0]):
            for b, img in (extra or {None: vol}).items():
                ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, s, "MR")
                ds.InstanceNumber = k + 1 + (1000 if b else 0)
                ds.ImagePositionPatient = [0.0, 0.0, 3.0 * k]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.PixelSpacing = [1.0, 1.0]
                ds.SliceThickness = 3.0
                if b is not None:
                    ds.add_new((0x0018, 0x9087), "FD", float(b))
                _mono(ds, img[k], signed=True)
                _save(ds, d)
        Importer(db, paths.storage).import_paths([d])
        return s["uid"]
    s_t2 = serie(3, "T2 TSE TRA", t2)
    serie(5, "ADC", np.where(gl, 900, 0).astype(np.int16))
    serie(4, "DWI b0 b1400", t2, {0.0: t2, 1400.0: np.where(foco_m, 900, 50).astype(np.int16)})
    return study["uid"], s_t2, gl, foco_m


def test_gravar_ler_esquema_laudo_e_sr(env, tmp_path):
    import pydicom

    from ipe.reporting import esquemas as E
    from ipe.reporting import fill as F
    from ipe.reporting import pirads_saida as PS
    from ipe.reporting.templates import best_template, default_templates
    paths, db, repo = env
    uid, _s, _g, _f = _exame_mr(env, tmp_path)
    # um esquema do médico já existe: o do PI-RADS entra ao lado, sem apagar
    E.gravar(repo, uid, [{"modelo": "face_frente", "marcas": [{"tipo": "ponto", "n": 1, "p": [[0.5, 0.5]]}]}], "dr")
    with pytest.raises(ValueError):
        PS.gravar_no_exame(repo, paths.storage, uid, "Dr. Teste")                # formulário vazio
    c = P.gravar(repo, uid, {"psa": 8, "diametros": [40, 45, 35], "lesoes": [
        {"setores": ["medio_PZpl_D"], "tamanho_mm": 14, "t2": 4, "dwi": 4, "dce": "+", "adc": 700, "epe": "nao"}]},
        "dr")
    assert c["geral"] == "4" and P.ler(repo, uid)["lesoes"][0]["zona"] == "PZ"
    lista = E.ler(repo, uid)
    assert [e["modelo"] for e in lista] == ["face_frente", "prostata"]
    assert lista[1]["setores"] == {"medio_PZpl_D": "4"} and lista[1]["id"] == P.ID_ESQUEMA
    # gravar de novo não duplica o esquema do PI-RADS
    P.gravar(repo, uid, P.ler(repo, uid), "dr")
    assert [e["modelo"] for e in E.ler(repo, uid)] == ["face_frente", "prostata"]
    # o laudo: o modelo de RM de próstata e os campos
    t = best_template(default_templates(), "MR", "RM PROSTATA MULTIPARAMETRICA")
    assert t["id"] == "rm_prostata" and "{pirads_achados}" in t["text"] and "{pirads}" in t["text"]
    ctx = F.build_context(repo, uid)
    assert "PI-RADS 4: probabilidade alta" in ctx["pirads"] and "Lesão 1 — zona periférica" in ctx["pirads_achados"]
    assert "densidade do PSA" in ctx["prostata_volume"]
    laudo = F.fill(t["text"], ctx)
    assert "{pirads" not in laudo and "IMPRESSÃO:\nPI-RADS 4" in laudo
    # SR e mapa no exame; gravar de novo troca
    for _ in range(2):
        r = PS.gravar_no_exame(repo, paths.storage, uid, "Dr. Teste")
    descs = [s.description for s in repo.series_for_study(uid, True)]
    assert descs.count(PS.DESCRICAO) == 1 and r["esquemas"] >= 1
    se = next(s for s in repo.series_for_study(uid, True) if s.description == PS.DESCRICAO)
    ds = pydicom.dcmread(repo.instances_for_series(se.series_uid)[0]["path"])
    texto = json.dumps([str(x.value) for x in ds.iterall() if x.VR in ("UT", "LO", "DS", "PN")], ensure_ascii=False)
    assert "PI-RADS 4" in texto and "Volume" in texto and "Apparent Diffusion Coefficient" in texto
    assert P.MARCA_PESQUISA not in texto and ds.VerificationFlag == "UNVERIFIED"
    # com sugestão do modelo de pesquisa: o SR leva o aviso
    P.aplicar_candidatos(repo, uid, [{"zona": "TZ", "setores": ["base_TZa_E"], "tamanho_mm": 9, "probabilidade": 0.6}])
    d = P.ler(repo, uid)
    assert [l["origem"] for l in d["lesoes"]] == ["medico", "picai"]
    sr = PS.montar_sr(repo, uid, repo.files_for_study(uid)[0], d, "Dr. Teste")
    assert P.MARCA_PESQUISA in json.dumps([str(x.value) for x in sr.iterall() if x.VR == "UT"], ensure_ascii=False)
    # uma rodada nova troca só as sugestões não conferidas
    P.aplicar_candidatos(repo, uid, [])
    assert [l["origem"] for l in P.ler(repo, uid)["lesoes"]] == ["medico"]


# ---------------------------------------------------------------------- IA: volume e modelos de pesquisa (simulados)
def _rodar(env, uid, serie, mod):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    FE.preparar_trabalho(t, mod)
    t.preparar()
    try:
        t.rodar_aqui()
        res, versao = FE.rodar_conta(t, mod, None)
        saida = FE.gravar(t, mod, res, versao, db, paths.storage, repo, None)
    finally:
        t.limpar()
    return res, saida


def test_volume_automatico_entra_no_pirads(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import prostata as PR
    paths, db, repo = env
    uid, serie, gl, _f = _exame_mr(env, tmp_path)
    assert FE.modulo("prostata") is PR
    assert PR.escolher_serie(repo, uid) == (serie, "")
    assert PR.e_t2_axial("t2_tse_tra") and not PR.e_t2_axial("T2 SAG") and not PR.e_t2_axial("ADC")
    P.gravar(repo, uid, {"psa": 6.0, "diametros": [40, 45, 35]}, "dr")
    res, saida = _rodar(env, uid, serie, PR)
    assert res.ml == pytest.approx(gl.sum() * 3 / 1000, abs=0.05)
    ap, t, cc = res.extensoes
    assert ap == pytest.approx(22, abs=2) and t == pytest.approx(28, abs=2) and cc == pytest.approx(30, abs=3.5)
    assert PR.DESC_SEG in [s.description for s in repo.series_for_study(uid)] and saida["seg_path"]
    ach = repo.achados(uid, "prostata")
    assert len(ach) == 1 and "Próstata com volume de" in PR.frase(ach[0])
    c = P.calcular(P.ler(repo, uid))
    assert c["volume_fonte"] == "TotalSegmentator" and c["volume_ml"] == pytest.approx(res.ml, abs=0.06)
    assert c["psad"] == pytest.approx(6.0 / res.ml, abs=0.01) and not c["pesquisa"]
    assert "PI-RADS" in PR.mensagem(res, 1.0)
    # as zonas (pesquisa) só rodam instaladas, com a licença e a opção ligada
    assert [t["nome"] for t in PR.tarefas("MR", None)] == ["total_mr"]


def test_picai_simulado_sugere_lesao_a_conferir(env, tmp_path, monkeypatch):
    from ipe.ai import picai as PC
    from ipe.ai import prostata as PR
    paths, db, repo = env
    uid, serie, _g, foco = _exame_mr(env, tmp_path, acesso="PR02")
    monkeypatch.setattr(PR, "zonas_prontas", lambda _s=None: True)       # o modelo das zonas (simulado) "instalado"
    assert [t["nome"] for t in PC.tarefas("MR", None)] == ["total_mr", "prostata_zonas", "picai"]
    assert PC.config(None, PC.CHAVE_AUTO) is False and not PC.exame_serve({"modalities": "MR",
                                                                            "description": "RM PROSTATA"})
    res, saida = _rodar(env, uid, serie, PC)
    assert [c.probabilidade for c in res.candidatos] == [0.73]
    c = res.candidatos[0]
    assert c.lado == "E" and c.nivel == "medio" and c.zona == "PZ" and c.setores == ["medio_PZpl_E"]
    assert c.ml == pytest.approx(foco.sum() * 3 / 1000, abs=0.01)
    assert PC.DESC_SEG in [s.description for s in repo.series_for_study(uid)]
    ach = repo.achados(uid, "picai")
    assert len(ach) == 1 and ach[0]["elegibilidade"].startswith(P.MARCA_PESQUISA.upper())
    assert P.MARCA_PESQUISA in PC.frase(ach[0]) and PC.mensagem(res, 1.0).startswith("MODELO DE PESQUISA")
    d = P.calcular(P.ler(repo, uid))
    les = d["lesoes"][0]
    assert les["origem"] == "picai" and les["pesquisa"] and not les["conferida"] and les["setores"] == ["medio_PZpl_E"]
    assert les["imagem"]["sop_uid"] and d["pesquisa"] and d["a_conferir"] == 1
    # o médico confere: continua marcada como de pesquisa, mas "conferida"
    dd = P.ler(repo, uid)
    dd["lesoes"][0].update({"conferida": True, "dwi": 4})
    c2 = P.gravar(repo, uid, dd, "dr")
    assert c2["a_conferir"] == 0 and c2["pesquisa"] and "conferida pelo médico" in P.texto_laudo(c2)
    # a zona (pesquisa) do volume
    res_v, _s = _rodar(env, uid, serie, PR)
    assert res_v.zonas is None                                           # a opção das zonas está desligada


# ---------------------------------------------------------------------- licença dos modelos de pesquisa
def test_licenca_instalador_e_prontidao(tmp_path, monkeypatch):
    from ipe.ai import extras as EX
    from ipe.ai import instalar_modelos_extras as IM
    from ipe.ai import totalseg as TS
    from ipe.core.config import Settings
    st = Settings(tmp_path / "s.json")
    assert set(EX.PESQUISA) == {"prostata_zonas", "picai"} and not set(EX.PESQUISA) & set(EX.MODELOS)
    assert all(m in IM.PASSOS for m in EX.PESQUISA)
    monkeypatch.setattr(TS, "instalado", lambda _s=None: True)
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "seg")
    monkeypatch.setattr(TS, "python_do_ambiente", lambda _s=None: tmp_path / "py")
    assert not EX.licenca_aceita(st, "picai") and EX.licenca_aceita(st, "brats")
    cmd = EX.comando_do_instalador(("picai", "brats"), st)
    assert "picai" not in cmd and "brats" in cmd and "--aceito-uso-em-pesquisa" not in cmd
    a = EX.aceitar_licenca(st, "picai", "dr")
    assert a["aceite"] == EX.ACEITE and EX.licenca_aceita(Settings(tmp_path / "s.json"), "picai")
    cmd = EX.comando_do_instalador(("picai",), st)
    assert cmd[-2:] == ["picai", "--aceito-uso-em-pesquisa"]
    # o instalador: "todos" não inclui pesquisa; pedido sem o aceite é recusado sem baixar nada
    chamados = []
    monkeypatch.setattr(IM, "PASSOS", {k: (lambda k=k: chamados.append(k)) for k in IM.PASSOS})
    assert IM.main(["picai", "--sem-pausa"]) == 1 and chamados == []
    IM.main(["--sem-pausa"])
    assert set(chamados) == set(EX.MODELOS)
    chamados.clear()
    IM.main(["picai", "--aceito-uso-em-pesquisa", "--sem-pausa"])
    assert chamados == ["picai"]
    # prontidão: ambiente próprio + pesos
    assert "ambiente do PI-CAI" in EX.prontidao("picai").falta
    (tmp_path / "seg" / "venv_picai" / "bin").mkdir(parents=True)
    (tmp_path / "seg" / "venv_picai" / "bin" / "python").write_text("")
    assert "pesos do PI-CAI" in EX.prontidao("picai").falta
    f = tmp_path / "seg" / "pesos" / "picai" / IM.PICAI_PASTA / "fold_0"
    f.mkdir(parents=True)
    (f / "model_best.model").write_bytes(b"x")
    assert EX.prontidao("picai").pronto
    sp = tmp_path / "seg" / "venv" / "lib" / "python3.12" / "site-packages" / "monai"
    sp.mkdir(parents=True)
    assert "zonas" in EX.prontidao("prostata_zonas").falta
    (tmp_path / "seg" / "pesos" / "prostata_zonas").mkdir(parents=True)
    (tmp_path / "seg" / "pesos" / "prostata_zonas" / "model.pt").write_bytes(b"x")
    assert EX.prontidao("prostata_zonas").pronto
    assert "pesquisa" in EX.motivo("picai", None) or EX.prontidao("picai").pronto
    assert all(k in EX.LICENCAS for k in EX.PESQUISA) and "CC BY-NC-SA 4.0" in EX.LICENCAS["picai"]["texto"]


def test_trabalhador_mapa_de_deteccao_em_rotulos():
    from ipe.ai import totalseg_worker as W
    det = np.zeros((3, 4, 4), np.float32)
    det[0, :2, :2] = 0.81
    det[2, 2:, 2:] = 0.25
    lab, cl = W._rotulos_do_mapa(det)
    assert cl == {1: "cspca_0.8100", 2: "cspca_0.2500"} and (lab == 1).sum() == 4 and (lab == 2).sum() == 4


# ---------------------------------------------------------------------- Ipê Web (as rotas) e a janela do Ipê de mesa
class _Sessao:
    def __init__(self, perms):
        self.perms, self.username, self.full_name = set(perms), "dr", "Dr. Teste"

    def can(self, p):
        return p in self.perms


class _C:
    def __init__(self, repo, storage):
        self.repo, self.storage = repo, storage

    def pode_ver(self, _s, _study):
        return True


def test_rotas_do_web(env, tmp_path):
    from ipe.central import pirads_web as PW
    paths, db, repo = env
    uid, _s, _g, _f = _exame_mr(env, tmp_path)
    c = _C(repo, paths.storage)
    leitor, medico = _Sessao({"view"}), _Sessao({"view", "report"})
    r = PW.rota(c, medico, "GET", "estado", {"study": [uid]}, {})
    assert r["pode"] and len(r["setores"]) == 38 and r["estado"]["lesoes"] == [] and r["marca_pesquisa"]
    est = {"psa": 5, "lesoes": [{"setores": ["apice_PZpl_D"], "dwi": 5, "tamanho_mm": 18}]}
    calc = PW.rota(c, leitor, "POST", "calcular", {}, {"study": uid, "estado": est})
    assert calc["estado"]["geral"] == "5" and not calc["pode"] and P.ler(repo, uid) is None
    with pytest.raises(PermissionError):
        PW.rota(c, leitor, "POST", "gravar", {}, {"study": uid, "estado": est})
    sop = repo.instances_for_series(_s)[0]["sop_uid"]
    est["lesoes"][0]["imagem"] = {"series_uid": _s, "sop_uid": sop, "frame": 0}
    g = PW.rota(c, medico, "POST", "gravar", {}, {"study": uid, "estado": est})
    assert g["estado"]["geral"] == "5" and g["esquema"]["setores"] == {"apice_PZpl_D": "5"}
    assert P.ler(repo, uid)["lesoes"][0]["imagem"]["rotulo"]                  # rótulo e imagem-chave pelo servidor
    assert "IMPRESSÃO" in g["texto"]
    ok = PW.rota(c, medico, "POST", "no_exame", {}, {"study": uid})
    assert ok["ok"] and ok["sr"]
    with pytest.raises(LookupError):
        PW.rota(c, medico, "GET", "nada", {}, {})


def test_janela_do_ipe_de_mesa(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ui import pirads_dialogo as PD
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s, _g, _f = _exame_mr(env, tmp_path)
    w = PD.PiradsDialog(repo, uid, "dr", True, None, paths.storage)
    w.show()
    try:
        assert not w.faixa.isVisible()
        w.resize(1180, 780)
        w.psa.setValue(7.5)
        for s, v in zip(w.diam, (40, 45, 35)):
            s.setValue(v)
        w._setor_clicado("medio_PZpl_D")                         # sem lesão: o clique cria a lesão no setor
        assert w.atual == 0 and w.d["lesoes"][0]["setores"] == ["medio_PZpl_D"]
        assert w.zona.currentData() == "PZ"
        w.dwi.setCurrentIndex(w.dwi.findData(3))
        w.dce.setCurrentIndex(w.dce.findData("+"))
        app.processEvents()
        assert w.l_cat.text() == "PI-RADS 4" and "PI-RADS geral: 4" in w.l_geral.text()
        assert "Densidade do PSA" in w.l_volume.text()
        w._setor_clicado("base_PZpl_D")
        assert w.d["lesoes"][0]["setores"] == ["medio_PZpl_D", "base_PZpl_D"]
        if os.environ.get("IPE_PIRADS_FOTO"):
            app.processEvents()
            w.grab().save(os.environ["IPE_PIRADS_FOTO"] + "_mesa.png")
        assert w.salvar()
        d = P.ler(repo, uid)
        assert d["psa"] == 7.5 and d["lesoes"][0]["dce"] == "+" and P.calcular(d)["geral"] == "4"
        w._ao_laudo()                                            # sem visualizador: vai para a área de transferência
        assert "PI-RADS 4" in QApplication.clipboard().text()
        assert PD.adc_em_micro(0.00085) == 850 and PD.adc_em_micro(0.85) == 850 and PD.adc_em_micro(850.4) == 850
        # sugestão de pesquisa: a faixa vermelha aparece
        P.aplicar_candidatos(repo, uid, [{"zona": "TZ", "setores": ["base_TZa_E"], "probabilidade": 0.5}])
        w.recarregar()
        assert w.faixa.isVisible() and "a conferir" in w.faixa.text()
    finally:
        w.close()
        app.processEvents()
