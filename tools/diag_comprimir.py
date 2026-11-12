"""Do diagnóstico do macOS (0.100.27): copia alguns exames sintéticos em sintaxes comprimidas (RLE, JPEG-LS,
JPEG 2000), cada uma como um exame novo, para ver se os decodificadores nativos do pacote aguentam.

    python tools/diag_comprimir.py <pasta de origem> <pasta de destino> [quantos por sintaxe]
"""
import sys
from pathlib import Path

import pydicom
from pydicom.uid import JPEG2000Lossless, JPEGLSLossless, RLELossless, generate_uid

SINTAXES = {"RLE": RLELossless, "JPEGLS": JPEGLSLossless, "J2K": JPEG2000Lossless}


def main(origem: str, destino: str, quantos: int = 12) -> int:
    arquivos = []
    for p in sorted(Path(origem).rglob("*")):
        if not p.is_file():
            continue
        try:
            ds = pydicom.dcmread(p, stop_before_pixels=True, force=True)
        except Exception:  # noqa: BLE001
            continue
        if "PixelData" not in pydicom.dcmread(p, force=True) or int(ds.get("SamplesPerPixel", 1)) != 1:
            continue
        if str(ds.get("Modality", "")) in ("CT", "MR", "MG"):
            arquivos.append(p)
    feitos = {}
    for nome, uid in SINTAXES.items():
        mapa: dict[str, str] = {}
        n = 0
        for p in arquivos[:quantos]:
            ds = pydicom.dcmread(p, force=True)
            try:
                ds.compress(uid)
            except Exception as e:  # noqa: BLE001
                print(f"{nome}: não comprimiu {p.name}: {type(e).__name__}: {e}")
                break
            for chave in ("StudyInstanceUID", "SeriesInstanceUID"):
                velho = str(ds.get(chave))
                setattr(ds, chave, mapa.setdefault(velho, generate_uid()))
            ds.SOPInstanceUID = generate_uid()
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            ds.PatientName, ds.PatientID = f"COMPRIMIDO^{nome}", f"COMP-{nome}"
            ds.AccessionNumber = f"COMP{nome}"
            alvo = Path(destino) / nome
            alvo.mkdir(parents=True, exist_ok=True)
            ds.save_as(alvo / f"{n:04d}.dcm", enforce_file_format=True)
            n += 1
        feitos[nome] = n
    print("comprimidos:", feitos)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12))
