"""Do diagnóstico do macOS: copia alguns exames sintéticos em várias sintaxes comprimidas, cada uma como um exame
novo, e também uma versão **estragada** de cada (o quadro comprimido cortado ao meio) — é quando o decodificador
dá erro que o programa precisa aguentar (0.100.29: no Mac ele fechava).

    python tools/diag_comprimir.py <pasta de origem> <pasta de destino> [quantos por sintaxe]
"""
import sys
from pathlib import Path

import pydicom
from pydicom.encaps import encapsulate, generate_frames
from pydicom.uid import JPEG2000Lossless, JPEGLSLossless, RLELossless, generate_uid

PYDICOM = {"RLE": RLELossless, "JPEGLS": JPEGLSLossless, "J2K": JPEG2000Lossless}
#: pelo GDCM (o pydicom não grava estas): JPEG sem perda (a .70 dos mamógrafos e de muitos PACS), J2K com perda
GDCM = {"JPEGLOSSLESS": "JPEGLosslessProcess14_1", "JPEGLOSSLESS14": "JPEGLosslessProcess14",
        "J2KLOSSY": "JPEG2000", "JPEGLSNEAR": "JPEGLSNearLossless"}


def _identidade(ds, nome: str, mapa: dict) -> None:
    for chave in ("StudyInstanceUID", "SeriesInstanceUID"):
        velho = str(ds.get(chave))
        setattr(ds, chave, mapa.setdefault(velho, generate_uid()))
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.PatientName, ds.PatientID = f"COMPRIMIDO^{nome}", f"COMP-{nome}"
    ds.AccessionNumber = f"COMP{nome}"[:16]


def _pelo_gdcm(origem: Path, destino: Path, sintaxe: str) -> bool:
    import importlib
    gdcm = importlib.import_module("gdcm")     # só no diagnóstico: o programa não usa o GDCM (0.100.29)
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


def _estragar(ds) -> None:
    """Corta cada quadro comprimido a 55% (o encapsulamento continua válido: quem reclama é o decodificador)."""
    n = int(ds.get("NumberOfFrames", 1) or 1)
    quadros = [f[: max(64, int(len(f) * 0.55))] for f in generate_frames(ds.PixelData, number_of_frames=n)]
    ds.PixelData = encapsulate(quadros)


def main(origem: str, destino: str, quantos: int = 12) -> int:
    arquivos = []
    for p in sorted(Path(origem).rglob("*")):
        if not p.is_file() or "comprimidos" in p.parts:
            continue
        try:
            ds = pydicom.dcmread(p, force=True)
        except Exception:  # noqa: BLE001
            continue
        if "PixelData" not in ds or int(ds.get("SamplesPerPixel", 1)) != 1:
            continue
        if str(ds.get("Modality", "")) in ("CT", "MR", "MG"):
            arquivos.append(p)
    feitos = {}
    dest = Path(destino)
    tmp = dest / "_tmp.dcm"
    for nome in list(PYDICOM) + list(GDCM):
        mapa: dict[str, str] = {}
        mapa_x: dict[str, str] = {}
        n = 0
        for p in arquivos[:quantos]:
            try:
                if nome in PYDICOM:
                    ds = pydicom.dcmread(p, force=True)
                    ds.compress(PYDICOM[nome])
                else:
                    dest.mkdir(parents=True, exist_ok=True)
                    if not _pelo_gdcm(p, tmp, GDCM[nome]):
                        raise RuntimeError("o GDCM não converteu")
                    ds = pydicom.dcmread(tmp, force=True)
            except Exception as e:  # noqa: BLE001
                print(f"{nome}: não comprimiu {p.name}: {type(e).__name__}: {e}")
                break
            _identidade(ds, nome, mapa)
            alvo = dest / nome
            alvo.mkdir(parents=True, exist_ok=True)
            ds.save_as(alvo / f"{n:04d}.dcm", enforce_file_format=True)
            if n < 4:                                            # e a versão estragada, como outro exame
                try:
                    _estragar(ds)
                    _identidade(ds, nome + "X", mapa_x)
                    ruim = dest / (nome + "_estragado")
                    ruim.mkdir(parents=True, exist_ok=True)
                    ds.save_as(ruim / f"{n:04d}.dcm", enforce_file_format=True)
                except Exception as e:  # noqa: BLE001
                    print(f"{nome}: não estragou: {e}")
            n += 1
        feitos[nome] = n
    tmp.unlink(missing_ok=True)
    print("comprimidos:", feitos)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 12))
