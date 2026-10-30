# Ipê

**DICOM viewer for research and teaching**, written in Python (PySide6), for Windows and Linux. It
started as a breast-imaging reading station and grew to cover CT, MR, PET/CT, nuclear medicine,
ultrasound and radiography, with DICOM networking, films, printing and reporting.

> **Not intended for diagnostic use.** Ipê is not a registered medical device. Do not use its
> images, measurements or results to report studies, decide care or treat patients.

*Other languages: [Português](README.md) · [Español](README.es.md) · Release history:
[CHANGELOG.en.md](CHANGELOG.en.md)*

## Why Ipê?

In Brasília, in the middle of the dry season, the ipê trees bloom and the landscape changes. And
there is a coincidence: *ipê* is in Fil**ipe**. Ipê was created by a breast radiologist who, like many
colleagues, moved to macOS because of OsiriX and Horos, and always wanted a complete program for
Windows and Linux. It is written with the help of Claude (Anthropic), working as a senior programmer
on the author's requests, and it exists thanks to open-source DICOM, computing and AI libraries.
[Read the full story](HISTORIA.en.md) · [Credits and licenses](CREDITOS.md)

---

## Features

- **Study database:** local SQLite database with thumbnails and search; import from folders, CD/DVD,
  ZIP or drag and drop; several storage locations; case lists; anonymized copies; tag correction
  that writes a copy; lossless compression with pixel-by-pixel verification.
- **Viewer:** multiple layouts, several monitors acting as one station, display protocols,
  window/level, zoom, cine, filters, editable color scales, automatic or manual synchronization,
  3D cursor and reference lines, four annotation levels, Ctrl+C copies the viewport in high
  resolution, prior studies in the thumbnail strip.
- **Reconstructions and 3D:** orthogonal, oblique and curved MPR, slabs, volume rendering, surface,
  cutting, PET/CT fusion, 3D mesh export (STL, OBJ, PLY, GLB, 3MF), 4D cardiac, DSA.
- **Measurements:** ruler, angle, Cobb, ROIs, calibrated ultrasound, measurement panel, DICOM SR,
  3D region-growing segmentation with volume and three perpendicular axes.
- **Breast:** mammography and tomosynthesis hanging by steps across monitors, breast framing,
  implant handling, breast density (three methods), dynamic breast MR with MSI/PEI/SER and a
  six-color kinetic map, lesion measurement and distances to skin, nipple and pectoral wall.
- **Nuclear medicine:** multi-frame NM, ANT/POST and geometric mean, ROIs and time-activity curves,
  renogram, gastric emptying, DISIDA, salivary, DMSA, parathyroid, thyroid uptake and transit.
- **Oncology and AI:** lesion follow-up, CAD/AI objects (SEG, GSPS, SR, RTSTRUCT), optional
  TotalSegmentator organ segmentation, vertebra and disc labeling.
- **DICOM network:** DICOM node (C-ECHO/FIND/MOVE/GET/STORE) and DICOMweb client, PACS search,
  per-series download, routing and automation, PACS completeness check, external calls via
  `ipe://` links, command line or a local HTTP API.
- **Films, printing and reports:** film composer, system and DICOM printers, the program as a DICOM
  printer, report templates with BI-RADS (PDF, DICOM PDF, SR), export to DICOM, JPG/PNG and a full
  HTML viewer.
- **Users and languages:** single or multi-user with permissions, optional central server;
  Portuguese, English and Spanish, with a translation editor for other languages.

## Installing

**Windows:** install **Python 3.12** (tick *"Add python.exe to PATH"*), double-click `instalar.bat`
once, then `executar.bat`. To build the Windows installer see [installer/LEIAME.md](installer/LEIAME.md).

**Linux:**
```bash
./instalar.sh
./executar.sh
```

To try it without real studies: **Help ▸ Generate test studies (phantoms)**.

## Command line

```
ipe                                    opens the interface
ipe open --accession 123456            opens the study by accession number
ipe open --study-uid 1.2.3...          opens it by StudyInstanceUID
ipe open --accession 123 --node PACS   if not in the database, queries the node, downloads and opens
ipe "ipe://open?accession=123"         same, through the link
ipe import D:\ --reference             imports without copying
ipe info                               shows where the database, files and settings live
ipe register-url                       registers ipe:// and dicomviewer:// links
```

## Where the data lives

`ipe info` shows the paths. On Windows: `%LOCALAPPDATA%\DicomViewer` (the program's former name,
kept for existing users). The `IPE_HOME` environment variable (or the older `DICOMVIEWER_HOME`)
points it elsewhere.

## Development

Code in `src/ipe/`, tests in `tests/` (`python -m pytest`; they generate synthetic studies).
**Never commit real studies, screenshots with patient data or databases.**

## License

[GPL-3.0-or-later](LICENSE). © Filipe Ramos Barra. Third-party libraries and models, with licenses and links: [CREDITOS.md](CREDITOS.md).
