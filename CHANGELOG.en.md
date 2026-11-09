# Ipê release history

*The program was called **DicomViewer** up to version 0.99.10. [Back to the README](README.md).
The full history, with every version, is in Portuguese: [CHANGELOG.md](CHANGELOG.md).*

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
