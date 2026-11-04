# Ipê release history

*The program was called **DicomViewer** up to version 0.99.10. [Back to the README](README.md).
The full history, with every version, is in Portuguese: [CHANGELOG.md](CHANGELOG.md).*

## 0.99.43 — mosaic in the viewport; CAD hidden until revealed
- **Slice mosaic** (right-click ▸ Mosaic, or shortcut): 2 × 2, 3 × 3 or 4 × 4 consecutive slices of the same
  series inside one viewport; the wheel turns the page; double-click returns to the normal viewport on that
  image.
- **Read first, see the CAD after** (Settings ▸ CAD/AI): CAD marks start hidden in each study; **CAD/AI ▸
  Reveal the CAD** (or the shortcut) shows them and says how long you read before.

## 0.99.42 — identity masking profiles
- **Hide patient data** gets profiles (button arrow): **Hide everything** (as before), **Screen**
  (pseudonym, real dates), **Teaching** (pseudonym, dates shifted by the same number of days for the whole
  patient — the interval between studies stays) and **Publication** (no dates or device). They apply to the
  viewport, the tab title and the database list; the viewport corner shows the profile in use.
- Anonymized export gets **Shift the dates**, checked automatically in the Teaching profile.

## 0.99.41 — key images and annotations in DICOM; draft measurements
- **Save key images and annotations in the study** (Key button): key images are written as a **KO** and
  measurements, arrows and texts as a **GSPS**, with each measurement's value beside it; they go to the
  PACS with the study and open in other viewers.
- An incoming **KO** marks the key images here; with several **GSPS from other systems**, only the most
  recent is shown; **Bring the measurements in for editing** (CAD/AI button) turns the measurements of an
  outside SR or GSPS into Ipê measurements.
- **Draft measurement** (right-click ▸ Draft, or a preference for every new measurement): dashed, it does
  not go to the SR, the GSPS, the report, the spreadsheet or lesion tracking.
- Fixed: the measurements **SR** used only the tag's pixel size — a measurement calibrated by hand or on
  ultrasound came out in pixels. It now uses the same scale as the screen (checked on the archive: 10, 20
  and 50 mm).

## 0.99.40 — structures: edit masks and save SEG / RTSTRUCT
- New **Structures** window (3D button, or CAD/AI): list of the study's masks with name, color, type
  (lesion, organ, other), volume, *locked* and source; imports saved lesions, SEG segments (including the
  AI ones) and RTSTRUCT contours.
- **Brush and eraser** on any viewport and plane of the study (disc in the plane or 3D sphere, radius in
  mm, option to paint only within the clicked intensity range, never over locked structures).
- **Grow / shrink** in mm, **largest island only**, **remove small islands**, **fill holes**,
  **interpolate the slices** between two drawn ones, **trim by range**, **merge / subtract / intersect**;
  undo and redo.
- **Save SEG** (with each segment's type) and **save RTSTRUCT** (contours along the pixel edges, holes as
  inner contours); **update the saved lesion** with the corrected mask and volume; send the volumes to
  the report.
- Measured on the archive: the AI SEGs (abdominal organs, cephalometry, implant) are imported, corrected
  and written as RTSTRUCT in under 1 s per structure.

## 0.99.39 — rigid motion correction in the dynamic study
- In the **Dynamic** window (and in the dynamic editor under Settings), **Include rotation**: besides
  translation, rigid registration of each phase onto the pre-contrast; a phase rotated 0.75° or more is
  resampled in 3D before the maps, the curves and the lesion capture. The panel title shows the largest
  displacement and rotation corrected.
- Measured first on the archive: in 6 breast MRIs (11 phases) the rotation between phases was 0–0.5° and
  the translation under 1.3 mm — so the option is off by default and, below the threshold, the phase keeps
  the translation only (no resampling blur).

## 0.99.38 — rigid registration between studies
- **Align automatically with the other study** now performs **rigid** registration (3D rotation and
  translation), with correlation (same sequence) or mutual information (other modality or sequence),
  over several resolutions; the quality is shown in the status bar.
- When the other study is rotated 1° or more, the program offers to **save it in this study's plane**
  (new series with this study's geometry and Frame of Reference): both then move together slice by slice.
- The registration matrix is stored; validation by point pairs (mean and maximum error in mm).
- Checked on the archive: real 3D brain MR with a known transform, mean error 0.4 mm in 6 s.

## 0.99.37 — diffusion on any MR
- **Diffusion** button (also under Applications): **ADC map** from the series' b-values (regression over
  all checked b), saved as an MR series of the study in ×10⁻⁶ mm²/s, with a noise threshold and minimum
  R²; **synthetic DWI** at a chosen b, labelled as synthetic; **ADC in an ROI**, with the scanner's ADC
  and the signal at each b side by side, and the sentence for the report.
- The b-value comes from the file (standard, GE, Siemens, Philips); on anonymized GE series the b0 is
  inferred; with no b in the file, it can be typed. Warnings before computing: single b, no b0, low b,
  incomplete slices, different TE.
- Checked on the archive: on the brain the ADC matches the scanner's (ratio 1.0002).

## 0.99.36 — usage-mode plan completed
- **Automation rules with an owner**: scheduled queries, priors, routing, dynamic preparation and
  automatic management get *Visible to* (Everyone / Only me / chosen users) and a column in the list;
  their own tab in personal and shared settings, with *Copy for me*. All of them still run.
- **Where automation downloads go**: to the shared database (they used to go to the bank of whoever was
  logged in); a personal query can send them to its owner's bank. A **prior** goes to the same bank as
  the current study.
- **References** for cephalometry and skull indices: mine only, or for everyone on this computer.
- **External calls** (RIS, link, API) no longer open another user's personal studies (the administrator
  can, and it is logged).
- **Case lists travel** with studies between this computer and the central server (folder, list,
  friendly name, history, answer and notes, without duplicates).
- **Client mode**: a new study downloaded from the PACS follows "my bank on this computer".
- Fix: saving a rule's configuration without the owner no longer erases the owner.

## 0.99.35 — translation review
- **Texts that stayed in Portuguese** in the English or Spanish program: about 650 new texts translated,
  including the AI screens and messages (CAD/AI, segmentation, spine, cephalometry, lymph nodes, skull
  indices, implant, AI tasks), automatic management and the program's closing message.
- The status bar, tray notices and hand-drawn tooltips are now translated.
- Sentences assembled at run time (with numbers, names and steps inside) and multi-line texts are
  translated piece by piece; names such as "Abdominal segmentation" used to come out half translated.
- Checked by opening the program in English and Spanish and going through menus, buttons, Settings
  windows and the AIs.

## 0.99.34 — fixes: database in English and cancelling AIs
- **Empty database in English**: the "All" modality filter was searching for a modality called "All".
  Fixed for every drop-down list: the screen shows the translation and the program reads the original.
  Menu permissions (import, export, configure) and opening the right Settings page also only worked in
  Portuguese; fixed.
- **AI tasks that would not cancel**: a segmentation started in the viewer was destroyed when the study
  was closed, but the task stayed "running" forever, the study stayed "busy" (no other AI could run)
  and Cancel did nothing. It now keeps running with the study closed and saves its result; Cancel always
  closes the task (forcibly, if the job does not stop within 15 s) and releases the study.

## 0.99.33 — English by default
- The program and the README now default to **English**; Portuguese and Spanish are still available.
- The Windows **installer** asks for the language on its first screen (English selected) and saves it
  for the program; `instalar.bat` and `instalar.sh` ask too. The portable package asks on first launch,
  with English selected. Existing users keep the language they chose.
- New command `ipe set-language en|pt-BR|es`.
- README: `README.md` in English (now complete), `README.pt-BR.md` in Portuguese, `README.es.md`.
- GitHub release notes are now in English.

## 0.99.32 — following the AIs
- **AI tasks**: progress (queued, building, running, saving, done, error) and **cancel**, also for the ones
  that run by themselves when an exam arrives. From the Applications button, the View menu and the
  "⚙ AI: …" notice on the status bar. Cancelling saves nothing to the exam.
- **Database**: ✦ on exams with AI results (the tooltip says which) and ⚙ while an AI is queued or running;
  **AI** column.
- **Abdominal organs** in the viewer (own button on abdomen CT/MR and in the Applications button).
- **Settings windows** shrink and maximize (the minimum used to be almost the screen size).

## 0.99.31 — wave A (ideas from Weasis ViewerHub and Eden)
- **Report in progress** on the central server: whoever opens the report holds it; the next one chooses
  read-only or take over (logged), and the server refuses saving a report you do not hold.
- **IHE IID opening** (`/IHEInvokeImageDisplay`, `requestType`) and filters in the link and the API:
  most recent exams, modalities, period, description; several IDs and UIDs.
- **Encrypted ipe:// link** (`c=`): no patient data in sight, built with the token, valid for 24 h.
- **Intensity profile** along a ruler or polyline, with a chart.
- **Remove the CT table** in MPR and 3D.
- **Exam history** on right click; **delete a single image**, logged.
- **Close the exam automatically** when the report is signed or after idle time.
- **ILO report template** (pneumoconiosis).

## 0.99.30 — three-level settings
- **Display and mammography protocols, breast dynamics layouts, sheet templates, report templates and
  case lists** can now be service-wide, shared with chosen users, or personal.
- Changing a service item without the configure permission creates a personal copy that only you see.
- **Settings ▸ Users ▸ Personal and shared settings…** shows and changes who sees each item; case lists
  have **Visible to** on right click.
- Shortcuts, mouse and presets: go back to the computer default or make yours the default.
- In client mode the server stores and enforces everything (another user's personal lists are not served).

## 0.99.29 — collapse the database panels (Weasis-style)
- **Locations and lists** (left) and **Series and comments** (right) collapse to a strip on the edge
  with the ◂/▸ button in their title; one click on the strip brings them back at their previous size.
  The exam list gets the full width.
- The **Lists** button and the **View** menu open and collapse the panels; the state is remembered.

## 0.99.28 — personal bank on the server or on this computer
- **Client mode**: the Locations panel shows the **Central server** and **This computer's database**; the
  local one opens without a network and works as a case bank.
- **Right click ▸ Bank**: copy or move from the server to this computer, and send from here to the server
  (to my bank or to the shared one). Reports, measurements, annotations and key images go along.
- **Exams I import go to "my bank on this computer"** (not uploaded) or to my bank on the server
  (uploaded already marked).
- **Send a whole database to the server** (migrating a computer that became a client); the administrator
  sends each exam to its owner's bank.
- **The server enforces the bank**: another user's personal exam does not show up in searches, DICOMweb or requests.
- Changing the usage mode warns what happens to the exams.

## 0.99.27 — personal and shared database
- Locations ▸ Database: everything I see, my database, shared, shared with me; the administrator also sees
  each user's database. "Database" column in the list.
- Right click on an exam ▸ Database: move to my database, to shared, share with…, and (administrator) hand
  to another user. The exam stays a single copy: only the mark changes.
- An exam arriving at a personal identity's AE goes to its owner's database; what you import or download
  follows your choice.
- Access log entries when the administrator opens someone's personal database or exam; hand over the
  whole database of someone who left.

## 0.99.26 — "Visible to" in settings
- DICOM nodes, identities, print servers, print rules and auto-film rules get a "Visible to" field: everyone
  (service), only me, or me and chosen users.
- Day-to-day choices show the service's, your own and what was shared with you; the administrator sees and
  edits everyone's in the settings screen.
- Users without the configure permission open "My DICOM nodes".

## 0.99.25 — usage mode on first use
- On first launch the program asks how it will be used: just me (opens without login), several people on
  this computer (creates the administrator there), this computer is the group server, or connect to a
  server. Works for the installer, the portable package, `executar.bat` and Linux.
- Settings ▸ Users ▸ Usage mode changes it later.
- Sign in with the Windows/Linux account, without a password, for users linked to that account.

## 0.99.24 — security review
- `ipe://` links without the token no longer open on their own: the program asks first (or accepts /
  refuses, in Network ▸ External call). With `&token=` in the link it opens directly. Constant-time token
  comparison.
- DICOM node: new "Registered nodes only, checking the node's IP" option.
- DICOM printer: new printers accept only the local network (existing ones unchanged).
- Central server: 5 wrong passwords in 10 min block the address for 10 min; warning when running without
  a certificate (HTTP).

## 0.99.23.1
- Fix: adjusting the spine numbering (e.g. sacralized L5) changed only the clicked tab; the other screens of the exam and a duplicate copy of the same SEG kept the old name. Now all are refreshed.

## 0.99.23 — transitional vertebra and spine numbering
- Fix: moving one level up in the lumbar spine produced two S1s; now the last free vertebra becomes S1,
  the sacrum S2 and the disc S1-S2; renumbering out of the spine is refused with a warning.
- Numbering by the physical sequence, counted from C2 (in the series or another series of the exam) or
  from the last rib (T12, CT); AI names only without an anchor.
- Transitional vertebra named lumbarized / sacralized (S1 lumbarized, L5 sacralized, L5 fused to the
  sacrum), thoracolumbar transition, rib pair count, rudimentary disc and suggested Castellvi.
- Right click ▸ Spine numbering ▸ Adjust…: "this vertebra is…", transition, Castellvi and the report
  sentence; saved with the exam, with a warning on the patient's next exam if the numbering differs.

## 0.99.22 — cheap round of the AW plan: seals, patient mix, windows, measurements and output
- Integrity seals at the top of the viewport: lossy-compressed mammography in red ("not suitable for
  reporting"), lossy compression elsewhere, Modality LUT table, non-square pixel, derived image.
- Patient mix: red seal when viewports show different patients; an external call bringing another
  patient asks (close the previous on all monitors / keep both / don't open) or follows the setting;
  the film asks before mixing patients.
- Switch WL through the windows stored in the file; typed window; "save current window as preset"
  with per-modality preset lists.
- Landmark blend in dynamic and DSA subtraction; temporal MIP and temporal mean maps.
- Reference ROI (others show % of it); 3D ruler; thick-slice warnings and optional ± uncertainty.
- AI result status (automatic / edited * / accepted by whom and when), stored with the exam.
- Copy (Ctrl+C) with its own annotation level and a minimum stamp (series, window, scale, processing).
- Fix: a PACS reply (priors, save without implant) arriving after the tab closed raised an error; now discarded.

## 0.99.21 — lymph node levels: skull base from the jugular veins
- The skull base (top of levels II and V) now comes from the top of the internal jugular veins or
  internal carotids; TotalSegmentator's skull includes the mandible.

## 0.99.20 — cervical lymph node levels
- Lymph node level map (I–VII, right/left) on neck CT from TotalSegmentator landmarks and the imaging
  rules of staging, labeled in any plane; a lesion segmented with the Segment tool gets its level.

## 0.99.19 — olfactory bulbs
- New guided measurement: olfactory bulb volume by planimetry (Cavalieri) on coronal T2, and
  olfactory sulcus depth.

## 0.99.18 — head indices measured on SynthSeg's 1 mm grid
- Measurements now use SynthSeg's 1 mm segmentation (thick 2D series gave a one-pixel 3rd ventricle);
  SWAN, phase, angio and perfusion series are no longer picked.

## 0.99.17 — automatic head indices (SynthSeg)
- Evans index, 3rd ventricle width, callosal angle and hippocampal/ventricular volumes from SynthSeg
  (DIPY's PyTorch version) on head MR of any sequence or CT, with the same review window; the MRPI 2.0,
  Evans and callosal angle guided measurements open pre-filled. Re-run instalar_segmentacao once.

## 0.99.16 — automatic cephalometry on arrival
- **Settings ▸ CAD/AI ▸ Nasopharynx cephalometry**: runs automatically when a CT arrives, filtered by
  the study description, with the preferred series, maximum thickness, minimum slices and
  destinations. The numbers are stored in the review image, so the Cephalometry button reopens them
  without running again. The measurement lines show in any plane that contains them
  (reformatted sagittal, axial, oblique); “Show in viewport” jumps to each one.
- Every segmentation and AI overlay (SEG, RTSTRUCT) now also shows in reformatted planes.

## 0.99.15 — automatic nasopharynx cephalometry
- **Cephalometry** button (face, nasopharynx and neck CT): TotalSegmentator (open tasks) finds the
  palate, pharynx, hyoid, mandible, tongue and cervical vertebrae, and Ipê measures the minimal
  airway cross-sectional area perpendicular to the airway axis, soft palate length and thickness,
  posterior airway space, hyoid to mandibular plane, tongue size and the hyoid spine level.
- Review window with the source of each number (automatic or edited), manual measurement, editable
  references and report text; a review image with the lines goes into the study.

## 0.99.11 — DicomViewer becomes Ipê
- New name and icon (the yellow ipê flower); source code published on GitHub under GPL-3.0.
- The data folder, the factory AE title `DICOMVIEWER`, `dicomviewer://` links and
  `python -m dicomviewer` keep working; the new link is `ipe://`.
- Prior studies chosen above the thumbnail strip; clicking an empty viewport lists the series.

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
