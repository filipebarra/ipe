"""0.100.29: o GDCM não decodifica mais nada dentro do programa.

No Mac o programa fechava sozinho ao abrir um exame: uma exceção de C++ sem dono, numa linha de pré-carga.
`tools/diag_fuzz.py` mostrou de onde ela vem: o GDCM (que o pydicom tentava primeiro) encerra o processo quando
o cabeçalho DICOM não combina com o quadro comprimido. Os outros decodificadores devolvem erro de Python.
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _rodar(codigo: str) -> subprocess.CompletedProcess:
    amb = dict(os.environ, PYTHONPATH=str(RAIZ / "src") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=300, cwd=RAIZ,
                          env=amb)


def test_gdcm_fora_de_todos_os_decodificadores():
    # nas duas ordens: o Ipê importado antes do pydicom (o programa) e depois (um roteiro, um teste)
    for primeiro in ("import ipe, pydicom", "import pydicom, ipe"):
        r = _rodar(primeiro + """
import sys
from pydicom.pixels.decoders.base import _PIXEL_DATA_DECODERS
from pydicom.pixels.encoders.base import _PIXEL_DATA_ENCODERS
for tabela in (_PIXEL_DATA_DECODERS, _PIXEL_DATA_ENCODERS):
    for uid, item in tabela.items():
        assert "gdcm" not in item[0].available_plugins, uid
try:
    import gdcm
except ImportError:
    print("SEM_GDCM")
""")
        assert r.returncode == 0 and "SEM_GDCM" in r.stdout, r.stderr[-800:]


def test_toda_sintaxe_comprimida_continua_com_decodificador():
    r = _rodar("""
import ipe
from pydicom.pixels import get_decoder
from pydicom import uid
for n in ("JPEGBaseline8Bit", "JPEGExtended12Bit", "JPEGLossless", "JPEGLosslessSV1", "JPEGLSLossless",
          "JPEGLSNearLossless", "JPEG2000Lossless", "JPEG2000", "RLELossless"):
    assert get_decoder(getattr(uid, n)).available_plugins, n
from ipe.imaging import series as SE
assert SE.decodificador_preferido(str(uid.JPEG2000Lossless)) == "pylibjpeg"
assert SE.decodificador_preferido(str(uid.JPEGLSLossless)) == "pyjpegls"
print("OK")
""")
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr[-800:]


def test_cabecalho_que_nao_combina_da_erro_e_nao_derruba(tmp_path):
    """Os estragos que matavam o processo com o GDCM (linhas, colunas, amostras e fotometria trocadas), pelo
    caminho do visualizador (`read_frame`). Num processo à parte: se cair, o teste vê."""
    r = _rodar(f"""
import sys
sys.path.insert(0, r"{RAIZ / 'tools'}")
from pathlib import Path
import pydicom
import diag_fuzz as F
from ipe.imaging.series import Frame, read_frame
pasta = Path(r"{tmp_path}")
lidos = erros = 0
for tipo in ("ct", "cor"):
    base = F._base(tipo, pasta)
    for nome, ts in F.PELO_PYDICOM.items():
        ds = pydicom.dcmread(base)
        try:
            ds.compress(ts)
        except Exception:
            continue
        inteiro = pasta / f"{{tipo}}_{{nome}}.dcm"
        ds.save_as(inteiro)
        read_frame(Frame(str(inteiro), 0, "1", 1))
        for k in list(range(1, 49)) + [61]:
            x = pydicom.dcmread(inteiro)
            F.mutar(x, k)
            alvo = pasta / "m.dcm"
            x.save_as(alvo)
            try:
                read_frame(Frame(str(alvo), 0, "1", 1))
                lidos += 1
            except Exception:
                erros += 1
print("VIVO", lidos, erros)
""")
    assert r.returncode == 0 and "VIVO" in r.stdout, (r.returncode, r.stderr[-1200:])
    _lidos, erros = (int(x) for x in r.stdout.split("VIVO")[1].split()[:2])
    assert erros > 20                                    # os estragos chegam mesmo ao decodificador
