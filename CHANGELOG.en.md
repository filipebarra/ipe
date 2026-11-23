# Ipê release history

*The program was called **DicomViewer** up to version 0.99.10. [Back to the README](README.md).
The full history, with every version, is in Portuguese: [CHANGELOG.md](CHANGELOG.md).*

## 0.100.110 — PACS: download straight to the client
- Ipê client, **PACS** window: button and right-click **Download straight to the client**. The node sends to the central
  server, the server passes the study to this computer's database and **deletes its own copy once the whole study has
  arrived here** (up to 3 retries for anything missing). Whatever was already on the server before stays there. The
  server does not run arrival rules on a pass-through study; this computer's rules run when it arrives. Logged in the
  access log (`transito_apagado`).

## 0.100.109 — Study link also from Ipê Web
- **Study link (no password)** button on the Ipê Web viewer toolbar (users who can export): for whom, what else the
  link can do (AI, send, attach), validity; **Create and copy**; the study's links with **Revoke**. Hidden in a
  session opened by a link (a link does not create another).

## 0.100.108 — Study link (Ipê Web), no password
- Right-click a study ▸ **Create study link (Ipê Web)…**: a link that opens **only that study** in Ipê Web, straight
  in the viewer, **without a password** — no list, no database, no report. On creation: for whom, what else the link
  can do (**run and review AI**, **send to the PACS**, **attach PDF and images**) and how long it lasts (1, 3, 7 or 30
  days). The window lists the study's links (uses, expiry) and **revokes** them — whoever has one open loses access
  immediately.
- Security: random token per link (the server stores only its hash), after the "#" and removed from the address bar;
  the server only lets through the allowed routes and that study's UIDs; wrong attempts per IP are limited; creation,
  use, denial and revocation are audited. Creating a link requires the export permission.

## 0.100.107 — Batch on an Ipê client: bring to this computer and delete from the server
- In the batch's **What to do** step (Ipê client), with **Also bring the studies to this computer** checked, the
  delete option now says what it does: **delete from the server the studies the batch downloaded from the PACS, after
  they arrive complete on this computer**. The client only tells the server once the study has fully arrived (it
  retries what is missing, up to 3 times); what was already on the server before the batch is never deleted.

## 0.100.106 — Mammography in Ipê Web: density, calcifications and silicone removal on demand
- In the **AI** tab of Ipê Web (and right-click ▸ AI in the database), mammograms list **Breast density (BI-RADS)**,
  **Breast arterial calcifications** and **Silicone implant: remove the silicone**. They run on the whole study, in the
  server queue, without the segmentation package. "Remove the silicone" runs even with the on-arrival correction off:
  useful for older studies that arrived before it.

## 0.100.105 — Ipê Web: the study opens while it arrives; installer with "windows" in its name
- **Opening link**: a study coming from the PACS opens as soon as the first images arrive; new series join the strip
  and a series that grew is reloaded in its viewport, on the same image, with a notice of how much has arrived.
- The Windows installer is now named **`Ipe-<version>-windows-installer.exe`** (like the Linux and macOS packages).
  Automatic updates recognize both the new and the old name.

## 0.100.104 — Ipê Web: keep me signed in for 1 day
- **"Keep me signed in on this computer (1 day)"** at the Ipê Web login: the login works in every browser tab and in
  opening links (`#/abrir?…`), even when idle, for 1 day. "Sign out" forgets it in every tab. Unchecked, it stays as
  before (this tab only, 12 h idle). The server logs it in the audit; the administrator can turn it off
  (`web.manter_conectado`).

## 0.100.103 — Ipê Web: open by external call
- **Opening address**: `…/web/#/abrir?acesso=12345` or `…/web/#/abrir?id=98765&data=20261123&mod=MR` (also `uid=`).
  Ipê Web searches the server; if not found, the PACS nodes the server shares, **downloads and opens** it when it
  arrives, with progress on screen. More than one study: a list to choose from. Login is still required (without a
  session it asks for the password and returns to the address). Date as YYYYMMDD, YYYY-MM-DD or DD/MM/YYYY.

## 0.100.102 — Liver MRI summary as an image
- The liver AI (fat, iron, stiffness) saves a **summary image (OT)** in the study, like the breast density one:
  series "Fígado na RM: resumo (Ipê)" with PDFF and grade, dual echo, R2*, estimated iron (LIC), stiffness and range,
  each result and who reviewed it. It is redone at every review in AI findings (desktop and Web): it shows the
  corrected numbers and goes from "not reviewed" to "reviewed". It goes to the configured destinations too.

## 0.100.101 — AI from the database, AI queue, liver table
- **Right-click a study ▸ AI**: the study's AIs, as in the viewer's AI button, each with its options (suggested
  series, redo, another series); those the rule left out under *Other AIs*. Several studies: the AI is queued on all.
- **AI queue**: requesting an AI while another runs on this computer is no longer blocked — it joins the queue and
  starts by itself (shown in AI tasks, where it can be removed).
- **Reports ▸ Liver MRI (steatosis, iron, stiffness): measurements and confirmations…**: the table of every study
  with the liver AI, like the breast density one, with filters and CSV.
- **"On this computer" column** on an Ipê client: the server's study is also here, complete or partial.
- **Batch from spreadsheet**: a study already in Ipê goes through the arrival rules (automatic AI, routing,
  printing), like a downloaded study (option checked by default in the "What to do" step).
- Release notes: macOS is no longer "experimental".

## 0.100.100 — Ipê client: AIs on the server or on this computer
- **Preferences ▸ CAD/AI ▸ On an Ipê client, run the AIs**: **on the central server** (default) — the AI requested
  in the viewer goes to the server queue and the result comes to the open study — or **on this computer**, and then
  the generated series and findings **go up to the server automatically** (before, the series stayed only in this
  computer's cache).
- New profile permission **Run the AIs on this computer** (by default: administrator and physician). Without it, or
  without the AI package installed here, the AI goes to the server, with a notice.
- **Batch on the client**: with "on this computer", the server searches and downloads, asks this computer for the
  AIs, collects the result and goes on with sending, printing and exporting.

## 0.100.99 — batch: what to search by, and in which order
- **Batch from spreadsheet ▸ Find the study**: you choose **what to search by and in which order** — Study UID,
  accession number, ID + date + modality, ID + date, ID + modality (any date), ID only (any date). Ipê tries the
  first one checked; if it finds nothing, the next. With "ID only" or "ID + modality", rows without a date are
  processed too.
- New column **Ipê: found by** (which attempt found it); for "not found", the note lists the attempts used.
- The breast template searches only by UID, accession and ID + date + MG.

## 0.100.98 — batch: why it was not found
- **Batch from spreadsheet**: when a study is not found, the note now says **why**: the node error (if the search
  failed); the studies the node returned that the filter removed (ID, date, modality); or, searching again by ID
  only, whether the patient has studies on **other dates or modalities** (with the closest ones) or none at all.
- PACS that does not filter by modality in the query: the batch searches again without it and filters in Ipê.

## 0.100.97 — batch from spreadsheet
- **Network ▸ Batch from spreadsheet…** (replaces the breast batch): for each row of a spreadsheet (CSV, XLSX or
  ODS), Ipê finds the study — by Study UID, accession number or ID + date, with a day tolerance, modality and
  "description contains" — first in its database, then in the checked nodes, in order, and does what you choose:
  run AIs, check the MRI protocol, send to nodes (originals, results or both), **print the AI review series**,
  **export** (PNG, one PDF per study, DICOM) and delete what came from outside.
- Each column's type is guessed from its title and can be corrected in the preview. A row with only the ID and
  no date is skipped.
- Output: the original spreadsheet with Ipê's columns, **one tab per AI** with the numbers, Summary and README.
  **Anonymize** replaces patient data with "Case 0001…" and keeps the key in a separate file.
- **Simulate** (only searches and counts), saved **templates** (the breast one is built in), **time window**
  (e.g. only 8 pm to 6 am), stop and resume. The log shows no patient names.
- **On an Ipê client, the batch runs on the central server** (its shared nodes, AIs and printers): the window
  follows it and, at the end, downloads the spreadsheet and the exported files. **Also bring the studies to this
  computer** copies each finished study to the local database (the server deletes what it downloaded only after the
  copy).

## 0.100.96 — AI menu translated; liver MRI on the site
- **Ipê in English or Spanish**: in the AI menu, the reason an AI does not apply to the study ("the study has no
  CT", "not found in the study: Skull and brain") showed in Portuguese, sometimes mixed. It now follows the chosen
  language.
- **Site**: new page "Liver MRI: fat, iron and stiffness", with a short video (maps and liver mask, AI findings
  and the stiffness review series) on an anonymized study.

## 0.100.95 — fixes: liver stiffness and database columns
- **Liver stiffness was not measured**: the calculation used a library (SciPy) the program does not install — on the
  user's computer the elastography step failed silently and the **Liver** button showed only fat and iron. It now
  uses only what Ipê already has.
- **Database columns**: a column the user turned on (e.g. **Added on**) was checked in the menu but missing from the
  table when the program opened — it had to be turned off and on again. It now shows on login.

## 0.100.94 — liver stiffness on MR elastography; scanner screen saves anonymized
- **Automatic liver stiffness (MR elastography)**: the **Liver** button (fat and iron) now also measures stiffness
  when the study has MR elastography (MR-Touch and similar) — no neural network in the measurement, like a manual ROI:
  the TotalSegmentator liver ≥ 5 mm from the edge, within the scanner's confidence area (the checkerboard of the
  masked elastogram), without the large vessels (from the acquisition's own magnitude). Area-weighted mean (the one
  for the report), median, p25–p75, area, slices, fraction of the liver within confidence and heterogeneity; with two
  acquisitions, both. Reference range (2D, 60 Hz) as text and a suggested classification. New series **"Liver
  stiffness: automatic ROI"** with the color elastogram, the ROI and each slice's value, to check.
- **Anonymization: scanner screen saves** (color elastogram, graphs — ImageType "SCREEN SAVE", Secondary Capture): the
  scanner burns the name, age, birth date and date into the screen header and still says there is no burned-in
  text. In anonymized export and case packages these screens now lose the whole header and footer. **Studies
  exported earlier with screen saves should be exported again.**

## 0.100.93 — MRI protocol check; vascular calcifications with implants
- **MRI protocol check** (Network ▸ MRI protocol check…): every incoming MRI is compared with the reference protocol
  of the study and scanner — missing or extra series, plane, 2D/3D, sequence, TR, TE, TI, flip angle, ETL, NEX,
  thickness, slice spacing, matrix, FOV, bandwidth, field, b-values and contrast, with per-protocol tolerances.
  **Build all from the archive** registers the dominant protocol of every study × scanner in the database at once; a
  good study can also become the reference. Results in the new **MRI protocol** column of the database (and ⚠ next to
  the name), in the study check (right click ▸ Tools) and in the *Checked studies* tab, with CSV.
- **Vascular calcifications in breasts with implants**: the implant edge was still counted as "calcification" in some
  views (and in the scales). The mammography implant mask (the same as "erase the implant") is now left out too, and
  the implant-corrected copy is not measured (the original is). Use "Measure again" on implant studies already
  measured.
- Translations: "right/left breast" and "none" in the calcification window; the "For the PACS to send here…" note in
  Network ▸ This computer.

## 0.100.92 — C-GET with compressed series, "All" filter in English and translations
- **C-GET**: when the requester accepts only uncompressed syntaxes, Ipê now decompresses JPEG-LS/JPEG 2000 series
  on the fly instead of leaving them behind (the study used to arrive without those series).
- **PACS search, database and case lists**: with the program in English or Spanish, the "All" modality was sent
  as "ALL" and found nothing.
- Missing translations in DICOM management (send queue, statuses, scheduled rules and weekdays), printing (films
  dashboard, unregistered sources, sends, "any") and the film composer (help and copies).

## 0.100.91 — vascular calcifications marked for B/W monitors and the PACS
- **Breast arterial calcification marks**: instead of red (dark gray on a B/W monitor), a **white outline with a
  black edge** ~1 mm around what the network found and **numbered arrows** at the ends of each vessel. In the window,
  Ipê Web and the marked images sent to the PACS (Secondary Capture) — confirm an old study again to redo its images.

## 0.100.90 — redo on every AI; the AIs in the Settings ▸ CAD/AI menu
- **Redo on the study for every AI**: organs, spine, cephalometry, head indices, lymph node levels and the common
  ones; breast density and arterial calcifications ("Redo the measurement on the study"). It uses the series the
  AI's rule picks; also in the AI button list.
- **Settings ▸ CAD/AI** lists every AI (there were six); each item opens the AI's page.

## 0.100.89 — redo the AI on the study
- **Redo on the study**: each AI menu (Liver, Composition, Nodules and the others) has "Redo on the study (preferred
  series in Settings)…" — before, with findings in the study, it could only be redone on the open series. It asks
  whether to discard the findings already reviewed.

## 0.100.88 — suggested classification of liver fat and iron
- **Suggested classification** in the AI findings window (new column and a table of the scales, as for breast
  arterial calcifications): steatosis by PDFF (5% threshold and Tang 2015 estimated grade) and iron overload by LIC
  (< 1.8 normal; 3.2–7 mild; 7–15 moderate; > 15 severe). Correctable; the report sentence uses the one that holds.
  Also in Ipê Web.

## 0.100.87 — liver iron on MRI from the right map; water-fat swap
- **Liver iron on MRI (important)**: on GE MRI with IDEAL IQ, the "WATER: IDEAL IQ (R2\*)" series (and "FAT: …")
  was taken as the R2\* map — "(R2\*)" is the sequence name — and, coming after the map, replaced it: the iron came
  from the water or fat signal. Redo the iron of studies measured before. The ImageType now decides.
- **Water-fat swap**: liver voxels above 60% while the rest is well below are left out of the PDFF, with a warning;
  with high R2\*, a warning that the PDFF is less reliable.

## 0.100.86 — AI findings in the export; assembled sentences translated
- **AI findings in the export**: the DICOM export (folder, .zip, anonymized copy in the database) carries the
  studies' AI findings in an `IPE_ACHADOS.json`; importing it into another Ipê brings them back with the state of
  each one. Anonymized, without the reviewer or the note.
- **English and Spanish**: sentences assembled from parts (such as the end of Lung nodules, "no nodule candidate
  (plus 1 below the minimum diameter)") came out half in Portuguese; now each part is translated.

## 0.100.85 — AI on the viewport series; emphysema on the parenchyma series; fewer out-of-memory failures
- **"… on this series"**: each AI's menu item runs on the active viewport's series, even when it is not the preferred
  one in Settings (some AIs used to switch to the preferred one). On error, the message names the recommended series
  — also in Ipê Web, when the viewport series is chosen.
- **Emphysema**: the preferred series is now the parenchyma/lung one (`PARENQUIMA|PULMAO|…`), and the button no longer
  swaps a sharp-kernel series for a soft one. On a study with both, the parenchyma series (with the 0.100.81 noise
  reduction) matched the report; the mediastinum series did not.
- **Memory**: in fast mode, a very thin series (e.g., a 0.6 mm chest CT) enters TotalSegmentator already reduced to
  1.5 mm, and the masks return to the original grid. TotalSegmentator helper processes no longer stay stuck (about
  2 GB each) when the AI crashes — before, the next AI also ran out of memory.

## 0.100.84 — Export: choose the series
- In the **Export** window (and in **Anonymize a copy**), the **Choose the series** box lists each study with its
  series so you tick only those to export, with **All** and **None**. It applies to DICOM, images and the anonymized
  copy in the database; a study with no series ticked is left out.

## 0.100.83 — Desktop Ipê no longer freezes with the embedded server
- When desktop Ipê is also the server, the background preparation of recent studies for Ipê Web read the headers
  with 8 threads and took turns away from the window, which showed "not responding". This preparation now reads one
  file at a time, with a pause; browser requests are still fast, in parallel.
- A DICOM element with an invalid value (common in private tags) dropped the whole image from the Ipê Web metadata
  and filled the log; now only that element is left out.
- **Emphysema**: the noise filter of 0.100.81 depended on scipy, which is not in the installed Ipê ("No module
  named 'scipy'" when saving); it now uses numpy only, with the same result.
- Linux: the system dialog showed "IpÃª" instead of "Ipê".

## 0.100.82 — Fix for "operator torchvision::nms does not exist"
- **torchvision** came in indirectly (nnU-Net → timm) from PyPI, built for another PyTorch, and a `pip install` of the
  extra models could replace the CPU PyTorch; with the pair mismatched, TotalSegmentator (emphysema and everything
  else) and the spinal cord install stopped with *operator torchvision::nms does not exist*.
- PyTorch and torchvision now install **together, from the same index**, and are pinned for later installs.
  **Install the extra models** checks the pair first and, if they do not match, reinstalls both (fixing an
  environment that is already broken). A task that fails for this reason says what to do.

## 0.100.81 — Emphysema: fewer false dots on noisy series
- **Emphysema (%LAA−950)**: on a noisy series (sharp kernel, or tracheal air with a standard deviation above 30 HU)
  Ipê applies a light Gaussian filter (σ 0.8 mm) before the threshold, so noise no longer shows up as "emphysema"
  scattered across the lung. The finding says when this was done; turn it off in Settings ▸ CAD/AI ▸ Emphysema.
- The **Emphysema** button measures on the study's soft-kernel series when the viewport one has a sharp kernel.

## 0.100.80 — Ipê Web: PACS search with Today/Yesterday, exam number and sortable columns
- In the Ipê Web PACS search: **Today** and **Yesterday** buttons (they set the date and search), the **Exam no.**
  field (Study ID; the accession number stays in the Accession field) and the **Accession** and **Exam no.** columns.
- **Sorting**: clicking a column title sorts by it; clicking again reverses (▲/▼).

## 0.100.79 — Prostate MRI: PI-RADS v2.1, automatic volume and separate research models
- **PI-RADS** (button in the viewer and in Ipê Web, on prostate MRI): PSA and date, volume by the ellipsoid (the
  three diameters, or **Take from the rulers**) or by the automatic segmentation, and the **PSA density**; each lesion
  with the zone, the **sectors** (click on the map), size, T2, diffusion, DCE, **ADC from the viewport ROI**,
  extraprostatic extension and the linked image. The **category** follows the PI-RADS v2.1 rule (peripheral zone by
  diffusion, with DCE; transition zone by T2, with diffusion), with warnings when size and score do not match, and
  can be overridden by hand.
- **Outputs**: the painted sector map (study scheme), the **PI-RADS SR** ("Save to study"), the report text and the
  new report template **Multiparametric prostate MRI (PI-RADS)**, with the fields `{pirads_achados}`, `{pirads}` and
  `{prostata_volume}`.
- **Automatic prostate volume** (TotalSegmentator, on the axial T2): volume and extents along the three axes, SEG and
  finding; the volume goes into PI-RADS and gives the PSA density.
- **Research models, optional and outside Ipê**: prostate zones (MONAI/Prostate158) and suggested lesions (PI-CAI,
  CC BY-NC-SA 4.0 weights). Nothing ships with the installer: the program shows the license, the person accepts
  "research and teaching use, non-clinical, non-commercial" and only then downloads (the PI-CAI weights are checked by
  SHA-256). Suggestions come in as lesions to be checked, and everything is marked **"research model — not for
  diagnosis"** (screen, SEG, SR and report). Settings ▸ CAD/AI ▸ Research models.

## 0.100.78 — Mammography: four quadrant areas, sync off, SR without review and sending to the PACS
- **Quadrant zoom with four areas** (desktop Ipê and Ipê Web): posterior and superior → anterior and superior →
  posterior and inferior → anterior and inferior → whole breast (Q key; Shift+Q goes back). The quadrant moves in all
  viewports together by default; the **Quadrant together** button on the mammography bar turns it off during the exam.
- **In mammography, all synchronizations are off by default** (zoom and pan, window and scrolling), in desktop Ipê
  and Ipê Web, and are kept separately from other modalities. Anyone who had turned on mammography scroll sync is
  set back to off once.
- **Density and vascular calcifications without review** (optional): an incoming mammogram is measured and the SR,
  the marked images and the summary are saved right away, marked as not reviewed. When opening the exam you can still
  confirm or correct: the SR is redone.
- **Sending to the PACS**: the chosen nodes receive the SR, the marked images and the summary once saved (without
  review or after confirming). Settings ▸ CAD/AI ▸ Density and calcifications, and Administration ▸ AI automations in
  Ipê Web.

## 0.100.77 — Ipê Web: quadrant zoom in mammography
- **Quadrant zoom in Ipê Web mammography**, as in desktop Ipê: **Quadrant zoom** button on the mammography bar or the
  **Q** key (**Shift+Q** goes back). Posterior and superior → posterior and inferior → whole breast, in all viewports
  of the stage together, each on its own side: the chest wall stays on its edge and the breasts stay mirrored.
  Scrolled tomosynthesis keeps the quadrant; the second screen follows; changing stage returns to the whole breast.

## 0.100.76 — Ipê website with videos per task; more translated screens
- **Ipê website** (GitHub Pages: <https://filipebarra.github.io/ipe/>), in English, Portuguese and Spanish,
  organized by everyday task — read a study, mammography, breast MRI, PET/CT, AI, reports and diagrams, teaching with
  cases, server and Ipê Web. Each task has a short video recorded in Ipê itself (anonymized example studies), the steps
  and where each thing is. The "How to build a course with cases" tutorial is in the three languages. The site is
  generated from `site/conteudo.py` and published automatically on every change.
- **Translations**: in English and Spanish, form labels (for example, the Organize list window), dialog buttons with
  their own text (Save, Delete diagram…), the Database column headers and the mammography "stage:" now show
  translated.

## 0.100.75 — Ipê Web: marks on mammography, X-ray and ultrasound show up again
- **Saved marks reappear** in Ipê Web on images without a frame of reference (mammography, X-ray, ultrasound):
  arrows, texts and measurements made in desktop Ipê or in Ipê Web itself were saved but did not come back on screen
  when the exam was reopened.
- **Mammography**: in the mammography hanging (which puts images from several series in one viewport), marks are now
  fetched by the real series of the images.
- **Case package**: as a result, marks on mammography cases show up on "Show the result".

## 0.100.74 — Guide diagrams separated from the report: Diagram button in the viewer and templates in Settings
- **Diagram button in the viewer** (desktop Ipê and Ipê Web): opens the *Exam diagrams* — new, draw, delete and
  **Save to the exam** (saving again replaces what was there). The diagram belongs to the exam and needs no report.
- **In the report, just include**: the **Diagrams in the report** checkbox (like key images) puts the legend in the
  text, the figures in the PDF and, on signing, the diagrams in the DICOM SR. Without it the report carries no
  diagram. The drawing strip left the report window.
- **Templates in settings**: **Settings ▸ Diagrams ▸ Diagram templates** in desktop Ipê and **Administration ▸
  Diagram templates** in Ipê Web (new from an image, blank, edit, copy, hide, restore, delete). The template picker
  is now only for choosing.
- If you already had diagrams from 0.100.72 and 0.100.73: they stay in the exam, but go into the report only with
  the checkbox checked.

## 0.100.73 — Guide diagrams: save to the exam without a report, and register or change templates (desktop and Web)
- **Save to the exam**: in the diagrams strip (desktop Ipê and Ipê Web), saves at once the figures (series "Esquemas
  do laudo") and an SR of the diagrams alone, without signing or saving the report — like the segmentation table and
  the density summary. Saving again replaces what was there; on signing, the report SR carries the diagrams.
- **Templates in Ipê Web too**: whoever may configure uploads an image (**New template from an image…**) or starts
  from an empty sheet (**New blank template…**), in the browser or in desktop Ipê.
- **Change existing templates**: **Edit template…** opens the template with the drawing tools — what you draw becomes
  part of it in every exam — and changes its name and group. **Save as a copy** makes a new template; Ipê's own
  templates can be **hidden** or **restored to the original** (the original drawing is never lost); your own can be
  deleted.

## 0.100.72 — Guide diagrams in the report (face, body, thyroid, breasts, prostate), in Ipê and Ipê Web
- **Guide diagrams**: in the report window (and in the Ipê Web report), **New diagram…** opens a base drawing to mark
  the findings: face (front and profiles), body (front and back), thyroid with cervical levels, breasts and the
  prostate sector map. They are Ipê's own drawings; whoever may configure can register their own from an image.
- **Tools**: numbered point, ellipse, arrow, freehand, text, move, delete and undo, in six colours. In Ipê Web they
  work with mouse, finger or pen.
- **Prostate**: a click paints the sector with the category (PI-RADS 1 to 5); the 41 sectors of PI-RADS v2.1.
- **Linked to the report and to the images**: each numbered mark has its description; **Insert the legend into the
  report** (and the `{esquemas}` template field) takes the list to the text. **Link to the open image** ties the mark
  to the image in the viewer, which becomes a key image.
- **Where it goes**: the figure goes into the report PDF; on signing, it goes to the exam as a DICOM image (series
  "Esquemas do laudo") and is cited in the DICOM SR, with each mark's position and linked image. With a diagram the SR
  becomes an Enhanced SR (Basic Text SR does not allow coordinates); without one, nothing changes.

## 0.100.71 — Ipê Web: Administration (users, DICOM nodes, DICOM printers, AI automations)
- For **administrators**, the Ipê Web exam list gains the **Administration…** button, with five tabs:
  - **Users**: create, edit, enable/disable, reset password and delete; **Roles and permissions…** with the table of
    what each role may do. Same rules as desktop Ipê (password of 6+ characters; one active administrator always
    remains; nobody deletes themselves). Disabled, deleted or password-reset users lose their open sessions at once.
  - **DICOM nodes** (DIMSE and DICOMweb) with **Test network**, and the **identities** (calling AE). Password, token
    and secret never come back to the browser: an empty field keeps what was stored.
  - **DICOM printers**, with **Test connection**; renaming follows the print destinations.
  - **AI automations**: the tools of Preferences ▸ CAD/AI — what runs by itself on arrival, on which exams and series,
    and where the result goes.
  - **Access log**, with filters.
- **Temporary password in Ipê Web**: whoever signs in with the password given by the administrator must change it
  before anything else (previously only desktop Ipê asked). **Change my password…** is in Administration ▸ Users.
- Every change goes to the access log with the name of who made it.

## 0.100.70 — Ipê Web: dragging a series thumbnail is no longer "attach"
- In Ipê Web, dragging a series thumbnail onto the viewer showed "Drop to attach to the study" and could attach the
  thumbnail itself. The browser puts the thumbnail image in the drag, and Ipê took it for a file from the computer.
  Now only what comes from outside the page is an attachment; the series goes to the viewport.

## 0.100.69 — Research: batch density and calcifications for the mammograms of a list
- **Network ▸ Batch density and calcifications (spreadsheet)…**: from a spreadsheet (.xlsx or .csv) with the patient
  ID and the mammogram date, Ipê finds each exam (in its database or in the PACS), downloads it, measures density (NYU
  network) and vascular calcifications (SCU-Net) and saves a spreadsheet with the original columns and Ipê's beside
  them: density category and probabilities; grade, area (worst breast, per breast and per view) and the estimated
  scales (CSBI, Margolies, Loberant, BAC-SS); implant; warnings; Study UID and accession.
- Checks the birth date (optional), deletes from Ipê what it downloaded only for the batch (what was already there is
  never deleted), can stop and resume, retries the failures, and has "how many rows now" to test with a few.
- These are the automatic measurements, unconfirmed: check a sample before analysing.

## 0.100.68 — Print jobs and film dashboard in Ipê Web
- **"Print jobs…" button in the Ipê Web exam list**, for **administrators and technologists**: desktop Ipê's Print jobs
  tab, served by the server.
  - The list of what arrived through the DICOM printer, what was composed, and films that came inside the exam, with
    search, filter (received, composed, sent, held) and auto-refresh.
  - The **sheet** beside it (◀ ▶, Enlarge), the job details and the **sending history**.
  - **Identify patient…** with header **OCR** (read on the server); once confirmed, the film follows its rule.
  - **Send to…** any **destination registered on the server** (no sharing needed), with a sheet template;
    **Reprint…**, **Merge as pages**, **Delete** and **Held…** with **Release**.
  - **Dashboard** tab: the cards, films per month, by modality and by creator, the list and **Export CSV**.
  - Print settings stay in desktop Ipê. Everything done from the browser goes to the access log.
- **Sturdier server**: each browser request that needed the main thread (film, printing, AI) left a Qt object behind;
  with many of them the server could crash or hang while writing a sheet to PDF. Fixed (found by this version's tests).

## 0.100.67 — Structures: scissors, one-click outlining, seeds; pharmacokinetics (Tofts, Ktrans)
- **Structures panel, new "More tools" tab** (Undo/Redo serve both tabs):
  - **Scissors**: draw a shape (freehand, rectangle or ellipse) and the structure is cut by it — erase inside, erase
    outside or fill —, on the slice or through all slices, in any plane.
  - **Level tracing**: click and drag over the lesion; the region bounded by the line of the same intensity as the
    point is added (bright or dark lesion), following the mouse.
  - **From the longest diameter**: draw the longest diameter and get the 3D outline in a new structure, with longest
    diameter, short axis and volume; **Adjust** redoes the outline at once, and a warning shows when contrast is poor.
  - **Hollow (shell)** inwards, outwards or half each side; **Smooth** (median, opening, closing).
  - **Automatic threshold (Otsu)** and **Fill by range**; **Split islands into structures** (one lesion per row).
  - **Grow from seeds**: strokes on the lesion and strokes on the background; each voxel goes to the seed it connects
    to through the path of least intensity change.
- **Dynamic: Ktrans (Tofts)… button** — **Ktrans**, **ve**, **kep** maps (and **vp** with extended Tofts) and the
  same numbers per ROI in the table and in *Copy values*. Population arterial input (Parker) or an ROI in an artery;
  TR and flip angle read from the exam; assumed tissue T1 (editable). The dialog and the panel **warn** when temporal
  resolution is routine (one phase per minute): Ktrans is then indicative, not absolute.
- The new computations were checked with synthetic data (simulated shapes and curves); on real exams, check the
  outline and read the Tofts warning.

## 0.100.66 — Web management in the page's language; weekdays in the rules
- **DICOM management in Ipê Web**: progress, summaries, each study's details, the queue and the rules' reports now come
  in the page's language (English or Spanish) — the server used to send them in Portuguese only.
- **Rule schedule** (desktop Ipê and Web): days are shown as "Mon to Fri" or "Mon, Wed, Fri" — they used to be
  initials, and the wrong ones.
- Translations: a text with several generic gaps no longer wins over a more specific one.

## 0.100.65 — DICOM management in Ipê Web: the Automatic tab
- **Automatic tab** in the browser's DICOM management (administrators): create, edit, duplicate, turn on/off, delete
  and **run now** the scheduled rules — the same ones as desktop Ipê (kept in the database). The editor has everything
  the window has: modalities and identities, destination, what to send, period, schedule (every N minutes or every
  day at a time, per weekday) and retry on error.
- **Last report** of each rule (completed now, with errors, offline, another Study UID) and **history**.
- The rules run on the server; changes go to the access log, with the user.

## 0.100.64 — Ipê Web: the browser translator no longer touches the page
- The browser offered (or applied by itself) a page translation and replaced Ipê Web's texts with nonsense. The page
  now tells the browser not to translate; Ipê Web's languages remain the program's own.

## 0.100.63 — DICOM management in Ipê Web (administrators)
- **DICOM management… in the Ipê Web study list**, administrators only: check that the modalities' studies are in the
  PACS (per study and per series) and send what is missing or the whole study, to the PACS or another destination —
  the same routine as the desktop Ipê window.
- **Runs on the server**: the server talks to the modalities and the PACS (with its AE or the chosen identity); the
  check and the sending continue with the page closed. All the server's DIMSE nodes are shown, with no need to share
  them with the clients. **Test** (C-ECHO) on each node.
- Send queue, re-check after sending, "only those with a problem" filter, CSV and access log with the user.

## 0.100.62 — HTTPS server: Ipê Web no longer disappears; http:// leads to https://
- **Server with a certificate (HTTPS)**: a connection that opened and said nothing (the browser pre-opening
  connections, a phone that went to sleep) stalled the whole server until it was closed — Ipê Web and the clients
  stopped being served and only came back after a restart. The HTTPS handshake now runs per connection, with a 20 s
  deadline.
- **http:// on the HTTPS server**: instead of failing, the browser is sent to https:// at the same address.

## 0.100.61 — opening time of desktop Ipê in client mode in the server log
- In client mode, each "Abertura (…)" line of desktop Ipê (first image, by stage — including the wait for the server —
  and what arrives later) also goes to the server log, as "Abertura cliente (…) | user@computer | version". Versions
  and computers can be compared without going to the client machine.

## 0.100.60 — tomosynthesis opens fast; automatic calcifications; series placed from outside in the dynamic (Web)
- **Opening mammography with tomosynthesis**: each slice re-read the whole file header and decoded while holding the
  program; the header and slice locations are now read once and decoding runs in parallel (in the test: from ~8 s to
  ~1.5 s to the first image; scrolling slices is lighter too).
- **Automatic vascular calcifications**: the measurement on arrival and in the database check failed on every image
  (internal error); fixed, and the mammograms in the database are checked again on the next start.
- **Ipê Web, dynamic**: a series placed in a frame from the series list (not from the frame label) now follows by
  patient position — it used to follow the slice number and got lost when scrolling.
- No "thumbnail failed" warning for series without images (SR).
- **Ipê Web: opening time in the server log** — the "Abertura web (…)" line (first image, by stage, and everything
  available, with network and decoding), like desktop Ipê's "Abertura (…)"; only modality, counts and times.
- **Client mode**: re-saving the density and calcification SR no longer duplicates the series on the server.

## 0.100.59 — Ipê Web: series in another plane in the dynamic view
- A series in another plane (sagittal, coronal) in a dynamic frame no longer jumps back to the middle when you scroll
  the dynamic after clicking with **Reference lines**: it does not follow scrolling (nor drives the dynamic); it moves
  to the point only on the click.

## 0.100.58 — Ipê Web: dynamic with chosen series, layout and frames; the correlation point
- **Breast dynamic**: **Series…** picks the series used in the analysis (or **Detect automatically**); when the
  server cannot find the phases, the list opens for you to check them.
- Dynamic **layout** (1 × 1 to 3 × 3) and, in each frame, **any phase, subtraction, map or study series** (a series
  outside the dynamic follows by patient position).
- **Subtraction with ◂ ▸** in the frame itself, as in desktop Ipê (the fourth default frame is already the
  subtraction).
- **Correlation**: clicking with **Reference lines** marks the point with a cross in every frame that passes through
  it (like Shift in desktop Ipê); **Esc** clears it.

## 0.100.57 — Automatic density and calcifications, confirm on open, and SR
- Every **mammogram that arrives** (network, PACS, import, upload to the server) has its **density** and **vascular
  calcifications** measured automatically in the background (AI tasks). Nothing is confirmed automatically.
- **When the mammogram is opened** (Ipê and Ipê Web), the density window opens to confirm; then the calcifications.
- **With both confirmed**, the study gets an **SR** with everything, the **images with the calcifications marked**
  and a **summary** table.
- **Mammograms already in the database** are checked once, in the background, after this version starts.
- Preferences ▸ CAD/AI ▸ **Density and calcifications (breast)**.

## 0.100.56 — Case pack (the list opens in the browser)
- **Export case pack** (right-click a list): a folder with the full Ipê Web viewer and the anonymized studies, for
  teaching, congresses or colleagues. Opens with **Abrir casos** on Windows, Mac or Linux (nothing to install) or
  copied to any static file website.
- Each case has the **presentation** (clinical history, series, documents) and the **result** — with **Show the
  result**: diagnosis, report/result, biopsy/pathology, teaching notes, the result series and documents and the
  **annotations** (arrows, measurements, ROIs) on the images.
- **Organize list**: new fields **Report / result** (with **Use the study's report**), **Biopsy / pathology** and
  **Result series**.

## 0.100.55 — Vascular calcifications: four scales; attachments and larger panel in Ipê Web
- **Ipê Web: attach PDFs and images to the study** — drag the files onto the open study (as in desktop Ipê) or use
  **Attach PDF or image…** below the series. They become DICOM inside the study on the server, follow the study's
  routing rules and show up right away. The study's PDFs are listed under **Documents** and open in a new tab.
- **Ipê Web: real monitors** — the Monitors panel no longer always shows 3 windows: with the browser's permission
  (Chrome/Edge, on HTTPS or on the server itself) it detects **all** monitors, with each one's resolution and
  orientation, and you choose what goes on each. Without it, choose how many windows (1 to 8).
- **Ipê Web: Link** now also works in a single window — the viewports scroll together (same plane), with the same
  window/level (same modality, not MG) and zoom.
- The **Vascular calcifications** window (desktop and Ipê Web) also shows the published scales, estimated from what
  the network marked: **Margolies** (0–12: vessels + extent + density, per breast), **CSBI** (0–3), **Loberant** (0–3)
  and **BAC-SS** (Nv + Ov + L, on the MLO). Hover to see how each one works. They are estimates — check the images.
  Studies measured before this version: **Measure again** to get the scales.
- The **Vascular calcifications** panel in Ipê Web opened narrow and cut off the previews, the "Marked" grade and the
  buttons. It now opens large (fitting the screen), the previews grow with it, and it can be **resized by dragging the
  bottom-right corner**; the browser remembers the size. The Breast density panel can be resized too.
- The panel's warnings (implant, spot/magnification views, missing views) are translated.

## 0.100.54 — Updates: GitHub rate limit and "the version does not change"
- **"HTTP Error 403: rate limit exceeded"** when checking for a new version: the GitHub API limits requests per
  internet address (in a clinic, every computer shares one). Ipê now finds the version on the release page, which
  has no such limit, and checks the download against the release's new `SHA256SUMS.txt`.
- **"I install another version and the version does not change"**: on start, Ipê warns when the open copy is older
  than the one the installer registered in another folder (a shortcut to another copy) and offers to open the new
  one; or when the installer ran in this folder but could not replace the files. The installer now waits for Ipê to
  close (including the tray one) before replacing files. The log shows the program folder at each start.

## 0.100.53 — Ipê Web on smaller screens
- The viewer's top bar shows what fits and puts the rest in the **»** button at the end of the bar (a menu with the
  buttons that did not fit). Before, on screens narrower than ~1900 pixels, the buttons on the right (Report, Send,
  CAD/AI, Reading mode…) were hidden, reachable only by scrolling the bar sideways.

## 0.100.52 — Vascular calcifications on every image; mammography window in the browser
- **Vascular calcifications** on **every 2D image** of the exam (repeats, other views, spot compression,
  magnification); in the confirmation window (and in Ipê Web) each view scrolls through its images (◀ ▶ or the
  wheel). Spot and magnification views are shown but not counted in the breast area.
- **Ipê Web**: mammograms keep the file's window (one image's window no longer spreads to the others, not even
  through linked windows); a window set on a tomosynthesis slice applies to the other slices of the series.

## 0.100.51 — Breast vascular calcifications
- **Vessels** button in mammography (and **Vascular calcifications** in Ipê Web): the **SCU-Net** network (Emory, MIT
  license, in the package) marks vascular calcifications on the four views; the window shows the views with the
  marks, the area per breast and a provisional grade suggestion; the physician grades (**absent, mild, moderate or
  marked**), confirms and can send the sentence to the report. Everything is saved in the exam, for validation and
  calibration.
- Only elongated segments (≥ 3 mm) count; the implant is found in the image and its edge is left out (exams with an
  implant get no grade suggestion).

## 0.100.50 — Breast density in Ipê Web
- **Breast density** button in the web viewer (exams with mammography): the NYU network measured on the server on
  the four views, the category with the probabilities, **Confirm** and **Confirm and send to the report** (the
  composition in the browser report's BI-RADS) and **Measure again**. The measurement and the confirmation are the
  same as in desktop Ipê (they go into Measured densities and the agreement). Confirming requires the permission to
  write reports.

## 0.100.49 — Printing through the server
- **DICOM printer shared by the server**, like the DICOM nodes: on the server, the printer gets the *Share with
  clients* box. In the client Ipê it appears in the film composer's Print window as *Name (through the server)*; in
  Ipê Web, in the film Output. Sheets leave from the server, with its IP and AE; the client never gets the address
  or the AE.
- Ipê Web now lists only the shared DICOM printers, without the address (before, it listed all of the server's,
  with AE and IP).

## 0.100.48 — Breast density: NYU network only
- After the reviews, density keeps **only the NYU network**: the % area by Otsu and by fuzzy, far from the
  confirmed categories, are no longer measured or shown (exam window, review queue, Measured densities, CSV and
  agreement). Measuring is faster. What was already saved with them stays in the database.
- The per-image table with the mask (*Per image, with the mask…*) and the queue's *See the % area with the mask…*
  button are gone too.

## 0.100.47 — Updates from the server: one package per system
- **The Mac downloaded the Linux package** when checking for a new version on a central server running Linux: the
  server kept a single package per channel and handed it to any computer. Each channel now keeps one package per
  system (Windows, Linux, macOS Apple chip, macOS Intel, from the package name) and each computer only gets its
  own; publishing one does not remove the others. With no package for the system, nothing is downloaded and the
  notice offers GitHub.
- With a server that is still older, the client checks the package name and does not download another system's.
- On the Mac, the `.dmg` from the server installs like the GitHub one (replaces the app and reopens it).
- The *Updates from the central server* window shows what is published for each system.

## 0.100.46 — Measured densities; the NYU network ships in the package
- **Measured densities** (Reports ▸ Breast density: measurements and confirmations…, and in the Density button): one
  row per measured exam, with the NYU network, the % area by Otsu and by fuzzy, the confirmed category, who confirmed
  it and when. Filters by period and status (not confirmed, same as the network, different from the network), each
  method's agreement with the confirmations, double-click to open the exam, and CSV.
- **The NYU network ships in the package** (Windows, Linux and macOS): before, the package did not include the model
  file, and the network did not run ("did not run") unless it was copied by hand. BSD-2 license, with the attribution
  in `modelos/LEIAME.md`.
- Density and the review queue **left the File menu**: they live in the Density button.

## 0.100.45 — Server nodes in the client's PACS window
- **The node shared by the server did not appear in the client** when the first request to the server failed (the
  list stayed empty until switching location). Now the list is requested again every time the PACS window opens,
  the failure is not kept, and the list says why when it is empty (the server shares no node, or did not answer).
- **Server node 1 was mistaken for "All query nodes"** in the client's PACS window. Fixed.
- With a server node chosen, the **As** field disappears: the server queries and retrieves, with its own AE, and the
  exam goes to the server's database (the window says so).
- In the node setup, the *Visible to* tip explains it is for the program's own users; for clients, *Share with
  clients* is what counts.
- **Density**: when the exam cannot be saved (central server on an older version), the measurement still shows,
  with a warning to update the server.

## 0.100.44 — The Density button
- **Density button** on mammography exams (outside the AI list): *Measure in the background* (measures the four
  views and saves them in the exam, without opening a window) and *Measure and review* (shows what was already
  measured or measures now). The **NYU network** comes first, with the probability of each category; the **% area by
  Otsu and by fuzzy** stays below, for now. The network's category comes preselected; you confirm or change it, and
  *Confirm and send to the report* puts the composition in the BI-RADS report. Everything is saved in the exam, with
  who confirmed it and when.
- The review queue uses the measurement already saved in the exam and also shows fuzzy; the answer in the queue
  counts as the exam's confirmation. The CSV gained the fuzzy columns.

## 0.100.43 — Breast density review
- **Review density (exam queue)**: in *File*, on the mammography bar and in the AI button ▸ Density. Build the queue
  by period, and each mammogram opens in the viewer with the program's two suggestions (NYU network and % area). You
  confirm or correct with one key (A–D or 1–4; N = not assessable) and the next exam opens. In part of the exams
  (10%, adjustable) the suggestion only appears after your answer, as a control. Below, each method's agreement with
  you (weighted kappa, exact agreement, dense × non-dense), and the CSV with everything. The review is stored in the
  database, one per exam and reviewer.
- **Density in the AI button list** for mammography exams: measure on the images on screen and the review queue.

## 0.100.42 — Code organization, part three (no change in use)
- **The image viewport and the main window were split too**, with the same function names. `viewport.py` (3,900
  lines) is down to 1,200; the rest went to viewport drawing, mouse and keyboard, menus and mammography.
  `main_window.py` (4,200) is down to 2,900; the rest went to the Prints tab, databases and server, the ultrasound
  automatic film and attached documents. Nothing changes on screen; the test that checks that no function is hidden by
  another now also covers these two.

## 0.100.41 — Code organization, part two (no change in use)
- **The viewer was split into four more files**, with the same function names: MPR and planes (`mpr_aba.py`),
  fusion and PET reading (`fusao_aba.py`), mammography and step protocols (`mamografia_aba.py`), and the AI tools and
  Structures (`ia_aba.py`). `viewer_tab.py` went from 6,600 lines (in 0.100.38) to 3,000. Nothing changes on screen;
  the test that checks that no function is hidden by another with the same name now looks at every part.

## 0.100.40 — Annotation text size on the toolbar; the brush opens Structures
- **Larger or smaller annotation text without going to settings**: in the **Annot.** button's arrow, *Larger text*,
  *Smaller text* (in 10% steps, from 60 to 250%) and *Normal text size*, for the corner text (patient, series, window,
  FOV), in every window. The menu shows the size in use, and the three actions can get keys in the shortcuts.
- **The brush opens the Structures panel by itself**: before, painting without the panel open told you to look for a
  "3D ▸ Structures" menu that did not exist under that name. Now the panel opens on the viewport's series and the
  stroke already paints into a new structure. On a viewport without a slice series (mammography, X-ray), the status
  bar says why it does not paint.

## 0.100.39 — Code organization (no change in use)
- **The viewer toolbar got its own file** (`ui/viewer/barra.py`). `viewer_tab.py` had 6,600 lines; the toolbar, the
  per-modality buttons, the AI button, the mouse buttons and the annotation level (about 1,400 lines) moved there,
  with the same names. Nothing changes on screen; a new test checks that no toolbar method is hidden by another one
  with the same name.

## 0.100.38 — Faster opening and downloading (Ipê, client mode and Ipê Web)
- **Client-mode download ~3× faster** (720 CT slices: from 2.9 s to 0.8 s as measured): the server sends each
  image's database fields along with it, and the client writes the file straight into place and the database in
  batches, without re-reading or writing twice. The **first image** arrives sooner: one sample of every series comes
  in a single request.
- **The connection to the server stays open** between requests (before, a new connection for every call).
- **Server ~4× lighter per image for Ipê Web** (from 220 to 930 images/s as measured): permissions and "who can see
  this study" are kept for a few seconds (a change made on the server applies at once); an image whose transfer copy
  is ready is served without opening the original; series metadata is kept on disk and prepared for recent studies.
- **Small server responses no longer wait**: on an open connection (the browser), every small response waited for
  the network acknowledgement — 40 ms on Linux, up to 200 ms with a Windows client.
- **Opening from the local database**: JPEG-LS and HTJ2K decoded in parallel without blocking the screen (MRI: from
  1.1–1.3 s to 0.4–0.6 s); **mammography** with the views decoded together and nipple alignment ~15× faster (from
  2.2 s to 0.7–0.8 s on two cores).
- **Import ~2× faster** (database writes in batches).

## 0.100.37 — PACS through the server (client and Ipê Web), AI button and diffusion in every MRI
- **Search and download from the PACS through the central server.** On the server, each query node can be marked
  *Share with clients*. The Ipê client now sees that node in the PACS search (and in the priors search) as *Name
  (through the server)*: the server talks to the PACS, with its own AE title and password, and the downloaded study
  goes **into the server's database**, in the requester's database. Progress shows in the client's queue; cancelling
  there cancels on the server.
- **Ipê Web: Search the PACS…** on the exam list, with the same shared nodes: search, **Download** (to the server's
  database), download progress and **Open the exam** when done. Searching requires the query permission;
  downloading, the retrieve permission; everything goes to the access log.
- **AI button in the viewer:** the AI tools leave the toolbar and live in a single list, like the measurements list,
  with the ones that apply to the study; at the end, findings to review, AI tasks and the other AIs. One button per AI
  can be restored at the end of the same list.
- **Diffusion in every MRI:** the Diffusion button appears in any MRI, even when the series description doesn't say
  DWI (it also recognizes RESOLVE, ZOOMit, IVIM, SS-EPI and EP2D).

## 0.100.36 — PostgreSQL is the only database
- **Ipê's database is now always the PostgreSQL bundled with Ipê** (nothing to install). SQLite is gone: on the first
  opening after the upgrade, the old database is moved into PostgreSQL with a progress window (only once; a few
  minutes for a large database), with every table's row count verified. The old file is kept as
  `dicomviewer.sqlite.migrado` in the same folder. This applies to the main database, to the other locations
  (external drive, other folder: each with PostgreSQL inside its own folder) and to the client-mode cache.
- Your own PostgreSQL server is still an option for the main database. The *Database server* window and the command
  line lose the SQLite option; the Copy button (and `--copiar`) copies the database in use to the chosen one.
- The password of Ipê's PostgreSQL is now kept with the data (each folder with its own).
- Fixed: with a space in the data folder path (on macOS the default folder has one, "Application Support") Ipê's
  PostgreSQL did not start.
- Empty values that SQLite accepted in required fields (in databases from old versions) get a default value during
  the migration.

## 0.100.35 — PostgreSQL that comes with Ipê
- **No need to install PostgreSQL separately anymore**: Ipê ships PostgreSQL 16 inside the package (Windows, macOS
  and Linux). In Settings ▸ Database ▸ Database server, the *PostgreSQL that comes with Ipê* option: it starts by
  itself when Ipê or the central server opens, keeps its data in the data folder and stops when the last Ipê program
  closes. It only accepts connections from this computer, with a password created and stored by Ipê. The Copy button
  moves the current database to it. Command line: `ipe banco embutido --copiar`.
- The package is about 35 MB larger.

## 0.100.34 — Main database on PostgreSQL
- The main database can live on a **PostgreSQL** server (free; Windows, macOS, Linux or cloud), for a central server
  with many workstations or a server in the cloud. **Settings ▸ Database ▸ Database server**: host, port, database,
  user and password (encrypted), test the connection and **copy the current database** from SQLite to it, with each
  table's count checked. SQLite remains the default; the images stay in the data folder.
- Command line: `ipe banco status | postgres … [--copiar] | sqlite`; the `IPE_DATABASE_URL` variable for scripted
  servers.
- The whole test suite now also runs against a real PostgreSQL.

## 0.100.33 — Segment from a box (MedSAM2) could not build the model
- **Segment from a box (MedSAM2)** stopped with "Cannot find primary config 'configs/sam2.1_hiera_t512.yaml'": the
  MedSAM2 package is installed without the model configuration file. Ipê now ships that file and puts it in place
  when it is missing — **no need to reinstall** the extra models. The installation now also checks the model
  configuration, not only that the package exists.

## 0.100.32 — macOS: Mac keys, system links with aliases, self-installing update and package in the release; PET/CT prepared session
- **Mac keys:** shortcuts already worked with ⌘ (Qt swaps them); now the texts too — tooltips, menus and messages
  show ⌘ and ⌥ instead of Ctrl and Alt.
- **Links:** on macOS, `ipe://` and `dicomviewer://` open Ipê (or go to the one already open).
- **Link aliases** (all systems): in Network ▸ External call, other link names that open Ipê, such as `osirix` or
  `horos`. Links in the OsiriX format (`osirix://?methodName=displayStudy&StudyInstanceUID=…`) are understood;
  `downloadURL` is refused.
- **Update on macOS:** Check for updates downloads the `.dmg` for the right architecture (it used to offer the Linux
  package), replaces the application and opens it again. Where it cannot be replaced automatically, the `.dmg`
  opens so you can replace it by hand.
- The macOS packages (Apple silicon and Intel) are now built together with the release.
- **PET/CT — prepared session:** together with the tumour burden (on arrival or with the Burden button) the liver
  and mediastinum references (PERCIST/Deauville) and the registration with the previous PET/CT are stored; the
  prepared study opens in PET Reading. Anything done by hand is not replaced. Options in Settings ▸ CAD/AI.
- Registration between studies: a volume too small for the first resolution no longer breaks the registration.

## 0.100.31 — macOS: checking for updates (and all HTTPS) works again
- In the macOS package, **Check for updates** failed with "certificate verify failed": the program could not find
  the certificate authorities. The same applied to downloading AI models, DICOMweb over HTTPS and the AI report.
  Where the system does not provide the certificates, Ipê now uses Mozilla's list (certifi). Windows is unchanged.

## 0.100.30 — macOS: clicking the menu bar icon no longer closes the program
- On macOS 27, clicking the Ipê icon in the menu bar (next to the clock) closed the program — a Qt defect with that
  system. On the Mac, Ipê no longer adds that icon: the Dock does the same job. Windows and Linux are unchanged.

## 0.100.29 — The program no longer closes by itself on an unusual compressed file
- When opening a study, Ipê could **close by itself** (seen on macOS): the GDCM decoder ends the whole process when
  the DICOM header does not match the compressed image (rows, columns, colour). GDCM was removed; JPEG, JPEG 2000
  and JPEG-LS are handled by pylibjpeg, CharLS and Pillow, which return an error the program handles — the faulty
  image shows as an error and the rest of the study opens. Applies to Windows, Linux and macOS.
- In the installed program, the last message of a library before a crash also goes to `queda.log`.

## 0.100.28 — macOS: the keyboard reaches the program
- In the macOS test package typing did not work (for example, the server address): the app was flagged as
  "background only", with no Dock icon. Fixed; Ipê now shows in the Dock and receives the keyboard.

## 0.100.27 — AI installation in a window, with progress and errors
- **Install segmentation** and **Install the extra models** run in an Ipê window: current step, elapsed time, the
  whole output with errors in red and, at the end, a verified verdict (installed, with errors, or not installed).
  Copy all, Save and a record in `instalacao_ia.log`. It does not block the program.
- When the program closes by itself because of a library error, a trace is left in `queda.log`, in the logs folder.

## 0.100.26 — Spinal cord and canal: area and compression per level (TotalSpineSeg)
- **Spinal cord** button on spine MRI: segments the cord, canal, discs and vertebrae and measures at each disc, in
  the plane perpendicular to the cord, the area, AP, transverse, compression ratio, canal, MSCC and MCC. Each level
  is a finding to review, with a sentence for the report. Also in the browser AI tab.
- It is an extra model (TotalSpineSeg), installed in its own environment so TotalSegmentator is not touched:
  Settings ▸ CAD/AI ▸ Install the extra models. It needs about 8 GB of free memory.

## 0.100.25 — White matter lesions on FLAIR (FLAMeS)
- **WM lesions** button on head MRI: marks the hyperintense lesions on FLAIR and gives the count, total volume and
  count per region (periventricular, juxtacortical, infratentorial, deep), compared with the previous study. A
  finding to review, a sentence for the report and the lesions coloured by region. Also in the browser AI tab.
- It is an extra model (FLAMeS, 2.4 GB): install it in Settings ▸ CAD/AI ▸ Install the extra models.
- BraTS and autoPET: the mask now shows in the study right after the run, without reopening it.

## 0.100.24 — macOS: test package
- First Ipê package for **macOS** (Ipe.app in a .dmg, for Apple silicon and for Intel), built separately and not in
  the release yet. Not signed by Apple: on first launch, right-click ▸ Open.
- On the Mac, the segmentation installer opens in Terminal and uses the Application Support folder.

## 0.100.23 — Synthetic 1 mm T1 (SynthSR)
- **Indices ▸ Create a synthetic 1 mm T1 from this series (AI, SynthSR)…**: a 2D head series (any contrast and
  thickness) becomes an isotropic 1 mm T1 series in the same patient position, for MPR, guided measurements (MRPI)
  and the automatic indices in studies without a 3D T1. Also in the browser AI tab and in Settings ▸ CAD/AI.
- It is a **synthetic image**: meant for measuring anatomy, not for looking for lesions (the program warns and
  writes it in the header). It stays on this computer only.
- No TensorFlow: the SynthSR network was rewritten in PyTorch and reads the original weights (53 MB, downloaded once).

## 0.100.22 — Linux: installing segmentation on an older system
- The segmentation installer looks for **Python 3.10 or newer** (Ubuntu 20.04 ships 3.8, and pip could not find
  TotalSegmentator); if there is none, it downloads its own Python without touching the system one. An environment
  built with an old Python is rebuilt.
- In the Linux package, the **installer terminal did not open** (gnome-terminal: "undefined symbol"): external
  programs no longer inherit Ipê's libraries.

## 0.100.21 — Browser: reference line and dragging between windows
- With linked windows, the slice of one window shows in the others as a (dashed) **reference line**, on viewports of
  another plane of the same study.
- **Drag a series** from one window's strip and drop it on a viewport of another window, even from another study.

## 0.100.20 — Browser: list with quick filters and preview; linked windows
- **List**: one-click filters (period, modality, report and AI status), AI and report badges on each study, and a
  **preview** of the selected study on the right (series, AI, report, priors) before opening it.
- **Linked windows**: scrolling, window/level and zoom in one viewer window follow in the others (in the prior
  study, by the same millimetres).

## 0.100.19 — Browser: user-chosen appearance, reading mode and monitor setup
- **Appearance**: series on the left, at the bottom or at the top; buttons at the top or in a left column; **reading
  mode** (images only, F key). The right panel starts collapsed. Saved in the browser.
- **Monitors**: a setup saved in the browser, as in Ipê — the order of the windows, what each one shows (the study or
  the prior study), and each one's layout and monitor.

## 0.100.18 — Browser: multiple windows (one per monitor), phone and tablet
- **Viewer windows**: the list in one window and studies in 1, 2 or 3 separate windows, one per monitor, for any study.
  The windows stay open waiting for the next study and remember their position; in mammography the 2nd window is the
  protocol's second screen.
- **Phone and tablet**: list as cards, one image at a time, panels as drawers, scrolling toolbar; one finger does the
  toolbar function (scroll slices), two fingers zoom and pan.
- **Login on phones**: after signing in it went back to the login page. The session now lives in the tab (it survives
  the reloads phones do on their own), the keyboard no longer capitalises the user name, and an image-engine failure no
  longer blocks sign-in. Browser errors now go to the server log.

## 0.100.17 — Mammography in the browser: the same zoom across the stack
- When scrolling to another image of the view (another 2D, the tomo), the zoom did not follow, and scrolling back did
  not restore the opening zoom. The browser was not reading the mammography pixel size (ImagerPixelSpacing; functional
  groups in tomo) and re-measured the framing at every change, accumulating error. The server now provides the pixel
  size and the step's opening framing (or your manual zoom) is applied to every image, as if they were stacked.
- GitHub publishing: actions updated (Node 24) and the build only starts once the new code has arrived.

## 0.100.16 — Browser: review AI findings
- **Findings to review** in the browser's AI tab (emphysema, nodules, Genant, calcium, aorta, PET tumour burden, body
  composition): Go to, Confirm, Correct the numbers, Discard, Back to suggested and **Send to report** (only confirmed
  and corrected ones). The same list as in Ipê; it needs the permission to write reports.
- "Go to" and the browser's reference lines find the right slice even while the series is still arriving.

## 0.100.15 — Browser: Close, the search comes back, AI in the same session
- With a study open, the top-corner button is **Close**; on the list it is still **Sign out**.
- **The search comes back**: closing the study returns to the list with the search and filters you had, with the
  study you had open highlighted.
- **AI in the same session**: when an AI task finishes, the new series join the strip and the SEG joins the menu (and
  is shown if none was chosen), without closing and reopening the study.

## 0.100.14 — AI visible in the browser; AI badge on thumbnails
- **Browser:** the **spine levels** and **lymph node levels** requested from the AI tab did not show (the overlay said
  "No CAD/AI in this study"). The names now appear on any series and plane, MPR included, as in Ipê, as soon as the
  task finishes.
- **Browser overlay:** a **CAD/AI (findings, segmentations, levels)** item turns only the AI on and off, remembered
  from one study to the next.
- **AI badge** on series thumbnails (Ipê and browser): on series that are an AI result or were analysed by one, with
  the tools in the tooltip.

## 0.100.13 — Installing segmentation: downloaded Python and language
- **The segmentation installer failed** with "os error 448 (untrusted mount point)" on some Windows machines: uv
  creates a folder shortcut to the Python 3.12 it downloads, and Windows blocks that shortcut. The environment is now
  created straight from the real Python (the shortcut is removed); a Python already downloaded is reused.
- The installer speaks **Ipê's language** (English, Spanish or Portuguese), and the "Install segmentation" question
  and other messages built from parts are now translated.
- The Windows package was missing some AI tools (emphysema, Genant, aorta…) that are imported by name, so the web AI
  tab came up empty with an error. They are all included now, and one faulty tool no longer breaks the list.

## 0.100.12 — Web viewer: AI tab
- Browser CAD/AI is now the **AI** tab of the right panel, like the film tab: every Ipê AI tool (those suitable for
  the study first, the others with the reason), the series for each (the suggested one or the active viewport's) and
  **Run**; at the top of the tab, the study's tasks with progress and **Cancel**. The toolbar button and **AI** in the
  footer open the tab.

## 0.100.11 — Web viewer: build the film and print
- **Film** tab in the browser: adjusted viewports (window, zoom, pan, rotation) go into the film (the viewport, all
  or the series every N); the preview is drawn by the server with Ipê's composer code; edit, reorder and remove
  cells; grid, paper, landscape, texts, header, anonymize.
- **Print**: download the PDF, print on the browser user's computer, on the server's printers, on DICOM printers and
  on Ipê's print destinations. Counts in the films panel. Only with print permission.
- The headless server (`ipe server`) now uses Qt widgets (offscreen) to draw the sheets.

## 0.100.10 — Web viewer: CAD/AI from the browser
- **CAD/AI in this exam** in the browser: Ipê's AI tools that fit the exam, with the suggested series (or the
  viewport's), running in the server's AI queue. **AI** in the footer shows the exam's tasks (requested and
  automatic) with step and time, and cancels yours; when done, **Reload the exam** brings the new series.
- New permission **Request CAD/AI manually** (by default: administrator and physician).

## 0.100.9 — Web viewer: send to a DICOM destination
- **Send to a DICOM destination** from the browser: the exam, the checked series or the active viewport's image, to
  the server's nodes, through the server's send queue (the same as Ipê's). Optionally along with the measurements
  (GSPS) and key images (KO). **Sends** in the footer shows progress and cancels. Only for users with send
  permission.

## 0.100.8 — PET by edge (gradient); resume the session; motion in the web dynamic
- **PET: edge by gradient (like PET Edge)** in 3D Segment: the contour sits where the signal falls fastest, with
  partial-volume correction using the PET resolution (measured on the lesion itself when it is large; the *PET
  resolution (FWHM)* field for small ones). On test spheres, ±15% of the true volume from 1.3 cm, against twice the
  error or more for 41% in small lesions. Warns when the lesion is near the resolution limit.
- **Resume the session**: Ipê records the open exams and saves the analysis state every 2 minutes; after a crash, it
  offers to reopen what was open, as it was (Settings ▸ Viewer ▸ Analysis state on open: ask, reopen without asking
  or do not reopen).
- **Web viewer — motion correction in the breast dynamic**: translation or rigid, with Ipê's computation done on the
  server; maps, curves, subtractions and the phase that moved come out corrected.

## 0.100.7 — Breast MRI: fibroglandular tissue and background enhancement; end of reading sends to the PACS
- **Fibroglandular and enhancement…** (breast dynamic panel): separates fibroglandular tissue from fat on the
  non-fat-saturated T1 (or on Dixon, or on the pre-contrast) and gives, for each breast, the percentage and the
  volume; with the dynamic open, the median FGT enhancement in the first phase and how much of it enhances more than
  20%. Removes skin, muscle and lateral chest wall, corrects the coil gradient and leaves an implant out. **Copy
  sentences** for the report and **Save the mask (SEG)** to check it. It returns numbers, not a category: the category
  is the physician's call.
- **End of reading** (Settings ▸ Reports): when the report is signed, the key-image KO, the measurement GSPS, the
  report of this signature (PDF and SR) and Ipê's series go to the chosen PACS on their own, through the send queue —
  also when the report is signed in the browser. Hidden series, local copies and other devices' series are not sent.

## 0.100.6 — Linux: .deb package and install.sh in the portable
- **`.deb` package** in the release (`Ipe-<version>-linux-amd64.deb`, package `ipe-viewer`): `sudo apt install ./…deb`
  installs into `/opt/ipe`, with the `ipe-viewer` command, the icon and the **Ipê** entry in the applications menu;
  `apt` pulls in any missing window libraries. `sudo apt remove ipe-viewer` removes it.
- **`install.sh` in the portable**: installs for your user, without administrator rights (program, `ipe-viewer`
  command, menu entry and icon); `--system` installs for all users into `/opt/ipe`; `--uninstall` removes it. Running
  the new version's script updates.
- Installing, updating or removing never touches the studies, the database or the settings. The name is
  `ipe-viewer` because `ipe` is already another program in the distributions.

## 0.100.5 — web viewer: double-click maximizes; "Sign out" goes back to the list
- **Double-click** a viewport to maximize it to 1×1; double-click again to go back to the previous layout, each
  viewport as it was (slice, zoom, window). On a measurement, the double-click still belongs to the measurement.
- **Sign out** (Sair): with a study open, it closes the study and goes back to the study list; on the list, it signs
  out of Ipê Web.
- Closing or reloading the tab with a study open asks for confirmation.

## 0.100.4 — web viewer: magnifier and aligned stack in mammography; report with BI-RADS, PDF/SR and active recall
- **Mammography**: scrolling from the 2D image to the tomosynthesis of the same view keeps the same scale in mm and
  the chest wall in the same place (the tomo has another size and spacing; before, the breast changed size and moved).
  It also holds after a manual zoom.
- **Magnifier**: holding the button shows the image's own pixels magnified around the cursor, with the viewport's
  window; the wheel changes the magnification (1.5× to 8×). Button in the mammography bar and tool in "Zoom and
  magnifier".
- **Report in the browser**: Ipê's **BI-RADS®** form (composition, findings, category per breast, recommendation),
  with the same sentences in the text; **Download PDF** (Ipê's PDF, with header and signature); on signing, the
  **PDF** and the **SR** saved into the study and the **active recall** (BI-RADS 0 and 3), with the patient's open
  requests at the top of the report.
- The windowless server (`ipe server`) starts the Qt GUI offscreen, to generate the PDF.

## 0.100.3 — web viewer: the mouse buttons obey again
- **Fixed**: after changing a button's function (for example, window/level on the right button, which used to be
  zoom), the mouse kept doing the old function — Cornerstone3D added the new button to the old ones and, when a
  function was removed, only released the left button. Now every change leaves exactly the chosen function on each
  button.
- **Fixed**: a measurement started with a single click (the ruler also draws as "click, move, click") left every
  tool frozen until the line was finished. Now clicking another viewport, changing tools or pressing Esc discards the
  half-drawn line, and it is not saved.

## 0.100.2 — web viewer: overlay, reference lines, adjustable PET, breast dynamics and mammography as in Ipê
- **Overlay**: the new icon turns on and off at once the CAD/AI (SR), annotations from another system (GSPS),
  RTSTRUCT contours, corner texts, measurements and reference lines; its arrow picks item by item, and a hidden type
  stays hidden in the next studies. The chosen SEG also shows on slice viewports.
- **Reference lines on slices**: the plane of the active viewport shows as a line on the others (the axial on the
  scout…); with the Reference lines tool, clicking a viewport takes the others to the slice of that point.
- **PET**: SUV window by mouse drag (top and floor, on every viewport of the same PET; Shift on the fusion adjusts
  the CT) and the **arrangement** chosen in the PET tab — the grid and what each viewport shows (CT + PET, CT, PET,
  PET MIP) with its plane —, remembered for the next PET/CT.
- **Breast dynamics**: the **curve under the cursor** (3×3, as in Ipê) and the curve of a point (pixel value); on each
  viewport label, ◂ ▸ change the phase and the menu picks the phase, the **subtraction** of any phase, the
  **landscape** (anatomy added back) and the **color**; the bar picks the color of the map over the phase.
- **Mammography**: each viewport is the stack of its view, as in Ipê — the wheel goes through the 2D images of the
  same breast and view and then through the tomosynthesis slices.
- **Study list**: clicking a column title sorts it (▲/▼), and the choice is remembered.

## 0.100.1 — central server client: the download no longer stops when the exam opens
- **The download stopped right after the exam opened**: when the first images took more than 0.4 s (a real
  network), closing the "Downloading the first images…" notice was read as "Cancel" — only the series already
  arriving finished, and the others stayed with one image. Now only the Cancel button stops the download.
- **Network signal** in the client's status bar: bars (like a phone's), round trip in ms and throughput in Mbit/s
  to the server. Measured when the program opens and on every exam opened (then only the round trip; throughput
  comes from the download itself); click to measure again.
- A failing series is no longer silent: the status bar says how many images are missing and why.
- The client sends to the server's access log its version at login and, at the end of each download, how many
  images arrived, how long it took, what is missing (per series) and the errors — it can be checked from the server.
- Exam comments show again in the client (the server was answering with an error).

## 0.100.0 — central server client: how much of each series arrived, and less data on the network
- The strip shows, for each series, how many images have arrived (*34/120 im*) with a bar, and ⬇ on the one
  arriving; the viewport shows **⬇ 34/120** until its series finishes; the status bar gains the percentage.
- Putting a series in a viewport moves it to the front of the download.
- Two series download at once, and importing into the database runs on a separate thread (the network no longer
  stops while a batch enters the database).
- **Lossless HTJ2K on the network**: the server sends the client a transfer copy (checked pixel by pixel; the
  archive does not change), 2 to 4× less data. Copies for exams from the last 14 days are prepared in the
  background; an image without a ready copy goes as is. The client decodes with OpenJPH (imagecodecs, ~1 ms per CT
  slice). Settings ▸ Network ▸ Central server turns it on and off.
- Sending to a DICOM node that does not accept the file's syntax (HTJ2K, JPEG-LS) now goes uncompressed.
- Web viewer: changing the layout or step while an image was loading sometimes broke the page; and the site bundle
  no longer depends on module order (a load error that showed up when the code changed).
- Measured on a 720-image exam with copies ready: on a ~100 Mbit/s network, 4.9 s with HTJ2K vs 16.8 s without;
  on 1 Gbit/s, 2.6 s vs 2.9 s.

## 0.99.99 — web viewer: the next series start right away
- The browser requests the metadata of all series together (three at a time) instead of one after the other;
  frames are queued in strip order as soon as each series arrives.
- The server reads headers in parallel, keeps the response (reopening is instant; it changes if the file changes)
  and reads the whole exam as soon as the first series is requested.
- The series' transfer copies (HTJ2K) are made by a single worker, queued, and wait while frames are being
  requested — before, each opened series competed for the CPU with the images the browser was waiting for.
- In a test exam with 6 series of 120 slices, the last series started downloading at 12.7 s; now at 3.3 s.

## 0.99.98 — web viewer: mammography with one and two screens, breast dynamic study and report
- **Mammography** in the Ipê protocol: steps (4 views, CC, MLO, current × prior…), the image of each viewport and
  the prior exam by the same rules, breasts back to back (mirrored when needed), the breast framed without the air,
  chest wall against the edge, same zoom and nipples at the same height; double-click enlarges; tomosynthesis per
  viewport.
- **Two screens**: a second window (on the other monitor when the browser allows) with the other half of the step,
  without asking for the password; both change step together.
- **Breast dynamic study**: phases found as in Ipê; kinetic map, SER, MSI, PEI, initial enhancement, subtraction,
  TTP and temporal MIP/mean **computed in the browser** with Ipê's formulas; a map (computed or already saved by
  Ipê) over the phase; **time-intensity curves** of the ROIs with the class, SER and descriptors.
- **Report in the browser**, in the same record as Ipê: suggested template with automatic fields, reviewed AI
  findings at the cursor, draft (with autosave), sign and release, amend, and the "who is reporting" lock (read only
  or take over; the server refuses saving by whoever does not hold the lock).

## 0.99.97 — web viewer: new interface (Weasis style)
- **Icon toolbar** and **each mouse button with its own function, as in Ipê**: clicking an icon with the left,
  middle or right button gives the function to that button; the mark under the icon (left, middle, right) shows
  which. The choice is remembered.
- **Right-click menu** on the image (click and release; click and hold does the button's function): window, zoom,
  rotate and flip, plane, mouse button functions, series, viewports and cine, delete measurements, reset; on a
  measurement, copy the value and delete it.
- **Collapsible panels**: series and prior studies on the left; **Image**, **Measurements**, **DICOM** (tags with a
  filter) and **PET** tabs on the right. Layout from 1×1 to 4×4 on a grid, and a footer with loading and button
  functions.

## 0.99.96 — web viewer: faster loading
- Images go to the browser as **lossless HTJ2K** (a transport copy checked pixel by pixel and cached; the archive does
  not change): 2 to 5 times fewer bytes on a CT, fast decoding and **progressive loading**.
- **Interleaved volume** (MPR appears early and fills in), **browser cache** with revalidation (reopening barely uses
  the network), decoding on all cores but one, and compressed metadata.
- **Loading** (toolbar): MB over the network, MB/s, decoding time per image, format and what came from the cache.

## 0.99.95 — web viewer: drag series and available images
- **Drag a series** from the strip onto any web viewer viewport (clicking still puts it in the active viewport).
- **Available images**: when the exam opens, the browser downloads the series in the background (those in the
  viewports first); each thumbnail shows the percentage ready and the top of the screen the exam total. With memory
  full, preloading stops.

## 0.99.94 — web viewer: PET/CT (phase 4)
- **PET/CT** in the web viewer: fusion (CT + PET), inverted greyscale PET and the PET MIP, with the axial views moving
  together and a click on the MIP taking the slices to the brightest point.
- PET arrives **in SUV using Ipê's calculation** (weight, dose and times); the ROI and pixel value on PET show SUVmax
  and SUVmean as in Ipê.
- **Fusion colour** with Ipê's tables, **opacity** and **top of the SUV window**; below 8% of the top is not painted.
- **Maximum SUV near the cursor** (3 cm sphere) takes the slices to the hottest voxel.
- The exam's **segmentations (SEG)** — tumour burden, organs, AI lesions — as masks with Ipê's colours.

## 0.99.93 — web viewer: measurements in the database and ultrasound calibration (phase 3)
- **Measurements in the web viewer**: ruler, angle, Cobb, elliptical, rectangular and freehand ROI, pixel, arrow and
  calibration. The number is Ipê's (same scale, same ROI rule, same text).
- Measurements are stored **in the server database**, in Ipê's format, with who measured: what is measured in the
  browser shows up in Ipê and vice versa. Moving an end updates it; clicking the measurement and **Delete
  measurement** deletes it.
- **Ultrasound**: distance uses the device's calibrated region (crossing two regions stays in pixels); manual
  **calibration** applies to that image (in other modalities, to the series).
- Fix: when changing the viewport grid, the image could appear tiny in a corner.

## 0.99.92 — web viewer: MPR, oblique and MIP (phase 2)
- Each web viewer viewport gained **A, C, S, MIP and Original** at the top: changes the plane with one click,
  reconstructing the series in the browser.
- **MPR** (toolbar): axial, coronal, sagittal and the rotating MIP, with reference lines — dragging the centre takes
  the planes to the point; rotating a line makes the obliques.
- **Two-point oblique**, **thickness** (3 to 20 mm as MIP, MinIP or average) and **rotating MIP** (button or mouse
  wheel); clicking the MIP takes the slices to the brightest point.
- A series that cannot form a volume stays as slices, with the reason; volumes over 1.5 GB are not built.

## 0.99.91 — web viewer in the central server (phase 1)
- The central server includes a **browser viewer** at `http(s)://server:8043/web/` (Chrome or Edge), with the same
  Ipê login: exam list with search and filters, series strip with thumbnails, 1×1 to 2×3 viewports, window, pan,
  zoom, scrolling, cine, invert and the Ipê window presets. Built with Cornerstone3D.
- Images go as they are stored: JPEG-LS, JPEG 2000 and JPEG are decoded in the browser; mammography uses the
  device window (including GE's sigmoid).
- Nothing about the patient is stored in the browser; each opening goes into the access log. The address is shown
  in Settings ▸ Network ▸ Central server.
- On the server: DICOMweb metadata and frames (WADO-RS), series thumbnail and security headers.

## 0.99.90 — aortic diameter per segment
- **Aorta** (**Aorta** button, or Applications ▸ Aorta) on chest or abdominal CT, with or without contrast:
  TotalSegmentator finds the aorta and the landmarks; the program traces the centreline and measures, in planes
  perpendicular to it every 2 mm, the maximum and the perpendicular diameter. You get the largest of each segment —
  root, ascending, arch, descending thoracic, suprarenal and infrarenal abdominal —, outer wall to outer wall, with
  the reference as text (ACC/AHA 2022; infrarenal aneurysm ≥ 30 mm and the ACR 2013 follow-up). One finding per
  segment and a SEG with one colour per segment.

## 0.99.89 — coronary calcium score (Agatston)
- **Coronary calcium** (**Calcium** button, or Applications ▸ Coronary calcium) on non-contrast CT: TotalSegmentator
  finds the heart, the aorta and the bones; around the heart, calcium ≥ 130 HU is scored by Agatston slice by slice
  (thin slices summed into 3 mm slabs), with the volume and the suggested vessel of each lesion (LM, LAD, LCX, RCA).
  You get the total, **CAC-DRS** and the SCCT/STR category; the aorta and what lies inside the heart (valve, mitral
  annulus) are reported separately. One finding per vessel: correcting or discarding it changes the report total.
  With contrast the score is not measured.
- Fix: the PET tumour-burden SEG (0.99.88) did not show up in the tab by itself after the calculation and was not
  treated as a local series.

## 0.99.88 — PET: tumour burden (FDG, PSMA, DOTA), PET reading and glucose-corrected SUV
- **PET tumour burden** (**Burden** button, or Applications ▸ Tumour burden): TotalSegmentator finds the organs on
  the PET/CT's CT; on the PET, the foci above the tracer threshold (FDG: PERCIST; PSMA: SUV 3; DOTA: liver) outside
  physiologic uptake become findings, with volume, SUVmax/mean/peak, TLG and region (prostate, bone, pelvic or
  extrapelvic node, viscera). Total MTV and TLG; in PSMA, **miTNM** (PROMISE) and each focus's **miPSMA** score.
  Discarding a focus in Findings removes it from the report total. The mask is saved as a SEG over the PET.
- **PET reading** (Fusion button): fusion, PET and rotating MIP in three viewports; clicking a focus on the MIP
  brings the slices to it. **Go to the SUV maximum near the cursor (3 cm)**.
- **Blood glucose** in the PET… window: stored with the exam, checked by Q.Check (warning above 200 mg/dL), and PET
  measurements also show SUVglu (SUV × glucose ÷ 100).

## 0.99.87 — user guide with screenshots of the program
- The PDF guide gained 19 figures: database, viewer with the AI segmentation, toolbar, layout, measurements, MPR,
  3D (PET MIP), mammography and tomosynthesis, breast MR and the dynamic window, priors, PET/CT fusion, spine
  levels, Structures, export and the settings (toolbar, network, central server).
- The screens use real anonymized exams (EXEMPLO patients, shifted dates, new UIDs, no institution or private
  tags) and are redone at every version by the `tools/guia/capturas.py` script, which opens the program without a
  window and photographs each screen. The guide generator accepts `![caption](file.png)`.

## 0.99.86 — faster opening (JPEG-LS) and the opening stopwatch in the log
- JPEG-LS images (Ipê's lossless compression; all stored mammography) are now decoded by pyjpegls (CharLS)
  instead of gdcm: on a 2850×2394 mammogram from your database, 122 ms instead of 280 ms, and viewports decode
  in parallel.
- The decoders and modules the first exam used to load on the spot are loaded a few seconds after the program
  opens.
- Each opening writes to the log the time to the first image, per step (database, toolbar, strip, protocol,
  window, state, image), and when the AI overlays finish loading.
- Release: only `-installer.exe` is published (the transitional `-instalador.exe` copy is gone).

## 0.99.85 — central server client opens the exam while downloading; Linux install
- In client mode, an exam not yet on the computer only opened after all images were downloaded. Now one image of
  each series comes first (the exam opens with the full strip and the hanging protocol builds the viewports) and
  the rest of each series arrives in the background, in batches; the viewports grow by themselves. The status bar
  shows "N of M images", and the log records the exam and the total to download.
- `instalar.sh`: stops with a clear message on old Linux (glibc < 2.34), picks a system Python 3.10+ instead of
  Anaconda's (and rebuilds an old `.venv`) and installs the missing window libraries (`libxcb-cursor0`…).

## 0.99.84 — faster opening of exams with AI SEGs
- The TotalSegmentator organ SEG (thousands of frames) was read on the main screen at every opening and froze the
  exam for seconds. Now the frames come straight from the file bytes (2–5× faster), large SEGs are read in the
  background (the image shows first) and what was already read stays in memory: reopening the exam is instant.
- Drawing only goes through the masks near the current slice, instead of all of them on every paint.
- Measured on a 300-slice exam with a 60-structure SEG: opening from 6.2 s to 1.4 s; reopening from 2.2 s to 0.2 s.

## 0.99.83 — MedSAM2, autoPET and BraTS (extra models)
- **Segment from a box (MedSAM2)**: left-button tool; a box on one slice becomes a 3D mask, propagated up and down,
  and opens in the 3D Segmentation window (volume, axes, SUV, lesion, SEG).
- **autoPET**: FDG-PET lesions by the autoPET II nnU-Net, with the PET/CT's CT resampled onto the PET; MTV, TLG,
  SUVmax and each lesion as a finding.
- **BraTS**: glioma on MRI (post-contrast T1, T1, T2, FLAIR registered and skull-stripped), MONAI SegResNet;
  volumes of enhancing part, necrosis and edema.
- **Settings ▸ CAD/AI ▸ Install the extra models…**: installs the three into the segmentation environment and shows
  what is ready.

## 0.99.82 — structures in 3D and liver lesions by segment
- **3D ▸ Structures**: the exam's segmentations (AI organs, lesions, nodules, SEG/RTSTRUCT) show as colored
  surfaces, together with VR bone or over the MIP, following rotation, cuts and sculpting.
- **Liver lesions** (CT and MRI): open TotalSegmentator tasks `liver_lesions` and `liver_segments`; volume, largest
  axial diameter and segment of each lesion, and tumor burden (% of the liver) overall and per Couinaud segment.
  Each lesion is a reviewable finding.

## 0.99.81 — package names in English
- Release files are now named `Ipe-<version>-installer.exe`, `-windows-portable.zip` and `-linux-portable.tar.gz`.
  The GitHub update finds both the new and the old names.
- Transition: the release also carries `Ipe-<version>-instalador.exe` (the same installer), so versions 0.99.70 to
  0.99.80 can update with one click.
- This release also brings 0.99.79 (a single Ipê per user: clicking the shortcut again brings the open one to the
  front, also from the tray) and 0.99.80 (height and weight for body composition, BMI and Martin 2013 references,
  and a text result for liver steatosis on CT).

## 0.99.80 — weight and height in body composition, and a steatosis result
- Clicking to calculate body composition opens a window with height, weight and sex from the file to check or
  enter (applies to the exam; the file is not changed). In AI findings, **Height and weight…** changes them later
  and recomputes the muscle index, BMI and references without running the AI.
- With weight: BMI and the Martin et al. (J Clin Oncol 2013) references for sarcopenia and myosteatosis.
- Liver attenuation now has a text **result** (Park 2006, Pickhardt 2012): consistent with moderate to severe
  steatosis, possible mild steatosis (liver/spleen < 1.0), no signs, or not classified with contrast. It goes to the
  report and follows corrected numbers.

## 0.99.79 — a single Ipê
- Clicking the shortcut again (or an ipe:// link) no longer opens another copy: the one already open comes to the
  front, also from the tray or the login. The lock is per user and is released by itself if the program crashes.

## 0.99.78 — cleaner right-click menus and AI app icons
- **Viewport**: on top, only what depends on where you clicked (measurement, nodule, BI-RADS finding, symmetry
  axis, DSA); then key image and copy; **Image ▸** (window, color, invert, filter, rotate, mosaic, histogram),
  **Frame ▸** (fuse, reference lines, sync, cine), **Annotations ▸**, **Left button tool ▸** (Navigate, Measure,
  Draw) and the tags; destructive items at the end. Color shows the modality's most used maps plus
  *More colors ▸*. Segmentation left the right-click menu (it stays on the buttons; *Identify vertebrae and discs*
  moved to the Genant button's arrow). DSA only in angiography; symmetry axis on breast MR or with a ROI on the slice.
- **Database**: Open and Report on top; **Organize ▸** (lists, priority, subspecialty, status, comment, database),
  **Documents ▸**, Send/Export, **Tools ▸** (anonymize, fix tags, remove implant only for mammography); Protect
  and Remove protection became a single item.
- **Icons**: each toolbar app has its own drawing (nodules, emphysema, composition, liver, organs, Genant,
  lymph nodes, cephalometry, indices, diffusion), with a gold ✦ on the AI ones.

## 0.99.77 — emphysema per lobe and vertebral fracture (Genant)
- **Emphysema** (chest CT): %LAA−950, Perc15 and volume per lobe, per lung and in total, with the distribution
  (upper, lower or even); warnings for thick slices, sharp kernel, contrast and air calibration (trachea). The
  areas below −950 HU in a SEG shown only on the computed series.
- **Genant** (spine CT or MR): anterior, middle and posterior height of each vertebral body and the height loss
  (wedge, biconcave, crush), with the Genant grade from T4 to L5.
- Both results go to AI findings for review; only what is confirmed goes into the report.

## 0.99.76 — mammography: double-click frames correctly
- In the 1×1 view from double-clicking a view, the breast sat too high with part of it hidden: the zoom and the
  nipple alignment came from the hidden frames. Now the enlarged frame is framed on its own, for its size.

## 0.99.75 — changing the database folder without "WinError 32"
- **Move the files** (Settings ▸ Database ▸ Change the database folder) failed on Windows with *WinError 32* (the
  database held open by background services) and left the program in the new folder with only part of the
  database. Now the move happens at the next start, before the database opens; if something fails, what had
  moved goes back and the program stays in the previous folder.

## 0.99.74 — HTTPS on the internal network, with Ipê's own certificate
- **Central server ▸ Generate a certificate for the internal network…**: Ipê creates an internal CA for the
  service and the server certificate (computer name and IPs), and the server switches to HTTPS.
- **Client ▸ Trust this server's certificate…**: downloads the server's CA, shows the fingerprint to check and then
  requires HTTPS verified with it. **Save the CA (.crt)** to install on Windows (browser and other DICOMweb viewers).
- New dependency: cryptography.

## 0.99.73 — Settings: the group window
- Clicking a group name in the Settings menu (Viewer, Exam protocols, CAD/AI, Reports…) opens a window with all
  the steps of that group in a list on the left. A submenu item still opens only itself, and *All preferences*
  still opens everything.

## 0.99.72 — the installer warns about Visual C++
- Ipê's installer checks for the Microsoft Visual C++ Redistributable (x64) and, if missing, offers to open the
  Microsoft download. Only the segmentation (PyTorch) needs it; Ipê and Python do not. *Install the segmentation*
  gives the same warning before opening.

## 0.99.71 — segmentation installer: PyTorch's Visual C++
- `instalar_segmentacao.bat` checks that PyTorch starts. If it does not (*WinError 126 … shm.dll*, common on
  Windows Server and freshly installed Windows), it downloads and installs the Microsoft Visual C++
  Redistributable and checks again, with a clear message if a restart is still needed.

## 0.99.70 — new version from GitHub, in one click
- On opening (once a day) and under **Help ▸ Check for a new version (GitHub)…**, Ipê looks for the latest
  release. On installed Windows, **Download and install** downloads the installer, checks the SHA-256, closes,
  installs silently and opens the new version. On the portable version and on Linux, it downloads the package and
  opens the folder. *Skip this version*, and **Help ▸ Notify me of new versions** to turn it off.
- A silent update (from GitHub or from the central server) no longer resets the usage mode to "only me" or the
  language to English, and the installer opens the program at the end.

## 0.99.69 — segmentation installer: finds the right Python
- `instalar_segmentacao.bat` checks that each Python **really starts** and answers (before, a broken Python or a
  missing command could pass), lists the computer's Pythons and ignores Windows PYTHONHOME and PYTHONPATH, which
  broke every Python with *No module named 'encodings'*.
- An old environment that does not start is deleted and rebuilt (or renamed, if the folder is locked). If the
  computer's Python does not work, a 3.12 is downloaded just for the segmentation. Clearer network message.

## 0.99.68 — export and import settings
- **Settings ▸ System ▸ Export settings…** and **Import settings…**: one `.ipeconfig` file that goes from Windows
  to Linux and back. It carries the computer and personal settings, protocols, report and sheet templates,
  profiles, SLA, active follow-up, DICOM nodes, AE identities, automation and translations.
- It leaves out what belongs to each computer (database, monitors, login, AE title, token, server/client,
  windows) and folders of the other system. Passwords only if ticked. The same name is updated, not duplicated;
  a copy of the current settings is kept before importing.

## 0.99.67 — the installer asks for the program folder and the database folder
- The Windows installer always asks for the **program folder** and the **database folder** (on an update, already
  filled in with the previous ones). It refuses Program Files (it installs without administrator rights) and a
  database inside the program folder. A database with studies is not swapped for an empty folder: the installer
  warns, and the program moves it, under Settings ▸ Database.
- Command line: `ipe-cli set-data-dir FOLDER`.
- The guide explains how to uninstall (Windows Installed apps) and what stays on the computer.

## 0.99.66 — import RAR, 7z and other archives
- **File ▸ Import archive (ZIP, RAR, 7z)…** and drag-and-drop now also open RAR, 7z, TAR (gz/bz2/xz), ISO and CAB.
  RAR, 7z and ISO use 7-Zip, if installed, or the tar that ships with Windows 10/11; WinRAR also works for RAR.
- Deflate64 ZIPs (what Windows makes for large files) now open through 7-Zip or the Windows tar.
- Split archives (.part1.rar, .7z.001): send all the parts, or just the first. An archive inside an archive also
  opens. Password-protected archives give a message instead of hanging.

## 0.99.65 — abdominal organs and lymph node levels only on the computed series
- The abdominal organ segmentation and the lymph node level map appear only on the series they were computed on
  (and its reconstructions), no longer on every series of the study, where they fell out of place.

## 0.99.64 — breast: fuse by dragging, colour maps, findings by markers
- **Fuse by dragging**: drop the series on the viewport's "Fuse on top" corner; and right-click ▸ Fuse this
  viewport over… for any dynamic map, phase or ADC over another viewport.
- **Colour maps** in the dynamic study: *Time in colour* (colour = time to peak, brightness = enhancement) and
  *Phases in colour* (RGB = early, intermediate, late).
- **BI-RADS findings by markers** in mammography: mark on CC and MLO, table with distance from the nipple,
  quadrant, clock position and third, and send to the BI-RADS report.

## 0.99.63 — study status
- **Status** column in the database: unread, being read, urgent, reviewed — automatic, from access, report and
  priority; change it by hand with a right-click (✎), filters in **Work ▾** and the "mark as reviewed" action in
  the viewer.

## 0.99.62 — complete lung nodule
- **Click nodule** on CT (right-click ▸ Lung nodule here): threshold segmentation, separated from vessels and
  pleura, optional ground glass; the same numbers as the AI; save as a confirmed finding or follow it as a lesion
  right away.
- **The same nodule in the prior study** (by the registration, or probable by lobe and distance): growth of the
  mean diameter and volume and doubling time, in the dialog, the Findings list and the report. The new
  measurement joins the lesion already being followed.

## 0.99.61 — breast round P2
- **Nipple alignment** in mammography: in the same screen row, both breasts with the nipple at the same height
  (protocol option; "by the middle of the breast" as before). Mirrored **zoom and pan** now also on the bar.
- **Invert only the breast**: tissue inverted, background black, in all viewports.
- **★ Slice**: the tomosynthesis slice as a key image, with the slice number; shortcuts to jump to the next
  and previous marked slices.
- **US** and **RM** cells in the mammography protocol: the patient's latest ultrasound and latest MRI
  (`RM:T2` picks the series).
- **Hand-set symmetry axis** for the mirrored ROI (right-click ▸ Symmetry axis).

## 0.99.60 — PET in follow-up (item 7, part 2)
- **SUL** (Janmahasatian lean body mass) stored with every PET measurement; PERCIST uses SULpeak.
- **PET…** button in the lesion panel: **liver** reference (3 cm sphere, by click or automatic from the liver
  segmentation) and **mediastinum**, **PERCIST threshold** (1.5 × liver + 2 SD), warning when the liver is
  not comparable between studies.
- **Deauville / Lugano** criterion: proposed score per lesion and per study (change it with a right-click)
  and the metabolic response.
- **Q.Check** of the PET header, for the study and against the baseline (uptake, weight, dose, unit,
  corrections, reconstruction, scanner).

## 0.99.59 — follow-up across dates (item 7, part 1)
- **Linking by position**: a measurement made in the follow-up study at a lesion's location (within 10 mm,
  carried to the prior by the registration) links to it automatically. Without a registration, or with two
  lesions nearby, it does not link.
- **Follow-up…** in the lesion panel: lesions not yet measured in this study, one by one — **repeat** the
  measurement at the estimated location (prior outline as a shadow), **too small** (5 mm), **absent**, stable
  or progression.
- **Nadir** in the panel (row and ▼ mark) and the four dates (baseline, nadir, prior, current) in the summary.

## 0.99.58 — saved analysis state
- The study **reopens as you left it**: layout, series, slice, window, zoom, pan, rotation, colors, active
  viewport, priors (linked again), panels and the dynamic parameters (back on with one click). Per user, only in
  Ipê (on the central server for all workstations).
- **View ▸ Analysis state**: reopen, back to factory, use the prior study's arrangement or open it alongside as
  it was. Settings ▸ Viewer ▸ Analysis state on opening.

## 0.99.57 — PDFs and images attached to the study
- Drag a **PDF** or an **image** onto the open study, or in the database with a study selected (with
  confirmation), or right-click ▸ **Attach a document…**: it becomes DICOM inside the study (encapsulated PDF
  or secondary capture image) and follows the study's routing rules. Other formats: save as PDF.
- **Study documents…**: the study's PDFs open inside the program.

## 0.99.56 — profiles by group and computer and updates through the server (wave B2 and B1)
- **Profiles by group and computer** (Settings ▸ Users): preferences sent by the server per computer (with
  wildcards), user or access profile; capture from a set-up computer; enforced keys.
- **Updates through the central server** (Settings ▸ Network): publish the installer to the test and stable
  channels, promote and remove; the client warns at sign-in, downloads, checks the SHA-256 and installs in one
  click.

## 0.99.55 — OAuth2/OIDC on DICOMweb nodes and encrypted passwords (wave B3)
- DICOMweb node with **OAuth2**: client credentials, username and password (Keycloak) or a fixed token; the
  token address can be the OIDC issuer (automatic discovery); token renewed on its own and one retry on 401.
- **Encrypted passwords**: the password, token and client secret are stored encrypted in the database (DPAPI
  on Windows; a local key elsewhere); old plain-text ones are encrypted the first time they are read.

## 0.99.54 — AI in the report text (wave B5)
- **AI ▾** button in the report: **local check** (offline; empty field, measurement without a unit,
  laterality, sex × organ, BI-RADS in the text × form, recommendation × category, empty impression), also
  **before signing**; and, with a configured model (Ollama, OpenAI-compatible server or the Anthropic API),
  **refine the text**, **generate the impression** and **point out errors** — always as a suggestion to accept.
- The text goes without the patient's name, ID, accession and birth date; the API key is stored encrypted.

## 0.99.53 — productivity panel (wave B6)
- **Reports ▸ Productivity…**: signed reports by radiologist, modality, subspecialty, priority or day, with
  amendments, median and p90 from arrival to signature and the share on time; pending now; CSV. Users who do
  not manage users see only their own reports.

## 0.99.52 — worklist with priority, subspecialty and deadline (wave B4)
- **Priority**, **Subspecialty**, **Report deadline** and **SLA** columns (left / due in / overdue; on time or
  late once signed), from service rules and changeable by right-click.
- **Work ▾**: unreported by deadline, overdue, due within 2 h, urgent studies and my subspecialties.
- Rules in **Settings ▸ Reports ▸ Priority, subspecialty and deadlines (SLA)…**.

## 0.99.51 — patient recall and mammography filters (wave B8 and B7)
- **Patient recall**: a signed BI-RADS 0 or 3 report creates the request to call the patient back (30 and
  180 days, configurable; 4 and 5 optional). **Reports ▸ Patient recall…**: deadlines, overdue items,
  contacted / scheduled / closed with history, CSV export; the patient leaves the list on her own when a new
  breast study of hers arrives.
- **Breast ▾** in the database: ready-made filters by BI-RADS, density, unreported, screening or diagnostic
  and patient recall; new **BI-RADS**, **Density** and **Patient recall** columns.

## 0.99.50 — liver iron at 3 T and LIC range
- **Liver MRI**: at 3 T, liver R2* is divided by 2.05 for the 1.5 T equivalent (Alam et al., JCMR 2016)
  and then goes into the Wood calibration — the finding shows the equivalent R2* and the LIC. Before, 3 T
  gave no estimate.
- **LIC range** next to the number: 3.2–7 mild, 7–15 moderate, > 15 mg Fe/g severe (reference text).

## 0.99.49 — liver fat and iron on MRI
- **Liver** (abdominal MRI): the liver, spleen and segments come from TotalSegmentator and the measurements
  from the scanner maps — **PDFF** (median, p25–p75 and by segment) and **R2\*** (with T2\*, the spleen and,
  at 1.5 T, the iron estimated by the Wood 2005 calibration); with the in/opposed-phase dual echo, the fat
  signal fraction. Tang 2015 PDFF reference as text.
- The numbers are reviewable findings (Applications ▸ AI findings); automatic in Settings ▸ CAD/AI.

## 0.99.48 — phases left out, curve descriptors, mirrored ROI
- **Dynamic ▸ Parameters**: **phases left out** (the one that moved leaves the maps and curves; not the
  initial, the late, nor two in a row) and **baseline from the mean of the pre phases**; a warning with a
  single pre phase.
- **New maps and columns**: contrast arrival (BAT), washout (steepest descent after the peak), iAUC90 and
  mean enhancement time (MRT).
- **Mirrored ROI** (right click on the ROI): the ROI on the other side, mirrored about the midline plane — on
  the same slice (axial/coronal) or on the other side's slice (sagittal) —, with the lesion / contralateral
  ratio.

## 0.99.47 — body composition at L3 and liver attenuation
- **Composition** (abdominal CT): on the axial slice through the middle of L3, muscle area, muscle density,
  visceral, subcutaneous and intermuscular fat; with the height in the file, the muscle index (Prado 2008
  reference as text). Liver and spleen: mean HU, liver − spleen and liver / spleen, with a warning when
  contrast was given.
- The numbers are reviewable findings (Applications ▸ AI findings); automatic in Settings ▸ CAD/AI.
- The segmentation installer now downloads *trunk_cavities*.

## 0.99.46 — reviewable AI findings; lung nodules
- **AI findings** (Applications ▸ AI findings): each candidate an AI points out is *suggested*, with position,
  numbers, model, series and warnings; you **confirm, correct or dismiss** them one by one, with who and when.
  Only what is confirmed or corrected goes to the report; a confirmed one can become a **tracked lesion**.
  Running again does not redo what was already reviewed.
- **Lung nodules** on CT (Nodules button, or automatic in Settings ▸ CAD/AI): TotalSegmentator
  *lung_nodules* — lobe, longest and mean diameter, volume, mean HU, solid part and proposed consistency.
- The segmentation installer now downloads *lung_nodules* and *total*.

## 0.99.45 — typed zoom, cloned ROI, doubling time, derived series that say where they came from
- **Typed zoom**: double click the "Zoom N%" in the corner ▸ fit, 1:1, 50 to 400% or *Type the zoom…*
  (`150`, `2x`, `1:1`).
- **Clone the ROI** (right click on the ROI): the other viewports receive the ROI at the same position in the
  patient, with the statistics of their image; between different studies, only with the viewports linked or
  registered.
- **Doubling time** in lesion tracking, by volume or by diameter (assuming a sphere); without growth, "not
  applicable".
- **Amber badge** when the viewport is linked in sync to viewports of another Frame of Reference.
- **Slices not shown**: when scrolling fast, how many slices never reached the screen appears for a moment.
- **Exporting different patients in a single package** (CD with viewer or .zip, identified) asks first.
- **Derived series** (reconstructions, maps, captures) write the parameters in *Derivation Description* and
  the source images in *Source Image Sequence*.

## 0.99.44 — editing limits, extended statistics, registration check
- **Structures ▸ Editing limits**: area (everywhere, only inside a structure, only outside the others), an
  intensity range valid for every tool, and **overwrite** (what one gains leaves the others).
- **Extended statistics** of the structure: median, 10th/90th percentiles, skewness, kurtosis, entropy,
  uniformity, largest diameter (Feret), sphericity, elongation and flatness; **Copy the numbers** (one line
  per structure, for the spreadsheet).
- **Check the registration** with the other study: checkerboard, curtain that follows the mouse, difference
  and blend, using the rigid-registration matrix.

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
