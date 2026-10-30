"""0.99.8: configurar o servidor sem janela pela linha de comando."""
import json

from ipe.__main__ import main


def test_config_e_nos_pela_linha(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path))
    assert main(["config", "dicom.ae_title", "SRV"]) == 0
    assert main(["config", "dicom.http_allowed_ips", '["192.168.1.0/24"]']) == 0
    cfg = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
    assert cfg["dicom"]["ae_title"] == "SRV"
    assert cfg["dicom"]["http_allowed_ips"] == ["192.168.1.0/24"], "valor lido como JSON"
    assert main(["config"]) == 0
    assert "central.port                 8043" in capsys.readouterr().out
    assert main(["node", "add", "PACS", "PACSAE", "10.0.0.1", "104", "--move"]) == 0
    assert main(["node", "add", "PACS", "PACSAE", "10.0.0.2", "11112"]) == 0   # mesmo nome: atualiza
    assert main(["node", "add", "Web", "--web", "http://x/dicom-web"]) == 0
    assert main(["node", "add", "Ruim", "UM_AE_GRANDE_DEMAIS", "h", "1"]) == 2
    capsys.readouterr()
    assert main(["node", "list"]) == 0
    out = capsys.readouterr().out
    assert "PACSAE@10.0.0.2:11112" in out and out.count("PACS ") == 1 and "dicomweb" in out
    assert main(["node", "remove", "Web"]) == 0
    assert main(["node", "remove", "Web"]) == 1
