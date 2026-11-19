"""0.100.71: Cadastros no Ipê Web — usuários e perfis, nós DICOM e identidades, impressoras DICOM, automações de IA
e o registro de acesso; só administradores. Servidor de verdade em loopback; nomes inventados."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture()
def servidor(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from pynetdicom import AE, evt
    from pynetdicom.sop_class import Verification
    from test_network import free_port
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.printing import config as C
    from ipe.printing import dispatch as D
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "med", "full_name": "Médica", "role": "medico", "password": "medica12"})
    st = Settings(paths.settings_file)
    porta_imp = free_port()
    C.save_servers(st, [C.ServerConfig(name="Filmes", enabled=True, ae_title="PRNIPE", port=porta_imp, to_database=False)])
    st.set("dicom", dict(st.get("dicom", {}), enabled=False, http_enabled=False))
    st.set("printing.dicom_printers", [{"name": "Dry da TC", "ae_title": "DRYTC", "host": "10.9.9.9", "port": 104,
                                        "min_density": 12}])
    D.save_destinations(st, [D.Destination(name="Filme da TC", kind="dicom", dicom_printer="Dry da TC")])
    st.save()
    net = NetworkService(db, repo, paths.storage, st)
    assert net.start_print_servers() == 1
    # um "PACS" que só responde ao eco
    porta_pacs = free_port()
    ae = AE(ae_title="PACSECO")
    ae.add_supported_context(Verification)
    scp = ae.start_server(("127.0.0.1", porta_pacs), block=False, evt_handlers=[(evt.EVT_C_ECHO, lambda e: 0x0000)])
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings, srv.net = st, net
    srv.start()
    srv.app, srv.repo_, srv.st, srv.porta_imp, srv.porta_pacs = app, repo, st, porta_imp, porta_pacs
    yield srv
    srv.stop()
    scp.shutdown()
    try:
        net.stop_print_servers()
    except Exception:  # noqa: BLE001
        pass


def _login(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def _token(srv, u="admin", p="admin123"):
    return _login(srv, u, p)["token"]


def _api(srv, rota, corpo=None, tok=None):
    tok = tok or _token(srv)
    caixa = {}

    def ir():
        req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/web/cadastros/{rota}",
                                     method="POST" if corpo is not None else "GET",
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            caixa["r"] = urllib.request.urlopen(req).read()
        except urllib.error.HTTPError as e:
            caixa["e"] = (e.code, json.loads(e.read().decode("utf-8", "replace")).get("error", ""))
    t = threading.Thread(target=ir)
    t.start()
    while t.is_alive():
        srv.app.processEvents()
        time.sleep(0.01)
    if "e" in caixa:
        raise AssertionError(caixa["e"])
    return json.loads(caixa["r"])


def _erro(srv, rota, corpo=None, tok=None):
    try:
        _api(srv, rota, corpo, tok)
    except AssertionError as e:
        return e.args[0]
    return (200, "")


def _usuario(srv, nome):
    return next(u for u in _api(srv, "usuarios")["usuarios"] if u["username"] == nome)


def test_so_administrador(servidor):
    srv = servidor
    med = _token(srv, "med", "medica12")
    for rota in ("usuarios", "nos", "impressoras", "ia", "registro"):
        assert _erro(srv, rota, tok=med)[0] == 403, rota
    for rota in ("usuario", "usuario_senha", "usuario_excluir", "perfis", "no", "no_excluir", "no_testar", "identidade",
                 "identidade_excluir", "impressora", "impressora_excluir", "impressora_testar", "ia"):
        assert _erro(srv, rota, {}, tok=med)[0] == 403, rota
    assert _erro(srv, "apagar_tudo", {})[0] == 404
    assert len(srv.repo_.users()) == 2 and not srv.repo_.nodes(todos=True)
    # a própria senha qualquer pessoa troca
    assert _erro(srv, "minha_senha", {"atual": "errada", "nova": "outra123"}, tok=med) == (400, "A senha atual não confere.")
    assert _erro(srv, "minha_senha", {"atual": "medica12", "nova": "123"}, tok=med)[0] == 400
    assert _erro(srv, "minha_senha", {"atual": "medica12", "nova": "medica12"}, tok=med)[0] == 400
    assert _api(srv, "minha_senha", {"atual": "medica12", "nova": "outra123"}, tok=med)["ok"]
    assert _login(srv, "med", "outra123")["must_change"] is False


def test_usuarios(servidor):
    srv = servidor
    adm = _token(srv)
    r = _api(srv, "usuarios", tok=adm)
    assert r["eu"] == "admin" and [u["username"] for u in r["usuarios"]] == ["admin", "med"]
    assert {p["k"] for p in r["papeis"]} == {"admin", "medico", "residente", "tecnico"}
    assert "password" not in json.dumps(r) and "hash" not in json.dumps(r)
    # criar: senha curta, usuário vazio, repetido
    assert _erro(srv, "usuario", {"username": "tec", "role": "tecnico", "password": "123"}, adm)[0] == 400
    assert _erro(srv, "usuario", {"username": "", "role": "tecnico", "password": "tecnica1"}, adm) == (400, "Preencha o usuário.")
    assert _erro(srv, "usuario", {"username": "tec", "role": "chefe", "password": "tecnica1"}, adm)[0] == 400
    assert _api(srv, "usuario", {"username": "tec", "full_name": "Técnica Um", "role": "tecnico", "password": "tecnica1"}, adm)["ok"]
    assert "Já existe" in _erro(srv, "usuario", {"username": "TEC", "role": "tecnico", "password": "tecnica1"}, adm)[1]
    u = _usuario(srv, "tec")
    assert u["papel"] == "Técnico" and u["active"] and u["must_change"]
    entrou = _login(srv, "tec", "tecnica1")
    assert entrou["must_change"] is True and entrou["role"] == "tecnico"
    tok_tec = entrou["token"]
    # a senha provisória é trocada pela própria pessoa
    assert _api(srv, "minha_senha", {"atual": "tecnica1", "nova": "minha-senha"}, tok_tec)["ok"]
    assert not _usuario(srv, "tec")["must_change"]
    # editar o perfil: a sessão aberta passa a valer com o perfil novo, sem cair
    assert _api(srv, "usuario", {"id": u["id"], "full_name": "Técnica Um", "role": "admin", "active": True}, adm)["ok"]
    assert _api(srv, "usuarios", tok=tok_tec)["eu"] == "tec"
    assert _api(srv, "usuario", {"id": u["id"], "full_name": "Técnica Um", "role": "tecnico", "active": True}, adm)["ok"]
    assert _erro(srv, "usuarios", tok=tok_tec)[0] == 403
    assert srv.repo_.authenticate("tec", "minha-senha")              # editar sem senha não mexe na senha
    # redefinir: provisória de novo, e a sessão aberta cai
    assert _erro(srv, "usuario_senha", {"id": u["id"], "senha": "1"}, adm)[0] == 400
    assert _api(srv, "usuario_senha", {"id": u["id"], "senha": "provisoria"}, adm)["ok"]
    assert _erro(srv, "minha_senha", {"atual": "x", "nova": "yyyyyy"}, tok_tec)[0] == 401
    assert _login(srv, "tec", "provisoria")["must_change"] is True
    # desativar: não entra mais, e a sessão cai
    tok_tec = _token(srv, "tec", "provisoria")
    assert _api(srv, "usuario", {"id": u["id"], "full_name": "Técnica Um", "role": "tecnico", "active": False}, adm)["ok"]
    assert _erro(srv, "minha_senha", {"atual": "x", "nova": "yyyyyy"}, tok_tec)[0] == 401
    with pytest.raises(urllib.error.HTTPError):
        _login(srv, "tec", "provisoria")
    # sempre sobra um administrador ativo; ninguém exclui a si mesmo
    eu = _usuario(srv, "admin")
    msg = "Precisa sobrar pelo menos um administrador ativo."
    assert _erro(srv, "usuario", {"id": eu["id"], "role": "medico", "active": True}, adm) == (400, msg)
    assert _erro(srv, "usuario", {"id": eu["id"], "role": "admin", "active": False}, adm) == (400, msg)
    assert _erro(srv, "usuario_excluir", {"id": eu["id"]}, adm) == (400, "Você não pode excluir o próprio usuário.")
    assert _erro(srv, "usuario_excluir", {"id": 99999}, adm)[0] == 404
    assert _api(srv, "usuario_excluir", {"id": u["id"]}, adm)["ok"]
    assert [x["username"] for x in _api(srv, "usuarios", tok=adm)["usuarios"]] == ["admin", "med"]
    # o administrador continua dentro depois de tudo, e o registro guarda quem fez
    acoes = [a["detail"] for a in srv.repo_.access_log(action="usuarios")]
    assert any("criou tec" in a for a in acoes) and any("redefiniu a senha de tec" in a for a in acoes)
    assert any("excluiu tec" in a for a in acoes) and all("provisoria" not in a and "tecnica1" not in a for a in acoes)
    assert {a["user"] for a in srv.repo_.access_log(action="usuarios") if "tec" in a["detail"] and "própria" not in a["detail"]} == {"admin"}


def test_perfis(servidor):
    srv = servidor
    adm = _token(srv)
    r = _api(srv, "usuarios", tok=adm)
    assert "delete" in r["perfis"]["medico"] and "configure" not in r["perfis"]["medico"]
    tabela = {k: [p for p in v if p != "delete"] for k, v in r["perfis"].items()}
    tabela["admin"] = []                                 # o administrador sempre pode tudo: a tela não tira
    tabela["medico"].append("inventada")
    assert _api(srv, "perfis", {"perfis": tabela}, adm)["ok"]
    r = _api(srv, "usuarios", tok=adm)
    assert "delete" not in r["perfis"]["medico"] and "inventada" not in r["perfis"]["medico"]
    assert "delete" in r["perfis"]["admin"]
    assert "delete" not in _login(srv, "med", "medica12")["perms"]
    assert _api(srv, "perfis", {"padrao": True}, adm)["ok"]
    assert "delete" in _login(srv, "med", "medica12")["perms"]
    assert _erro(srv, "perfis", {}, adm)[0] == 400


def test_nos_e_identidades(servidor):
    srv = servidor
    adm = _token(srv)
    assert _api(srv, "nos", tok=adm)["nos"] == []
    base = {"kind": "dimse", "name": "PACS de teste", "ae_title": "PACSECO", "host": "127.0.0.1", "port": srv.porta_pacs}
    assert _erro(srv, "no", {**base, "name": ""}, adm) == (400, "Preencha o nome.")
    assert _erro(srv, "no", {**base, "host": ""}, adm)[0] == 400
    assert "AE Title" in _erro(srv, "no", {**base, "ae_title": "AE COMPRIDO DEMAIS PARA VALER"}, adm)[1]
    # testar antes de gravar: o que está na tela
    r = _api(srv, "no_testar", base, adm)
    assert r["ok"] and "Responde em" in r["mensagem"]
    ruim = _api(srv, "no_testar", {**base, "port": 1}, adm)
    assert not ruim["ok"] and ruim["mensagem"].startswith("Sem resposta")
    assert not _api(srv, "no_testar", {**base, "host": ""}, adm)["ok"]
    nid = _api(srv, "no", {**base, "retrieve": "move", "move_destination": "IPE", "use_in_send": False, "priority": 3}, adm)["id"]
    n = _api(srv, "nos", tok=adm)["nos"][0]
    assert n["id"] == nid and n["endereco"] == f"PACSECO @ 127.0.0.1:{srv.porta_pacs}" and n["retrieve"] == "move"
    assert n["use_in_search"] and not n["use_in_send"] and n["active"] and n["priority"] == 3
    assert _api(srv, "no_testar", {**n}, adm)["ok"]
    # DICOMweb: a senha e o segredo ficam no servidor
    web = {"kind": "dicomweb", "name": "Orthanc", "base_url": "http://127.0.0.1:1/dicom-web/", "username": "leitura",
           "password": "segredo-do-no", "verify_tls": False}
    assert _erro(srv, "no", {**web, "base_url": "orthanc"}, adm)[0] == 400
    assert "OAuth2" in _erro(srv, "no", {**web, "auth": "oauth2_cliente"}, adm)[1]
    wid = _api(srv, "no", web, adm)["id"]
    lista = _api(srv, "nos", tok=adm)
    w = next(x for x in lista["nos"] if x["id"] == wid)
    assert w["tem_senha"] and w["base_url"] == "http://127.0.0.1:1/dicom-web" and not w["verify_tls"]
    assert "segredo-do-no" not in json.dumps(lista) and "password" not in w
    # editar sem a senha: fica a que estava; "apagar" tira
    assert _api(srv, "no", {**w, "name": "Orthanc da sala"}, adm)["ok"]
    gravado = next(x for x in srv.repo_.nodes(todos=True) if x["id"] == wid)
    assert gravado["name"] == "Orthanc da sala" and gravado["password"] == "segredo-do-no"
    assert _api(srv, "no", {**w, "apagar_senha": True}, adm)["ok"]
    assert next(x for x in srv.repo_.nodes(todos=True) if x["id"] == wid)["password"] == ""
    assert not _api(srv, "no_testar", {**w}, adm)["ok"]            # nada escuta ali
    # identidades
    assert "AE Title" in _erro(srv, "identidade", {"name": "Estação", "ae_title": ""}, adm)[1]
    assert _api(srv, "identidade", {"name": "Estação da mama", "ae_title": "WSMAMA", "allowed_nodes": [nid, 424242]}, adm)["ok"]
    i = _api(srv, "nos", tok=adm)["identidades"][0]
    assert i["ae_title"] == "WSMAMA" and i["allowed_nodes"] == [nid]
    assert _api(srv, "no_testar", {**n, "identidade": i["id"]}, adm)["ok"]
    assert _api(srv, "identidade", {**i, "name": "Estação 2", "allowed_nodes": []}, adm)["ok"]
    assert _api(srv, "nos", tok=adm)["identidades"][0]["name"] == "Estação 2"
    assert _api(srv, "identidade_excluir", {"id": i["id"]}, adm)["ok"]
    assert _api(srv, "no_excluir", {"id": wid}, adm)["ok"] and _erro(srv, "no_excluir", {"id": wid}, adm)[0] == 404
    assert [x["name"] for x in _api(srv, "nos", tok=adm)["nos"]] == ["PACS de teste"]
    textos = [a["detail"] for a in srv.repo_.access_log(action="config")]
    assert any("criou o nó DICOM PACS de teste" in t for t in textos) and all("segredo" not in t for t in textos)


def test_impressoras(servidor):
    from ipe.printing import dispatch as D
    srv = servidor
    adm = _token(srv)
    r = _api(srv, "impressoras", tok=adm)
    assert [p["name"] for p in r["impressoras"]] == ["Dry da TC"] and r["impressoras"][0]["usada_em"] == ["Filme da TC"]
    assert "8INX10IN" in r["tamanhos"] and "BLUE FILM" in r["midias"]
    nova = {"name": "Dry da mamo", "ae_title": "PRNIPE", "host": "127.0.0.1", "port": srv.porta_imp, "medium": "MAMMO BLUE FILM",
            "film_size": "8INX10IN", "dpi": 300, "compartilhar_clientes": True}
    assert _erro(srv, "impressora", {**nova, "host": ""}, adm) == (400, "Preencha o AE e o IP da impressora.")
    assert _erro(srv, "impressora", {**nova, "name": "dry da tc"}, adm) == (400, "Já existe a impressora dry da tc.")
    # o teste fala com a impressora (aqui, o servidor de impressão do próprio Ipê)
    t = _api(srv, "impressora_testar", nova, adm)
    assert t["ok"] and t["mensagem"].startswith("Conectou")
    assert not _api(srv, "impressora_testar", {**nova, "port": 1}, adm)["ok"]
    assert _api(srv, "impressora", nova, adm)["ok"]
    guardadas = srv.st.get("printing.dicom_printers")
    assert [p["name"] for p in guardadas] == ["Dry da TC", "Dry da mamo"]
    assert guardadas[1]["medium"] == "MAMMO BLUE FILM" and guardadas[1]["dpi"] == 300 and guardadas[1]["compartilhar_clientes"]
    # trocar o nome acompanha o destino de impressão; o que a tela não mostra fica
    tc = r["impressoras"][0]
    assert _api(srv, "impressora", {**tc, "original": "Dry da TC", "name": "Dry da tomografia", "host": "10.9.9.10"}, adm)["ok"]
    guardadas = srv.st.get("printing.dicom_printers")
    assert guardadas[0]["name"] == "Dry da tomografia" and guardadas[0]["host"] == "10.9.9.10" and guardadas[0]["min_density"] == 12
    assert D.all_destinations(srv.st)[0].dicom_printer == "Dry da tomografia"
    assert _erro(srv, "impressora", {**tc, "original": "Não existe"}, adm)[0] == 404
    # excluir a que está num destino pede confirmação
    r = _api(srv, "impressora_excluir", {"name": "Dry da tomografia"}, adm)
    assert not r["ok"] and r["usada_em"] == ["Filme da TC"] and len(srv.st.get("printing.dicom_printers")) == 2
    assert _api(srv, "impressora_excluir", {"name": "Dry da tomografia", "confirmar": True}, adm)["ok"]
    assert _api(srv, "impressora_excluir", {"name": "Dry da mamo"}, adm)["ok"]
    assert srv.st.get("printing.dicom_printers") == [] and _api(srv, "impressoras", tok=adm)["impressoras"] == []


def test_automacoes_de_ia(servidor):
    from ipe.ai import totalseg as TS
    from ipe.automation import mama_auto as MA
    srv = servidor
    adm = _token(srv)
    nid = srv.repo_.save_node({"name": "PACS", "kind": "dimse", "ae_title": "PACS", "host": "10.1.1.1", "port": 104,
                               "active": True, "use_in_send": True})
    r = _api(srv, "ia", tok=adm)
    ids = [f["id"] for f in r["ferramentas"]]
    assert ids[:7] == ["seg", "coluna", "implante", "mama", "cefalo", "neuro", "linfonodos"] and "calcio" in ids
    assert r["nos"] == [{"id": nid, "nome": "PACS  (PACS)"}]
    seg = r["ferramentas"][0]
    campos = {c["k"]: c for c in seg["campos"]}
    assert campos[TS.CHAVE_AUTO]["tipo"] == "bool" and campos[TS.CHAVE_DESTINOS]["tipo"] == "nos"
    assert [o["k"] for o in campos[TS.CHAVE_MODALIDADES]["opcoes"]] == ["CT", "MR"]
    assert "liver" in campos[TS.CHAVE_ESTRUTURAS]["valor"]
    for f in r["ferramentas"]:                                  # toda ferramenta tem o "automático" entre os campos
        assert f["auto"] in {c["k"] for c in f["campos"]}, f["id"]
    antes_mama = bool(srv.st.get(MA.CHAVE, True))
    valores = {TS.CHAVE_AUTO: True, TS.CHAVE_EXAME_CONTEM: " ABDOME|FIGADO ", TS.CHAVE_MODALIDADES: ["MR", "XA"],
               TS.CHAVE_ESPESSURA: 99, TS.CHAVE_MIN_CORTES: 3, TS.CHAVE_ESTRUTURAS: ["spleen", "liver", "inventada"],
               TS.CHAVE_DESTINOS: [nid, 777], MA.CHAVE: not antes_mama, "cad.ler_antes": True,
               "dicom": {"enabled": True}, "seg.python": "/tmp/outro"}
    g = _api(srv, "ia", {"valores": valores}, adm)
    assert g["ok"] and g["mudou"] >= 2
    st = srv.st
    assert st.get(TS.CHAVE_AUTO) is True and st.get(TS.CHAVE_EXAME_CONTEM) == "ABDOME|FIGADO"
    assert st.get(TS.CHAVE_MODALIDADES) == ["MR"] and st.get(TS.CHAVE_ESPESSURA) == 20 and st.get(TS.CHAVE_MIN_CORTES) == 20
    assert st.get(TS.CHAVE_ESTRUTURAS) == ["liver", "spleen"] and st.get(TS.CHAVE_DESTINOS) == [nid]
    assert st.get(MA.CHAVE) is (not antes_mama) and st.get("cad.ler_antes") is True
    # só as chaves das ferramentas: o resto do pedido não entra nas configurações
    assert st.get("dicom", {}).get("enabled") is False and not st.get("seg.python", "")
    r2 = _api(srv, "ia", tok=adm)
    assert r2["ler_antes"] and r2["ferramentas"][0]["ligada"]
    assert next(f for f in r2["ferramentas"] if f["id"] == "mama")["ligada"] is (not antes_mama)
    # gravou no arquivo: outra leitura das configurações vê
    from ipe.core.config import Settings
    assert Settings(st.path).get(TS.CHAVE_AUTO) is True
    assert _api(srv, "ia", {"valores": valores}, adm)["mudou"] == 0
    assert "Marque pelo menos uma" in _erro(srv, "ia", {"valores": {TS.CHAVE_ESTRUTURAS: []}}, adm)[1]
    assert _erro(srv, "ia", {"valores": {TS.CHAVE_ESPESSURA: "abc"}}, adm)[0] == 400
    assert any("Segmentação abdominal: automático" in a["detail"] for a in srv.repo_.access_log(action="config"))


def test_registro_e_idioma(servidor):
    srv = servidor
    adm = _token(srv)
    _api(srv, "usuario", {"username": "res", "role": "residente", "password": "resid123"}, adm)
    r = _api(srv, "registro", tok=adm)
    assert r["linhas"] and r["linhas"][0]["acao"] == "usuarios" and "criou res" in r["linhas"][0]["detalhe"]
    assert r["linhas"][0]["usuario"] == "admin" and "usuarios" in r["acoes"] and "admin" in r["usuarios"]
    assert _api(srv, "registro?usuario=med", tok=adm)["linhas"] == []
    assert _api(srv, "registro?texto=nada-disso", tok=adm)["linhas"] == []
    assert len(_api(srv, "registro?acao=usuarios&dias=0", tok=adm)["linhas"]) == 1
    # no idioma do navegador: os textos do programa, nunca os nomes
    en = _api(srv, "usuarios?lang=en", tok=adm)
    assert {p["nome"] for p in en["papeis"]} >= {"Administrator", "Physician"}
    assert next(u for u in en["usuarios"] if u["username"] == "res")["papel"] == "Resident"
    assert any(p["nome"] == "Delete studies" for p in en["permissoes"])
    ia = _api(srv, "ia?lang=en", tok=adm)
    assert ia["ferramentas"][0]["nome"] == "Abdominal segmentation"
    assert _erro(srv, "usuario?lang=en", {"username": "", "role": "medico", "password": "abcdef"}, adm)[1] == "Fill in the user name."
    assert _erro(srv, "usuario?lang=es", {"username": "x", "role": "medico", "password": "1"}, adm)[1] != \
        "A senha precisa ter pelo menos 6 caracteres."


# ---------------------------------------------------------------------- o navegador
def _ate(srv, f, t=40.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()
        try:
            if f():
                return True
        except Exception:  # noqa: BLE001 - a página ainda montando
            pass
        time.sleep(0.05)
    return False


def _entrar(srv, b, usuario, senha, erros):
    pg = b.new_page(viewport={"width": 1500, "height": 950})
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.fill("#usuario", usuario)
    pg.fill("#senha", senha)
    pg.click("button[type=submit]")
    assert _ate(srv, lambda: pg.locator("form.filtros").count() > 0)
    return pg


def test_no_navegador(servidor):
    import os

    from ipe.ai import totalseg as TS
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    foto = os.environ.get("IPE_CAD_FOTO")
    jan = "dialog.imp-janela"
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = _entrar(srv, b, "med", "medica12", erros)
        assert pg.locator("button.cadastros-abrir").is_hidden()
        pg.close()
        pg = _entrar(srv, b, "admin", "admin123", erros)
        assert pg.locator("button.cadastros-abrir").is_visible()
        pg.click("button.cadastros-abrir")
        assert _ate(srv, lambda: pg.locator(".cad-usuarios tbody tr[data-u]").count() == 2)
        est = lambda: pg.evaluate("() => window.__ipeCadastros.estado()")   # noqa: E731
        nota = lambda: pg.locator(".cadastros .imp-nota").inner_text()       # noqa: E731
        # ---- usuários: criar com senha curta (o erro fica na janela), depois certo
        pg.click(".imp-barra button:has-text('Novo usuário')")
        pg.fill(f"{jan} #cad-username", "tec")
        pg.fill(f"{jan} #cad-full_name", "Técnica Um")
        pg.select_option(f"{jan} #cad-role", label="Técnico")
        pg.fill(f"{jan} #cad-password", "123")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: "6 caracteres" in pg.locator(f"{jan} .cad-erro").inner_text())
        pg.fill(f"{jan} #cad-password", "provisoria")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: pg.locator(jan).count() == 0 and "tec" in nota())
        assert _ate(srv, lambda: "troca a senha" in pg.locator(".cad-usuarios tr[data-u=tec] .sit").inner_text())
        if foto:
            pg.screenshot(path=foto + "_usuarios.png")
        # editar: o usuário não muda, o nome sim
        pg.click(".cad-usuarios tr[data-u=tec] button:has-text('Editar')")
        assert pg.locator(f"{jan} #cad-username").get_attribute("readonly") is not None
        pg.fill(f"{jan} #cad-full_name", "Técnica da tarde")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: "Técnica da tarde" in pg.locator(".cad-usuarios tr[data-u=tec]").inner_text())
        # perfis: tirar "Apagar exames" do médico
        pg.click(".imp-barra button:has-text('Perfis e permissões')")
        caixa = pg.locator(f"{jan} input[aria-label='Médico: Apagar exames']")
        assert caixa.is_checked() and pg.locator(f"{jan} input[aria-label='Administrador: Apagar exames']").is_disabled()
        caixa.uncheck()
        if foto:
            pg.screenshot(path=foto + "_perfis.png")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: pg.locator(jan).count() == 0)
        assert "delete" not in _login(srv, "med", "medica12")["perms"]
        # o último administrador não se desativa: o erro aparece na tela
        pg.click(".cad-usuarios tr[data-u=admin] button:has-text('Desativar')")
        assert _ate(srv, lambda: "administrador ativo" in nota())
        # ---- nós DICOM: novo, testar na janela, gravar
        pg.click("button[data-aba=nos]")
        assert _ate(srv, lambda: "Nenhum nó DICOM" in pg.locator(".cad-nos").inner_text())
        pg.click(".imp-barra button:has-text('Novo nó DICOM')")
        assert pg.locator(f"{jan} #cad-base_url").is_hidden() and pg.locator(f"{jan} #cad-ae_title").is_visible()
        pg.select_option(f"{jan} #cad-kind", index=1)
        assert pg.locator(f"{jan} #cad-base_url").is_visible() and pg.locator(f"{jan} #cad-ae_title").is_hidden()
        assert pg.locator(f"{jan} #cad-token_url").is_hidden()
        pg.select_option(f"{jan} #cad-kind", index=0)
        pg.fill(f"{jan} #cad-name", "PACS de teste")
        pg.fill(f"{jan} #cad-ae_title", "PACSECO")
        pg.fill(f"{jan} #cad-host", "127.0.0.1")
        pg.fill(f"{jan} #cad-port", str(srv.porta_pacs))
        pg.click(f"{jan} button:has-text('Testar rede')")
        assert _ate(srv, lambda: "Responde em" in pg.locator(f"{jan} .cad-teste").inner_text())
        if foto:
            pg.screenshot(path=foto + "_no.png")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: pg.locator(".cad-nos tr[data-no='PACS de teste']").count() == 1)
        pg.click(".cad-nos tr[data-no='PACS de teste'] button:has-text('Testar')")
        assert _ate(srv, lambda: "Responde em" in pg.locator(".cad-nos tr[data-no='PACS de teste'] .sit").inner_text())
        # identidade, só para aquele nó
        pg.click(".imp-barra button:has-text('Nova identidade')")
        pg.fill(f"{jan} #cad-name", "Estação da mama")
        pg.fill(f"{jan} #cad-ae_title", "WSMAMA")
        pg.locator(f"{jan} .cad-lista input[type=checkbox]").first.check()
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: "PACS de teste" in pg.locator(".cad-identidades tr[data-id='Estação da mama']").inner_text())
        # ---- impressoras: editar a que existe, testar a nova
        pg.click("button[data-aba=impressoras]")
        assert _ate(srv, lambda: pg.locator(".cad-impressoras tr[data-imp]").count() == 1)
        assert "Filme da TC" in pg.locator(".cad-impressoras tr[data-imp='Dry da TC'] .sit").inner_text()
        pg.click(".imp-barra button:has-text('Nova impressora DICOM')")
        pg.fill(f"{jan} #cad-name", "Dry da mamo")
        pg.fill(f"{jan} #cad-ae_title", "PRNIPE")
        pg.fill(f"{jan} #cad-host", "127.0.0.1")
        pg.fill(f"{jan} #cad-port", str(srv.porta_imp))
        pg.select_option(f"{jan} #cad-medium", label="MAMMO BLUE FILM")
        pg.click(f"{jan} button:has-text('Testar conexão')")
        assert _ate(srv, lambda: "Conectou" in pg.locator(f"{jan} .cad-teste").inner_text())
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: pg.locator(".cad-impressoras tr[data-imp]").count() == 2)
        assert srv.st.get("printing.dicom_printers")[1]["medium"] == "MAMMO BLUE FILM"
        # excluir a que está num destino: avisa, e só sai confirmando duas vezes
        pg.click(".cad-impressoras tr[data-imp='Dry da TC'] button:has-text('Excluir')")
        pg.click(f"{jan} button.primario")
        assert _ate(srv, lambda: "Filme da TC" in pg.locator(jan).inner_text())
        pg.click(f"{jan} button:has-text('Cancelar')")
        assert _ate(srv, lambda: pg.locator(jan).count() == 0)
        assert len(srv.st.get("printing.dicom_printers")) == 2
        if foto:
            pg.screenshot(path=foto + "_impressoras.png")
        # ---- automações de IA: ligar a segmentação e mandar para o nó
        pg.click("button[data-aba=ia]")
        assert _ate(srv, lambda: pg.locator(".cad-ia-lista button").count() >= 7)
        assert pg.locator(".cad-ia .imp-barra, .imp-aba:not([hidden]) > .imp-barra button.primario").first.is_visible()
        salvar = pg.locator(".imp-aba:not([hidden]) > .imp-barra button.primario")
        assert salvar.is_disabled()
        assert "só à mão" in pg.locator(".cad-ia-lista button[data-f=seg]").inner_text()
        pg.check(f"[id='ia-{TS.CHAVE_AUTO}']")
        pg.fill(f"[id='ia-{TS.CHAVE_EXAME_CONTEM}']", "ABDOME")
        pg.locator(".cad-ia-painel fieldset:has(legend:has-text('enviar para')) input").first.check()
        assert "automático na chegada" in pg.locator(".cad-ia-lista button[data-f=seg]").inner_text()
        pg.click(".cad-ia-lista button[data-f=mama]")
        assert _ate(srv, lambda: "Densidade mamária" in pg.locator(".cad-ia-painel h3").inner_text())
        pg.click(".cad-ia-lista button[data-f=seg]")          # o que não foi salvo continua na tela
        assert pg.input_value(f"[id='ia-{TS.CHAVE_EXAME_CONTEM}']") == "ABDOME"
        if foto:
            pg.screenshot(path=foto + "_ia.png")
        salvar.click()
        assert _ate(srv, lambda: "gravadas" in nota())
        nid = srv.repo_.nodes(todos=True)[0]["id"]
        assert srv.st.get(TS.CHAVE_AUTO) is True and srv.st.get(TS.CHAVE_EXAME_CONTEM) == "ABDOME"
        assert srv.st.get(TS.CHAVE_DESTINOS) == [nid]
        assert _ate(srv, lambda: salvar.is_disabled() and est()["ferramentas"][0]["ligada"])
        # ---- registro
        pg.click("button[data-aba=registro]")
        assert _ate(srv, lambda: pg.locator(".cad-registro tbody tr").count() >= 5)
        assert "criou tec" in pg.locator(".cad-registro").inner_text()
        pg.fill(".imp-aba:not([hidden]) input[type=search]", "impressora")
        pg.keyboard.press("Enter")
        assert _ate(srv, lambda: pg.locator(".cad-registro tbody tr").count() == 1)
        if foto:
            pg.screenshot(path=foto + "_registro.png")
        pg.close()
        # ---- a senha provisória pede a troca ao entrar, e não dá para fugir
        pg = _entrar(srv, b, "tec", "provisoria", erros)
        assert _ate(srv, lambda: pg.locator("dialog.cad-senha").count() == 1)
        pg.keyboard.press("Escape")
        assert pg.locator("dialog.cad-senha").count() == 1
        pg.fill("dialog.cad-senha #cad-atual", "provisoria")
        pg.fill("dialog.cad-senha #cad-nova", "minha-senha")
        pg.fill("dialog.cad-senha #cad-de_novo", "outra-coisa")
        pg.click("dialog.cad-senha button.primario")
        assert _ate(srv, lambda: "não são iguais" in pg.locator("dialog.cad-senha .cad-erro").inner_text())
        pg.reload()                                           # recarregar a página não livra da troca
        assert _ate(srv, lambda: pg.locator("dialog.cad-senha").count() == 1)
        pg.fill("dialog.cad-senha #cad-atual", "provisoria")
        pg.fill("dialog.cad-senha #cad-nova", "minha-senha")
        pg.fill("dialog.cad-senha #cad-de_novo", "minha-senha")
        if foto:
            pg.screenshot(path=foto + "_senha.png")
        pg.click("dialog.cad-senha button.primario")
        assert _ate(srv, lambda: pg.locator("dialog.cad-senha").count() == 0)
        assert _login(srv, "tec", "minha-senha")["must_change"] is False
        # em inglês e num celular: a tela cabe e os textos vêm traduzidos
        pg.close()
        srv.st.set("language", "en")
        ctx = b.new_context(viewport={"width": 390, "height": 800})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        assert _ate(srv, lambda: pg.locator("button.cadastros-abrir").count() > 0)
        pg.evaluate("() => { location.hash = '#/cadastros'; }")
        assert _ate(srv, lambda: pg.locator(".cad-usuarios tbody tr[data-u]").count() == 3)
        assert "Administrator" in pg.locator(".cad-usuarios tr[data-u=admin]").inner_text()
        assert pg.locator(".cad-usuarios tr[data-u=admin] button:has-text('Reset password')").count() == 1
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2")
        if foto:
            pg.screenshot(path=foto + "_celular.png")
        pg.click("button[data-aba=ia]")
        assert _ate(srv, lambda: "Abdominal segmentation" in pg.locator(".cad-ia-lista button[data-f=seg]").inner_text())
        assert "automatic on arrival" in pg.locator(".cad-ia-lista button[data-f=seg]").inner_text().lower()
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 2")
        if foto:
            pg.screenshot(path=foto + "_celular_ia.png")
        b.close()
    assert not erros, erros
