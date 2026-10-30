"""0.99.11: o programa passou a se chamar Ipê. O que ele já tinha continua valendo."""
from __future__ import annotations

import runpy
import sys

import pytest

import ipe
from ipe.network.external import ExternalError, parse_url


def test_nome_novo_e_pasta_de_dados_antiga():
    assert ipe.APP_NAME == "Ipê" and ipe.APP_ASCII == "Ipe"
    # banco, exames e configurações continuam na pasta de sempre
    assert ipe.DATA_NAME == "DicomViewer"


def test_pasta_de_dados_usa_o_nome_antigo(monkeypatch, tmp_path):
    monkeypatch.delenv("IPE_HOME", raising=False)
    monkeypatch.delenv("DICOMVIEWER_HOME", raising=False)
    from ipe.core import config
    pastas = []
    monkeypatch.setattr(config, "user_data_dir", lambda nome, **k: pastas.append(nome) or str(tmp_path / nome))
    monkeypatch.setattr(config, "user_config_dir", lambda nome, **k: pastas.append(nome) or str(tmp_path / "cfg" / nome))
    monkeypatch.setattr(config, "user_log_dir", lambda nome, **k: pastas.append(nome) or str(tmp_path / "log" / nome))
    config.get_paths()
    assert pastas and set(pastas) == {"DicomViewer"}


def test_ipe_home_e_dicomviewer_home(monkeypatch, tmp_path):
    from ipe.core import config
    monkeypatch.delenv("IPE_HOME", raising=False)
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "velha"))
    assert str(tmp_path / "velha") in str(config.get_paths().data)
    monkeypatch.setenv("IPE_HOME", str(tmp_path / "nova"))
    assert str(tmp_path / "nova") in str(config.get_paths().data)


@pytest.mark.parametrize("url", ["ipe://open?accession=123", "dicomviewer://open?accession=123",
                                 "IPE://open?accession=123"])
def test_os_dois_links(url):
    assert parse_url(url)["accession"] == "123"


def test_outro_link_nao():
    with pytest.raises(ExternalError):
        parse_url("http://open?accession=123")


def test_python_m_dicomviewer_continua_abrindo(monkeypatch):
    chamado = []
    import ipe.__main__ as M
    monkeypatch.setattr(M, "main", lambda *a, **k: chamado.append(1) or 0)
    monkeypatch.setattr(sys, "argv", ["dicomviewer", "info"])
    sys.modules.pop("dicomviewer.__main__", None)
    with pytest.raises(SystemExit) as e:
        runpy.run_module("dicomviewer", run_name="__main__")
    assert e.value.code == 0 and chamado == [1]


def test_objetos_gravados_antes_continuam_sendo_nossos():
    from ipe.imaging import overlays as O
    import inspect
    assert "FABRICANTES_NOSSOS" in inspect.getsource(O)
    for nome in ("DicomViewer", "Ipe", "Ipê"):
        assert nome in ipe.FABRICANTES_NOSSOS
    assert "(DicomViewer)" in ipe.MARCAS_NOSSAS and "(Ipe)" in ipe.MARCAS_NOSSAS


def test_marca_do_implante_nao_mudou():
    # entra na geração dos UIDs: mudar duplicaria séries já corrigidas
    from ipe.imaging import mammo
    assert mammo.MARCA_SEM_IMPLANTE == "DicomViewer: implante corrigido"


def test_campos_dicom_sem_acento():
    """O nome com acento não vai para campos DICOM gravados sem conjunto de caracteres."""
    from ipe.exporter import sr
    import inspect
    fonte = inspect.getsource(sr)
    assert 'Manufacturer = "Ipe"' in fonte and "Ipê" not in fonte


def test_ae_title_de_fabrica_nao_mudou():
    # os PACS já cadastrados conhecem este computador por esse AE
    from ipe.core.config import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS["dicom"]["ae_title"] == "DICOMVIEWER"
