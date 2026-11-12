"""Do diagnóstico do macOS (0.100.29): que decodificador **derruba o processo** com um arquivo fora do comum?

No Mac o Ipê fechou ao abrir um exame com uma exceção de C++ que ninguém pegou, vinda de uma linha de pré-carga
(o relatório de queda não diz de qual biblioteca). Este roteiro monta imagens sintéticas em cada sintaxe comprimida,
estraga cada uma de centenas de maneiras (corte, bytes trocados, cabeçalho DICOM que não combina com o quadro) e
decodifica com cada decodificador num processo à parte: erro de Python é o esperado; **processo morto** é o defeito.

    python tools/diag_fuzz.py [quantas mutações por par] [pasta de saída]

Não usa nada do Ipê nem dado de paciente.
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.encaps import encapsulate, generate_frames
from pydicom.uid import (
    JPEG2000,
    ExplicitVRLittleEndian,
    JPEG2000Lossless,
    JPEGBaseline8Bit,
    JPEGExtended12Bit,
    JPEGLossless,
    JPEGLosslessSV1,
    JPEGLSLossless,
    JPEGLSNearLossless,
    RLELossless,
    generate_uid,
)

PELO_PYDICOM = {"RLE": RLELossless, "JPEGLS": JPEGLSLossless, "J2K": JPEG2000Lossless}
PELO_GDCM = {"JPEGSV1": ("JPEGLosslessProcess14_1", JPEGLosslessSV1), "JPEG14": ("JPEGLosslessProcess14", JPEGLossless),
             "JPEGBASE": ("JPEGBaselineProcess1", JPEGBaseline8Bit),
             "JPEGEXT": ("JPEGExtendedProcess2_4", JPEGExtended12Bit),
             "J2KLOSSY": ("JPEG2000", JPEG2000), "JPEGLSNEAR": ("JPEGLSNearLossless", JPEGLSNearLossless)}


def _base(tipo: str, pasta: Path) -> Path:
    """Uma imagem sem compressão: 'ct' (16 bits com sinal), 'mg' (12 bits em 16), 'us' (8 bits), 'cor' (RGB)."""
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:192, 0:160]
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = FileDataset(str(pasta / f"{tipo}.dcm"), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID, ds.SeriesInstanceUID = generate_uid(), generate_uid()
    ds.PatientName, ds.PatientID, ds.Modality = "EXEMPLO^Fuzz", "FUZZ", "OT"
    ds.Rows, ds.Columns, ds.SamplesPerPixel, ds.PhotometricInterpretation = 192, 160, 1, "MONOCHROME2"
    liso = 400 * np.sin(xx / 17.0) * np.cos(yy / 23.0) + rng.normal(0, 12, xx.shape)
    if tipo == "ct":
        px = (liso - 300).astype(np.int16)
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 1
    elif tipo == "mg":
        px = np.clip(liso + 2000, 0, 4095).astype(np.uint16)
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    elif tipo == "us":
        px = np.clip(liso / 4 + 120, 0, 255).astype(np.uint8)
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    else:
        g = np.clip(liso / 4 + 120, 0, 255).astype(np.uint8)
        px = np.stack([g, g[::-1], g[:, ::-1]], axis=-1)
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = px.tobytes()
    ds.save_as(ds.filename)
    return Path(ds.filename)


def _pelo_gdcm(origem: Path, destino: Path, sintaxe: str) -> bool:
    import gdcm
    r = gdcm.ImageReader()
    r.SetFileName(str(origem))
    if not r.Read():
        return False
    ch = gdcm.ImageChangeTransferSyntax()
    ch.SetTransferSyntax(gdcm.TransferSyntax(getattr(gdcm.TransferSyntax, sintaxe)))
    ch.SetInput(r.GetImage())
    if not ch.Change():
        return False
    w = gdcm.ImageWriter()
    w.SetFileName(str(destino))
    w.SetFile(r.GetFile())
    w.SetImage(ch.GetOutput())
    return bool(w.Write())


def montar(pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for tipo in ("ct", "mg", "us", "cor"):
        base = _base(tipo, pasta)
        for nome, ts in PELO_PYDICOM.items():
            try:
                ds = pydicom.dcmread(base)
                ds.compress(ts)
                alvo = pasta / f"{tipo}_{nome}.dcm"
                ds.save_as(alvo)
                feitos.append(alvo)
            except Exception as e:  # noqa: BLE001
                print(f"  (sem {tipo}/{nome}: {str(e)[:70]})")
        for nome, (sint, _ts) in PELO_GDCM.items():
            alvo = pasta / f"{tipo}_{nome}.dcm"
            try:
                if _pelo_gdcm(base, alvo, sint):
                    pydicom.dcmread(alvo)
                    feitos.append(alvo)
                else:
                    print(f"  (sem {tipo}/{nome})")
            except Exception as e:  # noqa: BLE001
                print(f"  (sem {tipo}/{nome}: {str(e)[:70]})")
    return feitos


# ---------------------------------------------------------------------------------------------------------------

def mutar(ds, k: int) -> str:
    """Estraga o conjunto de dados de um jeito que depende só de k (dá para repetir). Devolve o nome do estrago."""
    rng = random.Random(k)
    quadro = bytearray(next(generate_frames(ds.PixelData, number_of_frames=1)))
    n = len(quadro)
    tipo = k % 12
    nome = ""
    if k == 0:
        return "intacto"
    if tipo == 0:
        corte = rng.randrange(1, n)
        quadro = quadro[:corte]
        nome = f"corte em {corte}/{n}"
    elif tipo == 1:
        for _ in range(rng.randrange(1, 4)):                        # bytes trocados no cabeçalho do quadro
            quadro[rng.randrange(0, min(n, 120))] = rng.randrange(256)
        nome = "cabeçalho do quadro trocado"
    elif tipo == 2:
        for _ in range(rng.randrange(1, 12)):
            quadro[rng.randrange(0, n)] = rng.randrange(256)
        nome = "bytes trocados"
    elif tipo == 3:
        a = rng.randrange(0, n)
        b = min(n, a + rng.randrange(1, 400))
        quadro[a:b] = bytes(b - a)
        nome = f"zeros {a}..{b}"
    elif tipo == 4:
        ds.Rows = rng.choice([1, ds.Rows // 2, ds.Rows * 2, ds.Rows + 1, 65535])
        nome = f"Rows={ds.Rows}"
    elif tipo == 5:
        ds.Columns = rng.choice([1, ds.Columns // 2, ds.Columns * 2, ds.Columns + 1, 65535])
        nome = f"Columns={ds.Columns}"
    elif tipo == 6:
        ba, bs = rng.choice([(8, 8), (16, 8), (16, 10), (16, 12), (16, 16), (32, 32), (16, 15), (8, 7)])
        ds.BitsAllocated, ds.BitsStored, ds.HighBit = ba, bs, bs - 1
        nome = f"bits {ba}/{bs}"
    elif tipo == 7:
        ds.PixelRepresentation = 1 - int(ds.PixelRepresentation)
        ds.PhotometricInterpretation = rng.choice(["MONOCHROME1", "MONOCHROME2", "RGB", "YBR_FULL", "YBR_FULL_422",
                                                   "PALETTE COLOR", "YBR_RCT", "YBR_ICT"])
        nome = f"sinal trocado, {ds.PhotometricInterpretation}"
    elif tipo == 8:
        ds.SamplesPerPixel = 3 if int(ds.SamplesPerPixel) == 1 else 1
        if ds.SamplesPerPixel == 3:
            ds.PlanarConfiguration = rng.randrange(2)
        nome = f"amostras={ds.SamplesPerPixel}"
    elif tipo == 9:
        quadro = quadro[: rng.randrange(0, 8)]
        nome = f"quadro de {len(quadro)} bytes"
    elif tipo == 10:
        a = rng.randrange(0, n)
        quadro[a:a] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 64)))
        nome = "bytes a mais no meio"
    else:
        a = rng.randrange(2, n)
        quadro = quadro[:a] + b"\xff\xd9" + quadro[a:]
        nome = "fim de imagem no meio"
    ds.PixelData = encapsulate([bytes(quadro)])
    return nome


def filho(arquivo: str, plugin: str, inicio: int, fim: int, marca: str) -> int:
    """Roda as mutações inicio..fim-1; grava em `marca` a que está em curso (para o pai saber qual matou)."""
    from pydicom.pixels import get_decoder
    erros = 0
    for k in range(inicio, fim):
        ds = pydicom.dcmread(arquivo)
        try:
            nome = mutar(ds, k)
        except Exception:  # noqa: BLE001
            continue
        Path(marca).write_text(json.dumps({"k": k, "estrago": nome}), encoding="utf-8")
        try:
            get_decoder(ds.file_meta.TransferSyntaxUID).as_array(ds, decoding_plugin=plugin)
        except Exception:  # noqa: BLE001 - é o esperado
            erros += 1
    Path(marca).write_text(json.dumps({"k": fim, "erros": erros, "fim": True}), encoding="utf-8")
    return 0


def pai(n: int, saida: Path) -> int:
    from pydicom.pixels import get_decoder
    arquivos = montar(saida / "imagens")
    print(f"{len(arquivos)} imagens de partida; {n} mutações por par (imagem, decodificador)")
    mortes = []
    marca = saida / "marca.json"
    for arq in arquivos:
        ts = pydicom.dcmread(arq, stop_before_pixels=True).file_meta.TransferSyntaxUID
        for plugin in get_decoder(ts).available_plugins:
            k, mortes_do_par = 0, 0
            while k < n and mortes_do_par < 8:
                marca.unlink(missing_ok=True)
                try:
                    r = subprocess.run([sys.executable, __file__, "--filho", str(arq), plugin, str(k), str(n),
                                        str(marca)], capture_output=True, text=True, timeout=600)
                    rc, err = r.returncode, (r.stderr or "")[-600:]
                except subprocess.TimeoutExpired:
                    rc, err = "tempo esgotado", ""
                try:
                    m = json.loads(marca.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    m = {"k": k, "estrago": "?"}
                if m.get("fim"):
                    break
                mortes_do_par += 1
                linha = [x for x in err.strip().splitlines() if "terminat" in x or "libc++" in x or "Assert" in x]
                mortes.append({"imagem": arq.name, "decodificador": plugin, "k": m["k"], "estrago": m.get("estrago"),
                               "saida": rc, "mensagem": (linha or err.strip().splitlines()[-1:] or [""])[0][:300]})
                print(f"  MORREU: {arq.name} · {plugin} · k={m['k']} ({m.get('estrago')}) · saída {rc} · "
                      f"{mortes[-1]['mensagem']}", flush=True)
                k = int(m["k"]) + 1
            print(f"{arq.name:22s} {plugin:10s} {'ok' if not mortes_do_par else f'{mortes_do_par} morte(s)'}",
                  flush=True)
    (saida / "fuzz.json").write_text(json.dumps(mortes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nFUZZ: {len(mortes)} morte(s) de processo")
    por = {}
    for m in mortes:
        por[m["decodificador"]] = por.get(m["decodificador"], 0) + 1
    print("por decodificador:", por)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--filho":
        sys.exit(filho(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]))
    sys.exit(pai(int(sys.argv[1]) if len(sys.argv) > 1 else 240,
                 Path(sys.argv[2] if len(sys.argv) > 2 else "diag/fuzz")))
