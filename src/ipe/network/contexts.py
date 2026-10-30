"""Classes SOP de armazenamento e sintaxes de transferência negociadas na rede."""

from __future__ import annotations

from pydicom.uid import (
    DeflatedExplicitVRLittleEndian, ExplicitVRBigEndian, ExplicitVRLittleEndian,
    ImplicitVRLittleEndian, JPEG2000, JPEG2000Lossless, JPEGBaseline8Bit, JPEGExtended12Bit,
    JPEGLossless, JPEGLosslessSV1, JPEGLSLossless, JPEGLSNearLossless, RLELossless,
)

UNCOMPRESSED = [ExplicitVRLittleEndian, ImplicitVRLittleEndian]
ALL_TS = [ExplicitVRLittleEndian, ImplicitVRLittleEndian, JPEGLosslessSV1, JPEGLossless,
          JPEGBaseline8Bit, JPEGExtended12Bit, JPEGLSLossless, JPEGLSNearLossless, JPEG2000Lossless,
          JPEG2000, RLELossless, DeflatedExplicitVRLittleEndian, ExplicitVRBigEndian]

_P = "1.2.840.10008.5.1.4.1.1."
# classes mais comuns em radiologia (limite do protocolo: 128 contextos por associação)
STORAGE_CLASSES = [_P + s for s in (
    "2", "2.1", "2.2", "4", "4.1", "4.2", "4.3", "1", "1.1", "1.1.1", "1.2", "1.2.1",
    "13.1.3", "13.1.4", "13.1.5", "6.1", "6.2", "3.1", "7", "7.1", "7.2", "7.3", "7.4",
    "20", "128", "128.1", "130", "12.1", "12.1.1", "12.2", "13.1.1", "66", "66.1", "66.3",
    "66.4", "66.5", "30", "88.11", "88.22", "88.33", "88.34", "88.50", "88.59", "88.67",
    "104.1", "11.1", "11.2", "481.1", "481.2", "481.3", "481.5", "77.1.1", "77.1.1.1",
    "77.1.2", "77.1.4", "77.1.4.1", "77.1.5.1", "14.1",
)]
