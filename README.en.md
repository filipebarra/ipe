# Ipê

DICOM viewer for research and teaching, written in Python (PySide6), for Windows and Linux — with a
focus on breast imaging (mammography, tomosynthesis, dynamic MRI), MPR, measurements, DICOM
networking, films and printing.

> **Not intended for diagnostic use.** Ipê is not a registered medical device. Do not use its
> images, measurements or results to report studies, decide care or treat patients.

- **License:** [GPL-3.0-or-later](LICENSE).
- **Name:** up to version 0.99.10 the program was called *DicomViewer*. The data folder, the
  factory AE title `DICOMVIEWER` and `dicomviewer://` links keep working; the new link is `ipe://`.

*(Versions in other languages: [Português](README.md) · [Español](README.es.md). The Portuguese README
also carries the full change log of every version.)*

## What's new in 0.15.1

The blue line of text on the left of each frame was replaced by a **small mouse icon**. Hover it and a
balloon shows what each button does right now (left, right, middle, wheel, Ctrl+wheel, Shift+wheel); the
icon's left button lights up in amber whenever a tool other than window/level is active, and clicking the
icon opens the left-button tool list. Text painted directly over the image (Im 31/60, Thk 3.0 mm, W/L,
FOV), the film and the charts are now translated too, and the catalog grew to 2708 entries.

## What's new in 0.16 — several study locations

Like the *Sources* panel in OsiriX/Horos, the left column of the Database tab now has **Locations**. One
click switches location and the study list becomes that folder's. Each location carries the whole database
inside its folder (`dicomviewer.sqlite`, `Storage/`, a marker file), so an external drive opens on another
computer with everything: studies, case lists, comments, measurements and reports. Adding a location
**copies nothing** — files already in the folder are only indexed. Right-click a study to *Copy to
location*; the source files are never touched. Offline locations (drive unplugged, network down) are shown
in gray and come back when the drive does. PACS nodes appear in the same panel.

## What's new in 0.26 — comparing the study's images: DMSA, parathyroid, thyroid and transit

Four studies do not fit the curve window, because their arithmetic compares **separate images**:
DMSA (anterior × posterior), parathyroid (early × delayed), thyroid (thyroid × syringe) and
colonic transit (24 h × 48 h × 72 h). There is now a window for that — **NM ▸ Compare the study's
images…**

- **Each image is a row**, with its **role** and the **time read from the header**. Workstation
  screen captures are left out: they are the report sheet, not a measurement image.
- **Regions are drawn on each image** — the kidney does not fall on the same pixel in ANT and
  POST. **Copy** and **Copy mirrored** save the rework; mirrored is the right one for ANT/POST,
  because it keeps both regions the same area.
- **Decay correction between the images**, on by default. It is what makes a syringe measured at
  9:00 comparable with a thyroid measured at 11:00.

**The calculations**: DMSA relative function by the geometric mean √(ANT × POST); parathyroid dual
phase (decay-corrected, otherwise Tc-99m decay alone would look like 50% "retention" in 6 h);
thyroid uptake against the syringe standard; colonic transit geometric centre; and a free mode with
just the counts.

## What's new in 0.25 — one recipe per study: gastric, DISIDA, salivary glands and ratio

The curve window gained an **Exam** box. Picking the exam changes three things at once: the ready
region names, the calculation, and what the window asks for.

- **Renogram** (as in 0.24).
- **Gastric emptying** — % retention at 30 min, 1 h, 2 h and 4 h, plus T½. A time point the curve
  does not reach shows as **—**, never extrapolated.
- **Gallbladder (DISIDA)** — ejection fraction from the maximum before the stimulus and the minimum
  after it. The window asks when sincalide was given and marks it on the chart; without it, the
  program uses the whole curve's peak **and says so**.
- **Salivary glands** — relative uptake per gland (summing 100%) and excretion fraction after the
  stimulus.
- **Lesion / normal side ratio** — per-pixel mean of each region and the ratio between them.
- **Free** — the curve's general numbers only.

**The guideline reference values appear under the table**, as text next to what was measured. The
program does not classify: it never writes "delayed" or "obstructed".

**Condensed image**: each frame becomes a column and time becomes the horizontal axis — how reflux
and transit are read without stepping through the cine.

## What's new in 0.24.1 — freehand, automatic contour and double-click on the views

- **Freehand** is now an option in the "Shape" box: drag over the image and the trace becomes the
  region, closing on itself.
- **Automatic contour**: draw a rough region around the target, select it and click **Automatic
  contour**. The contour follows a threshold as a **% of that region's maximum** (40% by default)
  and takes **only what is connected to the hottest pixel** — two nearby kidneys do not merge into
  one region. It never escapes the box you drew, and changing the threshold recomputes inside the
  same box, so it can grow back.
- **Mirror R/L works with the automatic contour**: the mask is mirrored with the same area, which
  is what relative function requires. To make the other side follow its own kidney instead, select
  the mirrored region and click **Automatic contour** again.
- **Double-clicking a nuclear medicine series** opens **all its views side by side**, whatever they
  are called — ANT/POST, RAO/LPO, laterals, energy windows — with the same window and linked zoom.

## What's new in 0.24 — nuclear medicine phase 2: regions, curves and the renogram

The machinery seven studies share. Renogram, salivary glands, dacryoscintigraphy, radionuclide
cystography, gastro-oesophageal reflux, gastric emptying and the three-phase bone scan are all the
same thing: count a region's pixels in each frame, subtract background, put them on the right time
axis and apply a formula. Only the formula changes.

- **Its own analysis window** (**NM ▸ Time-activity curves by region…**): image with the regions on
  the left, chart and table on the right. It opens with **all frames added** — a single 2 s frame is
  too noisy to draw a kidney on — and the slider steps through frames when you want.
- **Mirror R/L**: draw one kidney and the other appears mirrored about the vertical axis, with the
  same background method — which is how both regions end up the same size, as relative function
  requires.
- **Three ways to subtract background**: a background ROI of its own, a **ring around the region**
  (with one pixel of clearance, so it does not measure the region's own spill) or a fixed fraction.
  The chosen method is recorded next to the result.
- **Counts per second**, on by default. With a 2 s flow phase and a 30 s dynamic phase, not dividing
  by duration produces a 15× step that does not exist in the patient.
- **Each point sits at the middle of its frame**, not at the start — enough to ruin a T½ otherwise.
- **Full renogram**: relative function by the integral method (1 to 2.5 min), time to peak, T½ after
  the peak and the 20 min/peak ratio. **A T½ that was not reached reads "not reached"**, never a
  large number.
- **Optional decay correction**; with no half-life in the file the program says so instead of
  correcting wrongly.
- **Export CSV** and **Send to the report** — numbers only, no interpretation, and nothing leaves on
  its own.

The program carries **no reference values** and never writes "obstructed": it returns the numbers
and what happened to the curve.

**Also in this version:** the workstation's report sheet (the screen capture handed to the patient
and the referring physician) is marked as a **key image automatically** on import, recognised by
what it is in the standard rather than by its description. **Nuclear medicine studies already in
the database are marked too**, by a background pass when the program starts — nothing needs
re-importing.

## What's new in 0.23.1 — nuclear medicine checked against real studies

Three things the DICOM standard says to record and the cameras do not. Found by opening 146 real
nuclear medicine series, and each one became a change:

- **The view (ANT, POST, LAT) is rarely in the header.** Only whole-body series carry the
  `ViewCodeSequence`; elsewhere the program could only show "Detector 1" and "Detector 2". It now
  reads the abbreviations from the **series description** — "ANT POST PERF", "LD LE PERF" — and
  accepts them only when their number matches the number of detectors. A view obtained that way is
  labelled **"ANT (from the description)"**, in a different color, with a warning in the status
  bar: swapping anterior for posterior flips right and left in the report, so the program never
  hides that it was inferred.
- **One series can mix a two-detector file with a one-detector file**, which used to split it into
  parallel views that did not match. The axes are now decided for the whole series.
- **`SeriesType` comes empty**, so the study type is derived from the vectors themselves, and SPECT
  projections now count as tomography even without a slice axis.

**On SUV in SPECT/CT: not possible, and now confirmed.** None of the 146 series carries the
quantitative scale (`Units` or Real World Value Mapping) — it is all raw counts. In PET, which does
carry `Units = BQML`, SUV keeps working.

## What's new in 0.23 — nuclear medicine: the study stops being a pile of frames

First stage of the nuclear medicine module. An NM file stores several images in a single cube, and what
says what each frame is are the **group 0054 vectors** in DICOM: detector, energy window, phase, slice,
projection, time. Without reading those vectors — which most generic viewers do not — a renogram or an
ANT/POST whole body shows up as a meaningless pile of frames.

- **The series opens as the parts it is made of.** In the left strip, right under the NM series, one
  line per view: `↳ ANT`, `↳ POST`, `↳ Phase 1 · 20 × 2 s`, `↳ ANT · Tc-99m`… Each can be dragged into
  a frame on its own. Works both when the camera writes everything into one file and when it writes one
  file per view.
- **NM button on the toolbar: "Anterior and posterior side by side"**. Opens ANT and POST in two frames
  **with the same window** — computed over both images together, so neither saturates — and with
  **window and zoom linked**. Comparing ANT with POST under different windows is a reading error, so the
  program does not let it happen by accident.
- **Inverted grayscale by default** in nuclear medicine (uptake dark), the convention of the field. It
  can be turned off in the NM button menu.
- **Geometric mean √(ANT × POST)**, computed on the fly, as a third view. The posterior is mirrored
  before combining — without that the arithmetic adds the liver to the spleen.
- **Real timing in dynamic studies**: each frame's duration comes from the phase sequence (0054,0032),
  not from a single value. In a 20 × 2 s + 20 × 30 s study the program knows frame 21 starts at 40 s —
  this is what will support the time-activity curves of the next stage.
- **Decay correction and counts per second**, with the half-life read from the header and, when missing,
  from a table (Tc-99m, I-123, I-131, Ga-67, In-111, Tl-201, Lu-177).
- **Nuclear medicine phantoms** in the sample data: a whole-body bone scan with ANT and POST in one file
  and a renogram with a 2 s flow phase and a 30 s dynamic phase.

Not yet: ROI time-activity curves, per-study quantification, SPECT/CT fusion and cardiac.

## What's new in 0.22 — list marks, per-series download, PACS search and 3D cutting

- **Marks in the study list**, next to the patient's name (like the ✎ for comments): **⌛ report in
  draft**, **✔ signed report**, **✔↻ amended report** and **▦ saved film**, each explained on hover.
- **A study that is still downloading**: the series that have not arrived yet show up in the left strip,
  **lighter**, as "queued", "downloading now" or "skipped" — the way Weasis does it. Right click one of
  them: **Do not download this series** (or cancel the whole study). For that, downloading is now done
  **series by series**: the program asks the PACS for the series list and fetches one at a time, so you
  can drop one in the middle. When the PACS does not answer at series level it keeps fetching the whole
  study.
- **PACS search**: the **Search** button turns into **Stop** while the search runs — the C-FIND is
  aborted and whatever arrived stays on screen. **Modality** accepts more than one (type `CT, MR`).
  Besides the ready-made periods there are now **Exact date…** and **Range…** with a calendar. And the
  **"on this computer"** status (yes / partial) now also appears **for each series**.
- **3D**: a new **Surface** mode beside VR, MIP, MinIP and average — first hit on the threshold, with
  the exact crossing interpolated and the normal computed at that point, so the outline comes out
  smooth. And a **Cut…** button: from the **3D cursor** (or the middle of the volume) it keeps only what
  is behind, in front, to the right, to the left, above or below — the cut face is drawn flat, like a
  real cut. It works for VR and MIP too, and the volume still rotates normally.

## What's new in 0.21 — six features at once

- **Correct DICOM tags**: wrong name, wrong side, wrong view, wrong date typed on the device. Right
  click on the image (DICOM information → **Correct**) or on the study list. The program saves a
  **corrected copy** with new UIDs and a reference to the source image — **the original study is never
  altered**. Series/image fixes stay in the same study; patient fixes create a new study.
- **Sharpen and smooth filters**: three sharpening levels (unsharp mask) and two smoothing levels,
  applied **to the image values**, before windowing. The chosen filter follows the image into the film,
  the PDF, the exported images and the **HTML viewer** (Filter button, key S).
- **Monitor GSDF calibration** (DICOM PS3.14): enter your monitor's black, white and gamma and the
  program builds the table that makes the gray steps **perceptually equal**. It shows the deviation
  before and after (on an ordinary monitor it drops from ~65% to ~5%) and comes with four test
  patterns — 16 steps with a 5% patch, a ramp, contrast near black and white, and line pairs —
  including full screen. The calibration is **per monitor**.
- **3D surface and STL**: from a segmentation you already made or from a density range (bone, cortical
  bone, skin, metal). The mesh comes out of *surface nets* — closed and smooth, no blocky look — with
  largest-piece-only, reduce and smooth options, and writes a **binary STL** for 3D printing or
  planning.
- **DSA (digital subtraction)**: mask from a chosen frame or the average of the first three,
  **logarithmic** subtraction (the one that really removes bone) or linear, inversion, and a **mask
  shift** with arrows to remove the motion ghost.
- **4D cardiac**: series with the same slices repeated across phases are recognised on their own (by
  position, with no tag needed). Scrolling now moves **through the slices without leaving the phase**;
  the phase cine plays the cycle **at a fixed slice**; you can **compare two phases side by side**
  scrolling together; and MPR/3D builds the volume **of the phase you are on**.

## What's new in 0.20.1 — print servers as a table

The server list became a **table like the DICOM nodes one**, with a **tick box to turn each server on or
off** in the first column and the columns that matter: name, AE Title, port, who it accepts, what it does
on arrival, sheet template, whether it stores in the database and its status (*Receiving*, *Off* or the
port error). There is also **Test (C-ECHO)**, which calls the server itself to check that the port is open
and answering. Ticking takes effect when you click OK.

## What's new in 0.20 — printing on its own: several servers, rules, a logo and automatic ultrasound films

- **A Prints button on the home screen** and a window just for this (**Print settings**) with tabs for
  servers, destinations, rules, sheet templates and automatic film building.
- **Several print servers at once**: one AE and port per device or per area, each with its own fixed
  destination, its own sheet template and its own choice of storing sheets in the database. The list
  shows which server each job arrived on.
- **Forwarding rules**: *when* — server, sending AE (accepts `MG*`), label text, film size, number of
  sheets and a time range (including one that crosses midnight); *then* — destination and template.
  They are checked in order, and a rule can **let the next ones run**, so one job can be saved as PDF
  *and* printed on film. With no rule at all, nothing leaves on its own.
- **Sheet templates with a logo**: logo, clinic name, second line, what to show (patient, date, device),
  footer, film or paper background, margins — with a **live preview** in the editor. Either keep the
  sheet as it came or **rebuild it with our own grid** (we keep each image box separately, so 2×2, 3×3…
  are all possible). It applies to PDF, the computer's printer and the DICOM printer.
- **Identifying the patient is easier**: the program lists **studies in the database from the same
  device and time** and one click fills in name and ID; with Tesseract installed, an **OCR** button
  tries to read the header burned into the sheet.
- **Automatic ultrasound films**: ultrasound sends images by C-STORE, not by printing — now, a few
  seconds after the study stops arriving, the program builds the film in the layout you chose and leaves
  it ready in the print list, or forwards it straight away.

## What's new in 0.19 — the program as a DICOM printer

Ipê now **receives films from the modalities** (CT, MR, MG, US) as if it were a film printer,
keeps them in a **print list**, and lets you forward each job wherever you want.

- **Turn it on** under Network → DICOM network → **DICOM printer**, then set the AE, IP and port shown
  there on the modality (default **11113**: film printers normally use 104, but the program never runs
  as administrator and on Linux ports below 1024 require that; almost every modality accepts another
  port).
- **What arrives** is the finished sheet: the grid (`STANDARD\2,2`, `ROW`, `COL`), film size,
  orientation, polarity, requested true size in mm and the pixels of every image box, stored **exactly
  as they came**. The printer status (N-GET) is answered, which many modalities ask for before sending
  the first image.
- **Patient name and ID do not come**: DICOM printing doesn't carry them (they are burned into the
  pixels). When the modality writes something in the **film session label** or Owner ID the program
  picks it up; otherwise you type it with **“Identify patient”**.
- **Print list (Ctrl+Shift+P)**: received films and the ones **built here in the composer** live in the
  same list, with a sheet-by-sheet preview, the film parameters and the status of each job.
- **Every sheet also becomes a study** in the database (Secondary Capture), so you can open it in the
  viewer like any other.
- **Send to…**: one job or many at once — **PDF in a folder**, the **computer's printer**, a **DICOM
  printer** (replayed *as it came*: same grid, same film size, box by box) or **PNG/JPEG images in a
  folder**. Nothing leaves on its own unless you pick a fixed destination under “On arrival”.

## What's new in 0.18.2 — edit protocols from the step list

In the mammography bar, **"Edit protocols…" is no longer a separate button: it is now the last line of the
step list** (after a separator). Choosing it opens the editor and **does not change the step you are on**.

## What's new in 0.18.1

The blanked implant no longer has a jagged edge: the implant is found on a reduced image (fast), but the
border is now **redone at full resolution** — in a narrow band around the coarse contour each pixel is
decided by its own value, with the threshold halfway between silicone and neighbouring tissue, followed by
a majority filter. The contour matches the real one to within a pixel. The blanked area is also always the
middle grey of the window actually on screen.

## What's new in 0.18

**Blank implant, rebuilt**: it used to look for the implant by density, which fails on real studies because
a dense breast is bright too. It now looks for the **lack of texture** — the silicone is a large, bright,
*smooth* area. If it still cannot find it, right-click inside the silicone → *Blank the implant from here*.

**The exported HTML viewer now does mammography**: a *Mammography* button lays CC and MLO of both breasts
side by side with the chest wall towards the centre and the tissue window; *Quadrant* (Q) zooms the
posterior-upper then the posterior-lower quadrant on all frames at once, anchored to the corner; *Breast
window* redoes the window on the tissue alone. Side, view, breast box, chest-wall side and tissue window are
computed at export time and travel with the file. The exported viewer is written in the language in use.

## What's new in 0.17.2

**Blank implant** (mammography bar, Alt+I): the implant is shown as a flat, textureless area — only the
capsule line remains — and the window is computed on the breast tissue alone, the way mammography units
present a prosthesis. It applies to every frame at once and never changes the file. Quadrant zoom now has
two steps instead of four: posterior and upper → posterior and lower → whole image.

## What's new in 0.17

**This computer's database folder** can now be changed from inside the program (right-click *This
computer's database* in the Locations panel, or *Settings → Change this computer's database folder…*); it
asks whether to **move** the database and the files or **just point** to the new folder, and remembers the
choice.

**Mammography:** zoom and pan are now **synchronized between frames** by anatomical position — the other
breast is mirrored, and it holds across 2D, tomosynthesis and the recombined image. Quadrant zoom follows
the breast instead of the screen, in four steps: **posterior and upper → posterior and lower → anterior and
upper → anterior and lower → whole image**, and the quadrant is **anchored to the corner**, so the chest
wall stays on the side of the screen it was already on and the two breasts stay mirrored. Scrolling from 2D into the tomo slices no longer jumps, and
*LE ⇄ Recomb.* keeps the quadrant. The step name is on the left of the bar and both arrows on the right.

## Languages

The program speaks **Portuguese, English and Spanish**. The first time it opens it asks which language to
use (suggesting the system one); after that, *Settings → Language*. The change takes effect when the
program is reopened.

Everything is translated — menus, warnings, help, **protocol names** and the **report templates** (CT,
mammography, MR and PET), including the messages the program assembles on the fly.

**Translating into another language does not require programming**: *Settings → Language → Translate…*
opens a table with the Portuguese text on one side and yours on the other (with a filter and a *only the
missing ones* option). The result is saved in `<data>/locale/<language>.json`, a plain file you can send
to someone else or back to the project. The same editor is used to fix a word in English or Spanish.

## What already works

- **Local database (SQLite):** patient → study → series → image, with thumbnails.
- **Import:** folders with subfolders, CD/DVD, loose files and ZIPs. Files, folders and ZIPs can also be
  dropped onto any window of the program. Importing runs in the background, with a progress bar and a
  cancel button, and skips duplicate images.
  - By default files are copied into the storage folder. In `settings.json` you can switch to
    "reference only" (`copy_to_storage: false`).
- **Browser:**
  - search by name, ID, accession or description (several terms with `|`);
  - filters by modality and period;
  - series panel with thumbnails;
  - comments per study;
  - case lists (normal or meeting, with a friendly name);
  - protect and delete studies. Studies in lists are protected.
- **2D viewer:**
  - layouts from 1×1 to 3×3; double click maximizes a frame;
  - drag a series from the side strip into a frame;
  - window/level with presets (keys 1–6), zoom, pan, scrolling, ruler in mm, invert and cine;
  - slices ordered by their real position in the patient (not by image number);
  - support for multiframe, color images (US), MONOCHROME1 and JPEG/JPEG 2000;
  - orientation letters (A/P/R/L/S/I);
  - automatic layout for MG (RCC, LCC, RMLO, LMLO).
- **Clickable areas in the overlay:**
  - click "Im x/y" or the position → scroll;
  - click the orientation letters → pan;
  - click the FOV/zoom → zoom;
  - click W/L → window;
  - click the series name → series list.
- **Mouse:**
  - right: click and release opens the menu; hold and drag zooms;
  - middle: click fits to the window; drag pans;
  - wheel: scrolls the slices; with Ctrl, zoom; with Shift, jumps 5 slices.
  - All configurable in `settings.json`.
- **Hide patient data** on screen (the basis of meeting mode).
- **Lesion tracking** (RECIST 1.1, mRECIST, PERCIST 1.0 or free), **CAD/AI overlays** (SR, GSPS, SEG,
  RTSTRUCT), **3D segmentation** with volume, SUVpeak, TMTV/TLG, and a **structured report** with
  BI-RADS® that writes itself, exported as PDF, DICOM Encapsulated PDF and DICOM SR.
- **Mammography**: protocol by steps, quadrant zoom, magnifier, tomosynthesis in the same scroll as the
  2D view, slab thickness, contrast-enhanced mammography (low energy ⇄ recombined) and implant mask.
- **PACS**: query/retrieve, DICOM node, automation, routing, DICOM printing and **opening a study while
  it is still downloading** (streaming), with a network test per node.
- **External call:** `ipe open --accession 123` opens the study. If the program is already
  running, the call goes to the existing window.

## Installing on Windows

1. Install **Python 3.12** from <https://www.python.org/downloads/>, ticking **"Add python.exe to PATH"**.
2. Double-click `instalar.bat` (only the first time; it downloads about 300 MB of libraries).
3. Double-click `executar.bat`.
4. To try it without real studies, use **File → Generate test studies (phantoms)**.

## Installing on Linux

```bash
./instalar.sh
./executar.sh
```

## Command line

On Windows use `.venv\Scripts\ipe.exe`. On Linux use `.venv/bin/ipe`.

```
ipe                              opens the interface
ipe open --accession 123456      opens the study by accession number
ipe open --study-uid 1.2.3...    opens it by StudyInstanceUID
ipe open --patient-id ABC        opens the patient's most recent study
ipe open C:\folder\study         imports the folder and opens the studies
ipe import D:\ --reference       imports without copying (reference only)
ipe sample C:\temp\phantoms      generates synthetic test studies
ipe info                         shows where the database, files and settings live
ipe open --accession 123 --node PACS   if not in the database, queries the node, downloads and opens
ipe retrieve --accession 123     only downloads from PACS
ipe "ipe://open?accession=123"  same effect as the link
ipe register-url                 registers the ipe:// link in the system
```

The environment variable `DICOMVIEWER_HOME` changes the data folder. That allows, for instance, keeping a
separate database for each research project.

## Where the data lives

Run `ipe info` to see the paths. On Windows they are in `%LOCALAPPDATA%\DicomViewer` and contain:

- `dicomviewer.sqlite` (database);
- `Storage\` (copied DICOM files);
- `settings.json` (preferences);
- `locale\` (your own translations);
- logs.

## Code layout

```
src/ipe/
  core/        settings, logs, phantom generator, languages (i18n.py)
  db/          models (SQLAlchemy) and queries
  importer/    scanning, deduplication, thumbnails
  network/     DICOM node (server.py), client (client.py), queue (service.py), link and API (external.py)
  imaging/     pixel reading, geometric ordering, window/level, cache, measurements,
               lesions (lesions.py), CAD/AI (overlays.py), 3D segmentation (segment.py, seg_writer.py)
  reporting/   report: templates, filling, BI-RADS, PDF, DICOM PDF and SR
  ui/          main window, browser, dialogs, report window (report_window.py),
               automatic screen translation (qt_i18n.py) and translation editor (translate_dialog.py)
  ui/viewer/   viewer tab, 2D viewport, synchronization (sync.py), lesions/CAD/segmentation (onco.py)
locale/        bundled languages (pt-BR.json, en.json, es.json)
tools/         translation catalog tools (i18n_extract/merge/show.py)
tests/         automatic tests (run testar.bat)
```
