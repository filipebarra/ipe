"""0.100.33: "Segmentar pela caixa (MedSAM2)" parava com *Cannot find primary config
'configs/sam2.1_hiera_t512.yaml'* — o pacote do MedSAM2 instalado pelo pip vem sem a pasta sam2/configs.
O Ipê traz a cópia do arquivo e a põe no lugar quando falta."""
from pathlib import Path

import pytest

from ipe.ai import totalseg_worker as W

RAIZ = Path(__file__).resolve().parents[1]
COPIA = RAIZ / "src" / "ipe" / "ai" / "medsam2_sam2.1_hiera_t512.yaml"


def test_a_copia_do_ipe_e_a_configuracao_do_modelo():
    txt = COPIA.read_text(encoding="utf-8")
    # a diretiva tem que ser a PRIMEIRA linha: com um comentário antes, o hydra põe tudo sob "configs" e o modelo
    # fica sem image_encoder (visto ao rodar o MedSAM2 de verdade, com pesos aleatórios)
    assert txt.splitlines()[0] == "# @package _global_" and "sam2.modeling.sam2_base.SAM2Base" in txt
    assert "image_size: 512" in txt                        # o trabalhador redimensiona os cortes para 512
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(txt)
    assert d["model"]["image_encoder"]["trunk"]["_target_"].endswith("hieradet.Hiera")


def test_poe_no_lugar_quando_falta_e_nao_troca_o_que_existe(tmp_path):
    sam2 = tmp_path / "site-packages" / "sam2"
    sam2.mkdir(parents=True)                               # como o pip deixa: sem a pasta configs
    assert W._config_do_medsam2(sam2) == "configs/sam2.1_hiera_t512.yaml"
    alvo = sam2 / "configs" / "sam2.1_hiera_t512.yaml"
    assert alvo.read_bytes() == COPIA.read_bytes()
    alvo.write_text("do pacote")
    W._config_do_medsam2(sam2)
    assert alvo.read_text() == "do pacote"                 # se o pacote trouxe o arquivo, vale o dele


def test_sem_a_copia_o_erro_diz_o_que_falta(tmp_path):
    with pytest.raises(RuntimeError, match="configuração do MedSAM2"):
        W._config_do_medsam2(tmp_path / "sam2", origem=tmp_path / "nao_existe.yaml")


def test_vai_no_pacote_e_o_instalador_confere_a_configuracao():
    assert "medsam2_sam2.1_hiera_t512.yaml" in (RAIZ / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"ai/*.yaml"' in (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    inst = (RAIZ / "src" / "ipe" / "ai" / "instalar_modelos_extras.py").read_text(encoding="utf-8")
    assert "compose(config_name='configs/sam2.1_hiera_t512.yaml')" in inst and "shutil.copyfile(origem, alvo)" in inst
    assert "c.model.image_encoder" in inst
    fonte = (RAIZ / "src" / "ipe" / "ai" / "totalseg_worker.py").read_text(encoding="utf-8")
    assert "build_sam2_video_predictor_npz(_config_do_medsam2()" in fonte
