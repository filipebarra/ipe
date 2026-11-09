# Ipê

**DICOM viewer for research and teaching**, written in Python (PySide6), for Windows and Linux. It
started as a breast-imaging reading station and grew to cover CT, MR, PET/CT, nuclear medicine,
ultrasound and radiography, with DICOM networking, films, printing and reporting.

> **Not intended for diagnostic use.** Ipê is not a medical device registered with ANVISA or any
> other agency. Do not use its images, measurements or results to report studies, decide care or
> treat patients.

*Other languages: [Português](README.pt-BR.md) · [Español](README.es.md) · Release history:
[CHANGELOG.en.md](CHANGELOG.en.md)*

The program opens in **English** by default. The installer asks for the language (English,
Portuguese or Spanish), and it can be changed later in Settings ▸ System ▸ Language.

## Why Ipê?

In Brasília, in the middle of the dry season, the ipê trees bloom and the landscape changes. And
there is a coincidence: *ipê* is in Fil**ipe**. Ipê was created by a breast radiologist who, like many
colleagues, moved to macOS because of OsiriX and Horos, and always wanted a complete program for
Windows and Linux. It is written with the help of Claude (Anthropic), working as a senior programmer
on the author's requests, and it exists thanks to open-source DICOM, computing and AI libraries.
[Read the full story](HISTORIA.en.md) · [Credits and licenses](CREDITOS.md)

---

## Features

### Study database
- Local database (SQLite): patient → study → series → image, with thumbnails and search by name, ID,
  accession or description (several terms with `|`), modality and date range.
- Import from folders, CD/DVD, ZIP and loose files, including drag and drop onto the window; in the
  background, without duplicates. Copy into storage or just reference the files. RAR, 7z and other
  archives too.
- Several study locations (external drive, network folder), comments, case lists and smart lists,
  protected studies, hiding and deleting series.
- Marks for studies that already have AI results (✦) or an AI running (⚙).
- Anonymize copies of studies; fix tags by writing a copy (the original is never changed).
- Lossless compression, checked pixel by pixel, and an archive report.
- PDFs and images attached to the study; study status; saved analysis state (reopen where you left).
- Worklist with priority, subspecialty and deadline; productivity panel; patient recall and
  mammography filters.

### Viewer
- Many viewport layouts, several monitors treated as **one** workstation, layout memory per monitor
  and hanging protocols.
- Window/level, zoom, pan, cine, invert, rotate, flip, magnifier, sharpening and smoothing filters,
  editable color scales.
- Automatic (same point in the patient) or manual synchronization, per modality; 3D cursor and
  reference lines.
- On-screen annotations in four levels (full, partial 1, partial 2, none), configurable.
- Ctrl+C copies the viewport as shown, in high resolution.
- Prior studies in the thumbnail strip; click an empty viewport to choose the series.
- Mosaic inside a viewport, typed zoom, key images and annotations saved as DICOM.
- A toolbar that adapts to the study: applications (dynamic, 3D, NM…) appear only when they suit the
  open study; the Applications button lists all of them, and each can be always, never or automatic.
- Settings menu with a submenu per topic and one window per item.

### Reconstructions and 3D
- Orthogonal, oblique and curved MPR; MIP/MinIP/average slabs; save a reconstruction as a series.
- Volume rendering, surface, cropping and sculpting; PET/CT fusion.
- Export 3D meshes as STL, OBJ, PLY, GLB and 3MF.
- 4D cardiac and digital subtraction (DSA).
- Rigid registration between studies (with a visual check) and motion correction in dynamic studies.
- Structures in 3D: edit masks and save them as SEG or RTSTRUCT.

### Measurements
- Ruler, polyline, angle, Cobb, ROIs (ellipse, rectangle, freehand) with mean and SD, text, arrow,
  curve; manual calibration per image or series.
- Ultrasound calibrated by the file's region, image by image.
- Extended ROI statistics, cloned and mirrored ROIs, doubling time; draft measurements.
- Panel with all measurements of the study; export to a spreadsheet and save as DICOM SR.
- 3D region-growing segmentation, with volume and three perpendicular axes.
- Guided measurements (Indices): MRPI and MRPI 2.0, Evans index and callosal angle, with checks of
  the plane and slice thickness.
- Automatic skull indices (SynthSeg): Evans, third ventricle, callosal angle and hippocampal
  volumes, on MR of any sequence or CT.
- Cervical lymph node levels on CT (map of levels I to VII in any plane; a segmented lesion gets its
  level).
- Nasopharynx cephalometry on CT, automatic (TotalSegmentator) or manual: minimum airway area
  perpendicular to the axis, soft palate, posterior airway space, hyoid and tongue, in report format.
- Body: composition at L3 (with weight and height) and liver attenuation; liver fat and iron on MR
  (1.5 T and 3 T); biometry and a steatosis result; diffusion (ADC) on any MR.
- Chest and vessels: emphysema per lobe, vertebral fractures (Genant), coronary calcium score
  (Agatston, CAC-DRS) and aortic diameters per segment, measured perpendicular to the centreline.

### Breast
- Mammography and tomosynthesis: step-by-step protocol, distribution across monitors, breast
  framing, quadrants, correct view from the device label, synthesized 2D, implant, tomosynthesis
  depth indicator.
- Breast density by three methods, with the mask shown.
- Dynamic MR: MSI, PEI, SER maps and a 6-color kinetic map (CADstream style), in any plane;
  configurable layouts; lesion measurement with angiovolume and kinetic patterns; lesion distance to
  skin, nipple and pectoralis.
- Fusion by dragging one series onto another, colour maps and findings recorded by markers.

### Nuclear medicine
- Multi-frame NM reading (detectors, phases, energy windows), ANT/POST and geometric mean with a
  shared window.
- ROIs and time-activity curves, renogram, gastric emptying, HIDA, salivary glands, DMSA,
  parathyroid, thyroid uptake and transit, with decay correction. The program returns numbers; it
  does not interpret them.
- PET: SUV by body weight, lean mass and glucose correction; PET reading layout; tumour burden
  (FDG, PSMA, DOTA: MTV, TLG, lesion count) and follow-up across dates.

### Oncology and AI
- Lesions tracked across studies; CAD/AI objects (SEG, GSPS, SR, RTSTRUCT) that can be switched on
  and off.
- Abdominal organ segmentation with TotalSegmentator (optional, installed separately) and
  identification of vertebrae and discs.
- AI tasks window: progress of every AI (including the ones that run automatically when a study
  arrives), with cancel.
- Reviewable AI findings (confirm, correct or discard) that can go into the report text; complete lung
  nodule workup; liver lesions by Couinaud segment.
- Optional extra models: SynthSeg, MedSAM2 (interactive segmentation), autoPET and BraTS.

### DICOM networking
- DICOM node (C-ECHO, C-FIND, C-MOVE, C-GET, C-STORE) and DICOMweb client (QIDO, WADO, STOW).
- PACS search, download by series, open while downloading, prefetch of priors.
- Automation: routing, scheduled queries, rules by modality; DICOM management (check that studies
  from the modalities reached the PACS and send what is missing).
- External calls by `ipe://` link, command line or local HTTP API, including opening only the
  viewer.

### Web viewer (central server)
The central server also serves a viewer in the browser, with nothing to install on the reading
computer: open `http(s)://<server>:8043/web` (the address is shown in the server window) and log in
with the Ipê user. It is meant for the internal network for now.
- Weasis-style screen: one icon toolbar where each mouse button gets its own function, as in Ipê
  (click the icon with the button that should do it; a mark under the icon shows which), a right-click
  menu on the image (click and release; click and hold does the button's function), collapsible panels
  with series and prior studies on the left and Image, Measurements, DICOM and PET tabs on the right.
- Study list, thumbnail strip (click or drag a series onto a viewport), layouts from 1×1 to 4×4, window
  presets, cine.
- MPR, oblique, thick slabs and MIP, with one-click plane change, as in Ipê.
- Measurements with Ipê's numbers (ruler, angle, Cobb, ROIs, pixel, arrow, calibration), saved in
  the server database: what is measured in the browser shows up in Ipê and vice versa. Ultrasound
  calibrated by the device's region.
- PET/CT: fusion, PET and PET MIP with the axial views moving together, SUV by Ipê's calculation,
  Ipê's colour tables, maximum SUV near the cursor, and the study's SEGs (tumour burden, organs) as
  masks.
- Fast loading: images go over the network as lossless HTJ2K (a checked transport copy; the
  archive is not changed), load progressively and are kept in the browser cache; each thumbnail
  shows the percentage already available, and the **Loading** button shows network speed and
  decoding time.
- Coming next: mammography hanging protocol across two monitors, breast dynamics and reporting.

### Films, printing and reporting
- Film composer; printing to an ordinary printer, PDF and DICOM printer.
- The program as a DICOM printer: receives films from modalities, identifies the patient and
  forwards them by rules.
- Reports with templates (CT, MG, MR, PET) and BI-RADS, as PDF, DICOM PDF and SR.
- Export as DICOM, JPG/PNG and a complete HTML viewer, with anonymization.

### Users and languages
- One user or several, with profiles and permissions; optional central server.
- Profiles by group and computer, settings exported and imported, updates through the server or
  straight from GitHub in one click.
- HTTPS on the internal network with Ipê's own certificate; OAuth2/OIDC on DICOMweb nodes; stored
  passwords encrypted.
- English, Portuguese and Spanish, with a translation editor for other languages.

---

## Installation

### Windows — installer
The `Ipe-<version>-installer.exe` installer (and the portable `.zip` package) installs into the
user profile, without asking for administrator rights. Its first screen asks for the language, with
English selected; then it asks for the program folder and the database folder. To build it from source, see [installer/LEIAME.md](installer/LEIAME.md).

### Windows — from source
1. Install **Python 3.12** from <https://www.python.org/downloads/>, ticking **"Add python.exe to
   PATH"**.
2. Double-click `instalar.bat` (first time only; it asks for the language and downloads about
   300 MB of libraries).
3. Double-click `executar.bat`.

### Linux
```bash
./instalar.sh
./executar.sh
```

To try it without real studies: **Help ▸ Generate test studies (phantoms)**.

Organ segmentation (TotalSegmentator) is optional and installed separately, with
`instalar_segmentacao.bat` / `instalar_segmentacao.sh`.

---

## Command line

On Windows, use `.venv\Scripts\ipe.exe` (or `ipe-cli.exe` in the installed program). On Linux,
`.venv/bin/ipe`.

```
ipe                                    opens the interface
ipe open --accession 123456            opens the study by accession
ipe open --study-uid 1.2.3...          opens by StudyInstanceUID
ipe open --patient-id ABC              opens the patient's most recent study
ipe open --accession 123 --node PACS   if not in the database, queries the node, downloads and opens
ipe open --accession 123 --janela viewer   opens only the viewer
ipe open C:\folder\study               imports the folder and opens the studies
ipe "ipe://open?accession=123"         the same, by link
ipe import D:\ --reference             imports without copying (reference only)
ipe retrieve --accession 123           only downloads from the PACS
ipe sample C:\temp\phantoms            generates synthetic test studies
ipe info                               shows where the database, files and settings are
ipe set-language en                    program language: en, pt-BR or es
ipe register-url                       registers the ipe:// and dicomviewer:// links
ipe server                             headless central server
```

## Where the data lives

`ipe info` shows the paths. On Windows they are in `%LOCALAPPDATA%\DicomViewer` (the program's old
name, kept for those who upgrade): the `dicomviewer.sqlite` database, the `Storage\` folder with the
DICOM files, `Impressoes\`, `settings.json` and logs. The `IPE_HOME` environment variable (or the old
`DICOMVIEWER_HOME`) changes the folder — useful to keep one database per research project.

## Coming from DicomViewer

Up to version 0.99.10 the program was called **DicomViewer**. These still work: the data folder, the
factory AE title `DICOMVIEWER`, `dicomviewer://` links, `python -m dicomviewer` and the old
shortcuts. The new installer upgrades the old one in place.

## Development

- Code in `src/ipe/` (`core`, `db`, `importer`, `imaging`, `network`, `printing`, `reporting`, `ui`,
  `ai`, `automation`, `central`, `exporter`, `caselists`); tests in `tests/`; translation and guide
  tools in `tools/`. The source strings are in Portuguese (they are the keys of the translation
  files in `src/ipe/locale/`).
- Tests: `python -m pytest` (or `testar.bat`). The tests generate synthetic studies.
- **Never commit real studies, screenshots with patient data or databases to the repository.**
- User guide as PDF: `docs/Ipe-guia-do-usuario.pdf` (F1 in the program; in Portuguese).

## License

[GPL-3.0-or-later](LICENSE). You may use, study, modify and redistribute it; anyone who
redistributes a modified version must publish its source under the same license. © Filipe Ramos
Barra.

The libraries and models Ipê uses, with licenses and links, are listed in
[CREDITOS.md](CREDITOS.md) (and in the program, under Help ▸ About Ipê ▸ Credits and licenses).
