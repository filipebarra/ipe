> **Not for diagnostic use.** This program is a project of its own, with no health-authority registration and no certification as a medical device. The numbers it returns are measurements; interpretation always belongs to the physician.

<!--
Source text of the user guide (English). To build the PDF:  python tools/guia/gerar_guia.py --idioma en
The accepted syntax is at the top of tools/guia/gerar_guia.py. {versao} becomes the code version.
When a screen changes, change this too (and the Portuguese and Spanish versions) and build again.
-->


# First steps

Ipê is a DICOM viewer for Windows and Linux, made for the reporting workstation: it keeps studies in a local database, receives and fetches studies over the DICOM network, checks that the studies from the modalities reached the PACS, shows the images on several monitors and ends in the report, the film or the export.

This guide describes version {versao}. Where the program has a limitation, it is written down — it is more useful to know what the tool does not do than to find out in front of the study.

## Overview: what Ipê has

A map of the program, by subject, with the chapter where each thing is explained.

| Subject | What there is | Where |
|---|---|---|
| Studies | Local database (PostgreSQL), locations (external drive, case bank), import folder/ZIP/RAR/7z/CD, comments, protection, trash, check and rebuild the database, clear the cache | First steps; The database screen; Settings |
| Viewer | Window and presets, measurements and calibration, tile view, key images, syncing frames, MPR/oblique/curved/3D, fusion, multiple monitors, integrity stamps | The viewer; Multiple monitors |
| Mammography | Display protocols, nipple alignment, density (BI-RADS), vascular calcifications and scales, SR, active search, tomosynthesis, silicone implant | Mammography; Breast |
| Breast MRI and other MR | Dynamic (curves, maps, subtraction, Tofts), phase alignment by AI, splitting dynamic series, diffusion (ADC), liver (fat, iron, stiffness), prostate (PI-RADS), MR protocol check | Breast; Nuclear medicine and oncology; Report |
| AI | Abdominal organs, spine levels and transitional vertebra, cervical lymph nodes, cephalometry, skull indices, nodules, emphysema, aorta, coronary calcium, body composition, spinal cord, FDG/PSMA lesions, glioma, FLAIR, synthetic T1, MedSAM2 — automatic on arrival or by hand, queued, with reviewable findings | Nuclear medicine and oncology; Breast; Settings |
| AI output | SEG, tables and color overlay series, per AI or for all, and sending to the DICOM destinations (for PACS that do not show SEG) | What each AI saves in the study |
| Batch | Batch from a spreadsheet (searches the PACS, runs the AIs, sends, prints, anonymizes), exporting the AI results to Excel | DICOM network, PACS and automation; Case lists |
| Lists and teaching | Case lists and smart lists, meeting mode, case package, hiding/anonymization profiles | Case lists |
| Report | Templates, AI findings, AI impression, guide diagrams, attachments (PDF and images), signing and sending to the PACS, worklist with deadline, productivity | Report |
| Film and printing | Film composer, DICOM printing, received prints, film panel | Film and printing |
| Network | DICOM nodes, search/download (C-FIND, C-MOVE, C-GET), sending, automation rules, DICOM management (are the modalities' studies in the PACS?), central server, Ipê client, Ipê Web, HTTPS | DICOM network, PACS and automation; DICOM Management |
| Integration | External call (RIS, ipe:// link, HTTP API), passwordless study link, opening by the Ipê Web address | External call |
| Administration | Users and permissions, profiles, three levels of settings, audit, exporting/importing settings, updating (GitHub and server) | Settings, users and export |

## The two screens

The program has one fixed tab, **Database**, and one tab per open study. Everything starts in the database: the study list, the search, the case lists and the buttons that open the other windows (PACS, Management, prints, report, settings).

- **Open a study**: double-click the row, or the **Open** button.
- **Back to the database**: **Ctrl+B**, or the Database tab.
- **Close a study**: the ✕ on the tab. With the study split across monitors, closing one closes all — half a study open on one monitor is worse than none.
- **Switching tabs does not steal the keyboard**: when you click a study's tab, the keyboard goes to the frame. The arrows move through the mammography steps, not through the tabs.
- **Only one Ipê** (0.99.79): clicking the shortcut again, or opening an ipe:// link, does not open another program. The one already open comes to the front, even when it was hidden in the tray (close to tray) or still at the login. If the program crashed, the next click opens normally.

## Importing studies

**File** menu: **Import folder…** (Ctrl+I), **Import files…** and **Import archive (ZIP, RAR, 7z)…**. You can also drag files, folders or archives onto the window.

> **Archives.** The program opens ZIP and TAR (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz) on its own. RAR, 7z, ISO and CAB it opens with **7-Zip**, if installed (7-zip.org), or with the **tar that already comes with Windows 10/11**; for RAR, an installed WinRAR also works. If neither exists, the program warns you. Archive in parts (.part1.rar, .part2.rar…, or .7z.001, .7z.002…): send all the parts, or only the first, with the others in the same folder. An archive inside another is also opened. A password-protected file does not open: the program warns you, and then you extract it outside and import the folder.

> **Copy or reference?** In Settings ▸ Database ▸ Import, the box *Copy the files to the program's storage* decides whether the DICOM is copied into the program's folder or only referenced where it is. Unchecked, the program never writes to the original file — and never deletes it.

## Opening the study faster (0.100.38)

When opening a study from this computer's database:

- **JPEG-LS** images (the archive's lossless compression) and HTJ2K are decoded **in parallel**, by the processor's several cores, without holding the screen while the series is read ahead. In measurements, a 12-series MR opened in 0.4–0.6 s (before, 1.1–1.3 s).
- In **mammography**, the four views are decoded at the same time, and nipple alignment became about fifteen times faster: 0.7–0.8 s to the first image (before, 2.2 s), on a two-core computer — with more cores, less.
- **Import** (folder, CD, what arrives over the network) writes to the database in batches: about twice as fast.

The log still says, at each opening, where the time went (the line *Opening (…): first image in … s*).

## Where the data lives

Menu **Help ▸ Open data folder** shows where the database (the `postgres` folder), the copied images (Storage), the settings (settings.json) and the logs are. On the command line, `ipe-cli info` prints the same paths.

The program does not run as administrator, and never needs to: everything it writes stays in the user's profile.

### New version from GitHub

On opening (once a day), Ipê checks GitHub for a new version; **Help ▸ Check for a new version (GitHub)…** checks right away, and **Help ▸ Notify me of new versions** turns the notice on and off (the same as the **Do not notify me again** box, which is in the notice itself). When there is a new version, the window shows the number (and the news, in *Show details*) and offers:

- **Download and install** (Windows, installed with the installer): downloads the installer, checks the SHA-256 that GitHub publishes, closes the program, installs without questions and opens the new version. The program folder, the database folder, the language and the usage mode stay as they were.
- **Download** (portable version for Windows and Linux): downloads the package and opens the folder; replacing the program folder is manual (the database and the settings stay outside it).
- **Skip this version**: the automatic notice does not come back for it (the search from the menu still shows it). **Later**: asks again the next day. **See the page**: opens the release in the browser.

The release files have had English names since 0.99.81: `Ipe-<version>-windows-installer.exe` (until 0.100.104, `Ipe-<version>-installer.exe`), `Ipe-<version>-windows-portable.zip` and `Ipe-<version>-linux-portable.tar.gz`. Since 0.99.86 the release no longer carries the copy with the old name (`-instalador.exe`): whoever is still on a version from 0.99.70 to 0.99.80 installs the new one by hand once.

In client mode the central server decides the version (Help ▸ Check for an update on the central server…), and the GitHub notice does not appear. The query sends GitHub only the program name and the version.

**GitHub limit (0.100.54).** Without an account, GitHub accepts few queries per hour from the same internet address — in a clinic, all computers go out through the same one — and answered "HTTP Error 403: rate limit exceeded". Now, when that happens, Ipê finds the new version through the release page itself (which has no such limit) and downloads from there, checking the SHA-256 against the release's `SHA256SUMS.txt` file.

**The version did not change after installing (0.100.54).** Two causes, and Ipê now warns about both on opening:

- *The shortcut points to another copy.* The installer updates the folder where Ipê was installed (normally `%LOCALAPPDATA%\Programs\Ipe`); if the shortcut you use opens another copy (the portable one, an old folder), it stays old. Ipê compares the open version with the one the installer registered and offers to open the new one. Afterwards, change the shortcut (or delete the old copy). The log (`Logs\dicomviewer.log`) shows, at each opening, the version and the program folder.
- *Ipê was open during the installation* (for example, minimized as an icon near the clock, on the computer that serves the studies): the old files stayed in place. Now the installer waits for Ipê to close (up to 30 s, in the automatic update) and, if it stays open, asks you to close it before going on.

### Taking the settings to another computer

**Settings ▸ System ▸ Export settings…** writes an `.ipeconfig` file with what you choose: this computer's settings (window, mouse, printing, export, network), your preferences, the display and mammography protocols, the report and sheet templates, profiles, SLA and active search, the DICOM nodes, the AE identities, automation and your own translations. The file is the same on Windows and Linux: export on one and import on the other.

**Settings ▸ System ▸ Import settings…** opens the file, shows what it has and imports the checked parts. What already exists here with the same name (a node, a rule, a protocol) is updated; the rest stays. Before importing, the current settings are kept in a copy, in `backups_config` in the settings folder (to go back, import the copy). Afterwards, close and reopen the program.

What does **not** go, because it belongs to each computer: the studies and the database folder, the locations, the monitors, the saved login, this computer's AE title and token, the server or client role and the window positions. A folder from the other system (`C:\...` arriving on Linux, `/home/...` arriving on Windows) is not written. The **passwords** of the DICOM nodes and of the report AI only go if you check *Take the passwords*: in that case the file carries them in clear text, so keep it carefully. The service part, the nodes and automation require the permission to configure the computer.

### Installing and uninstalling on Windows

The installer asks for two folders: the **program** folder (suggests the user's `AppData\Local\Programs\Ipe`; it can be another drive, like `D:\Ipe`, but not Program Files, because it installs without administrator) and the **database** folder (suggests the current one; it can be another drive or an external drive, but outside the program folder). In an update both come already filled in with the previous ones. If the current database already has studies and the chosen folder is empty, the installer does not switch and warns you: to take the studies along, use **Settings ▸ Database ▸ Change this computer's database folder…**, which moves the files: with **Move the files**, the database is moved the next time the program opens, before anything else (with the program open Windows does not let the database be touched); if something fails, what had already gone comes back and nothing changes. **Just point** starts using the database that is already in the chosen folder. On the command line: `ipe-cli set-data-dir FOLDER`.

To uninstall: **Windows Settings ▸ Apps ▸ Installed apps ▸ Ipê ▸ Uninstall** (or Control Panel ▸ Programs and Features). The program leaves, with the shortcuts and the ipe:// link. The database, the studies, the reports and the settings stay: they are yours. To delete them too, delete the database folder and the `AppData\Local\DicomViewer` folder after uninstalling.

### Installing on Linux

**From the release packages (0.100.6)** — on GitHub, the releases page has two ways, both without Python:

- **`.deb` package** (Debian, Ubuntu, Mint…): `sudo apt install ./Ipe-<version>-linux-amd64.deb`. It installs in `/opt/ipe`, with the `ipe-viewer` command, the icon and the **Ipê** shortcut in the applications menu; `apt` installs any missing window libraries. Updating is installing the new `.deb`; removing, `sudo apt remove ipe-viewer`.
- **Portable** (`Ipe-<version>-linux-portable.tar.gz`, any distribution): extract and run `Ipe/install.sh`. It installs for your user, without administrator (the program in `~/.local/share/ipe/programa`, the `ipe-viewer` command in `~/.local/bin`, the shortcut in the menu). `install.sh --system` installs for all users in `/opt/ipe` (asks for the `sudo` password); `install.sh --uninstall` removes. You can also just run `Ipe/Ipe`, without installing.

The command is called `ipe-viewer` because `ipe` is already the name of another program (a drawing editor) in the distributions. Installing, updating or removing the program does not touch the studies, the database or the settings (`~/.local/share/DicomViewer` and `~/.config/DicomViewer`).

From the source: in the Ipê folder, `./instalar.sh` and then `./executar.sh`. It needs a Linux with **glibc 2.34 or newer** (Ubuntu 22.04, Debian 12, Fedora 35 or later), because Ipê's Qt has no package for older systems — the script warns and stops. It finds on its own a **system Python 3.10 or newer** (not Anaconda's, which tends to come first in the path and be older), rebuilds the `.venv` environment if it was created with an old Python and installs the window libraries that Ubuntu does not bring (`libxcb-cursor0` and company, with `sudo`). The Linux portable version does not need Python, but also needs those libraries.


### Checking and rebuilding the database (0.100.117)

**Settings ▸ Database ▸ Check and rebuild the database…** (administrator) does what OsiriX/Horos's *Rebuild Database* does, without losing what exists only in Ipê: comments, lists, measurements, key images, reports and AI results are tied to the study by UID and are never deleted.

- **Check** (start here; it changes nothing) shows how many database images lost their file (in Storage and referenced), how many files are in Storage without being in the database, the empty series and studies, patients without a study, series without a thumbnail and empty folders. **Save the report…** writes the list with the paths.
- **Partial rebuild** fixes what the check found: indexes the loose files in Storage, removes from the database the Storage images whose file disappeared, cleans the empty ones, rebuilds the thumbnails and deletes the empty folders. **Referenced** images that are not in place only go if you check the option — an external drive or flash drive that is unplugged works again when plugged in.
- **Full rebuild** rereads the header of every file and updates the index (patient, study, series, images). Beforehand, it writes a copy of the index in the data folder, in `Backups`. In a large database it takes time: you can **Stop** and later **Continue where it stopped**.

On the server, from the command line: `ipe-cli banco conferir`, `ipe-cli banco parcial` (with `--referenciados` to also remove the referenced ones), `ipe-cli banco completa`, `ipe-cli banco continuar` and `ipe-cli banco restaurar-indice <copy>` (puts the index back as it was before the full rebuild). The Ipê client has no rebuild: the server keeps the database.

### Notice of AIs not installed (0.100.121)

On opening, if the computer does not have the AIs installed — the **organ segmentation** (TotalSegmentator) or the **extra models** (MedSAM2, autoPET, BraTS, FLAMeS, spinal cord) —, Ipê says what is missing and offers **Install the segmentation** or **Install the extra models**, or **Later**. The notice comes back every time the program opens, until everything is installed. Check **Do not notify me again** to make it stop; to turn it back on, **Help ▸ Notify me when AIs need installing**. The research models (prostate) and the breast dynamic alignment are optional and are not part of the notice.

### Clearing Ipê's cache (0.100.120)

**Settings ▸ Database ▸ Clear Ipê's cache…** deletes what the program keeps only temporarily and rebuilds by itself. The window shows the size of each item and clears only what is checked:

- **Viewer image memory**: the images already read; they come back when the study is opened.
- **Studies downloaded from the server** (client mode only; comes unchecked): the server keeps everything and the study downloads again on opening. Kept on the computer are the **open** studies, the **protected (locked)** ones and those the server **does not have in full** (the program checks each one with the server before removing it).
- **Forgotten temporary folders**: leftovers from the AIs and the reports from when the program closed in the middle, idle for more than 6 hours.
- **Already downloaded updates**: the installers of old versions.

The database, this computer's studies, the trash, the settings and the AI models are never touched. The server cache limit (Settings ▸ Usage mode ▸ *Local cache*) still applies: this window is for freeing space right away.

## Help

**F1** (outside a study), the **Help** button on the start screen or **Help ▸ User guide (PDF)** open this guide in the computer's PDF reader, **in the program's language** (Portuguese, English or Spanish; without the one for the chosen language, it opens the Portuguese one). **Help ▸ About Ipê…** shows the version. Inside a study F1 belongs to the film (chapter 12).

The figures in this guide are screens of the program itself, redone with each version, with real **anonymized** studies (EXAMPLE patients, shifted dates, no institution). The screens come from the Portuguese interface; on another system (Windows or Linux) the font and the look of the windows change a little; the buttons and menus are the same.

## What the program never does to the original

- Exporting, packaging, anonymizing and fixing tags generate new files; the original stays intact.
- The only function that rewrites a patient file is lossless compression, and only after checking pixel by pixel that the image is identical.
- Deleting a study and deleting a series remove files, and only those inside the program's Storage. A merely referenced file is not touched.
- What the program writes *into* the study (the lesion capture, film in the study, saved reconstructions) enters as a **new series**; the original series do not change.

# The database screen

## Study list

The central table lists the studies of the selected location. Above it: the **Search** field, the **Columns ▾** button (chooses which columns appear) and **Clear filters**. The right-hand panel shows the series of the selected study.

![The database screen with the sample studies (anonymized). On the left, the locations and the case bank; on the right, the series and comments of the chosen study.](banco.png)

Right-click on a study (or on several selected ones), arranged in groups since 0.99.78:

- **Open**, **Open choosing series…** and **Report…** at the top;
- **Organize ▸** case lists, priority, subspecialty, study status, comment and the database (personal or shared);
- **Documents ▸** attach a PDF or image, the study's documents and the history;
- **Send to ▸** a node ▸ *as this program* or *as* one of the registered identities (chapter 9), and **Export…**;
- **Film ▸**, only when the study has key images or a saved film;
- **Tools ▸** **Anonymize a copy of this study…** (exports anonymized or keeps an anonymized copy in the database, chapter 14), **Fix tags…** and, in mammography only, **Delete implant**;
- at the end, **Protect** (or **Remove protection**, if already protected) and **Delete from database…**.

### Collapsing the side panels

The two panels on the sides of the list — **Locations and lists**, on the left, and **Series and comments**, on the right — collapse into a **strip at the edge**, like Weasis panels: the **◂/▸** button in the panel title. Collapsed, what remains is the strip with the name written sideways; one click on it (or on the little arrow) brings the panel back, at the size it had. The study list gets the full width.

The **Lists** button on the bar opens and collapses the left panel, and **View ▸ Show Locations and lists / Show Series and comments** does the same in the menu. Each user has their own state, and the program opens as it was last time.

## Series panel

- Switches between icon and list with the header button; the choice is remembered.
- Right-click on a series: **Hide** (reversible — the series disappears from the list and from the viewer, and the **Hidden** button brings it back) or **Delete** (removes it from the database and the files that are in Storage). The program refuses to delete the last series of a study and any series of a locked study.
- **Send N series to ▸** a node ▸ as… — sends **only the selected series** (Ctrl+click or Shift+click to choose several).
- Still in the right-click menu: mark the selected series as dynamic (works for CT and MR) and split a series that carries all the phases together.
- Captures and series that the program itself saved (the lesion capture, saved maps and reconstructions) appear with a thumbnail, like the others.

## Locations

The **Locations** panel, on the left, switches between different databases (for example, the local database and a central server on the intranet). It collapses, and collapsed it still says which location you are in. One location at a time.

## Case bank

Right below the locations is the **Case bank** tree: folders and lists. Three kinds of list, chosen at creation — Normal, Meeting and Smart (filter). Chapter 7 covers the last two.

Buttons: **+ List**, **+ Folder**, **▶ Meeting mode**. Right-click on the tree opens the same items plus rename, description, move, export and delete.

## Comments and protection

- **Add comment** writes a note on the study, which appears in the list.
- The **lock** protects the study: it does not enter automatic cleanup and cannot be deleted while protected.
- **Study history…** (right-click on the study ▸ Documents) shows who did what on **this** study — opened, downloaded, exported, sent, printed, changed database, deleted image, took over the report — and when the reports were created and signed.

## Buttons of the start screen

| Button | What it opens |
|---|---|
| Import | import a folder, files or ZIP |
| PACS | search and download (Ctrl+Shift+F) — chapter 9 |
| Management | check that the modalities' studies are in the PACS — chapter 10 |
| Open / Send / Export | actions on the selected studies |
| Print | the film composer (Ctrl+P) — chapter 12 |
| Prints | what the modalities sent to print and what was assembled here |
| Report | the report of the selected study — chapter 11 |
| Lists / Meeting | the case bank and meeting mode |
| Hide | hides patient data across the whole program |
| Delete | deletes the selected studies |
| Monitor | the monitor settings (does not open a study) |
| Settings / Users / Help | preferences, profiles and this guide |

# The viewer

Each study opens in a tab with the toolbar on top, the strip of series thumbnails on the left and the frames in the center. At the end of the toolbar is the block of **study applications** (MPR, 3D, Dynamic, Fusion, NM): each one appears only when it serves the open study — by modality, by body region (from BodyPartExamined and the descriptions) and by series type (angio, 3D T1, 3D T2, dynamic, volume). A mammogram has no MPR, 3D, Fusion or NM; a breast MRI shows Dynamic. The **Applications** button lists all of them, including those left out, with the reason — and they run anyway. Right-click on an application: **Automatic**, **Always** or **Never**, for all studies or only for studies of that region. The order, the modes and the region dictionary are in Settings ▸ Viewer ▸ *Toolbar and applications* and Settings ▸ Study protocols ▸ *Body regions* (with a box to test descriptions).

![Portal-phase abdominal CT, with the organs and liver segments from the AI segmentation (TotalSegmentator) overlaid.](visualizador_tc_orgaos.png)

## Mouse

The left-button tool is the one lit on the toolbar. The other buttons, the wheel and the clicks are set in Settings ▸ Viewer ▸ Mouse. By default:

| Gesture | What it does |
|---|---|
| Left, dragging | the tool chosen on the toolbar (by default, window/level) |
| Right, dragging | zoom |
| Right, clicking | frame menu |
| Middle, dragging | move the image (pan) |
| Middle, clicking | fit to window |
| Wheel | scroll through the slices |
| Shift held | the left button becomes the 3D cursor (no click needed: moving the mouse already finds the point in the other frames) |
| Ctrl held | the left button becomes scroll (moves the slices up and down) |

Shift and Ctrl borrow the left button: the tool chosen on the toolbar does not change, and when you release everything goes back to what it was. Which key does what is chosen in Settings ▸ Viewer ▸ Keyboard shortcuts (Shift / Ctrl / Alt / None).

## The tools

The left-button tool is chosen on the toolbar, in the frame's right-click menu — in **Left button tool ▸ Navigate** (what moves the image), **▸ Measure** (what measures) and **▸ Draw** (arrow, text, pencil, brush) — or by clicking the corner that shows the current tool.

![The viewer toolbar. The applications (MPR, 3D, composition, Genant…) appear at the end of the bar only when they serve the open study.](barra_ferramentas.png)

### The right-click menu on the frame (0.99.78)

Arranged to fit at a glance:

- **on top, what depends on where you clicked**: the measurement under the mouse (delete, draft, lesion, reference, mirror, clone, profile), *Lung nodule here* (chest CT), *BI-RADS finding here* and *Find the implant* (mammography), *Symmetry axis* (breast MRI, or when there is an ROI on the slice), *Digital subtraction (DSA)* (angiography only, XA/RF), *Spine numbering*, *4D cardiac*, saving the MPR reconstruction and *Remove the CT table*;
- **Mark key image ★** and **Copy the image**;
- **Image ▸** window (only the presets of the frame's modality), color (the most used for the modality and *More colors ▸* with the others), invert, filter, rotate/flip, slice mosaic, histogram, fit to window and restore;
- **Frame ▸** fuse this frame over another, cut lines, sync group, cine and the list of the series' measurements;
- **Annotations ▸**, **Left button tool ▸** and **DICOM information (tags)…**;
- at the end, set apart, what deletes: **Delete measurements on this slice** and **Delete this image…**.

The AI applications (organs, spine, nodules…) are only in the toolbar buttons and in the **Applications** button. Each application has its own icon on the toolbar, and those that use AI carry a golden ✦ in the corner.

The *key* column below is a suggestion: almost the whole shortcut list comes empty by default, and each key is chosen in Settings ▸ Viewer ▸ Keyboard shortcuts (chapter 14). Among the tools, only zoom by quadrant has a default key (Q).

| Tool | Key | What it is for |
|---|---|---|
| Window / level | W | brightness and contrast |
| Zoom | Z | zoom in and out |
| Pan | P | move the image in the frame |
| Scroll | S | move through the slices |
| Ruler | M | distance in mm |
| Angle / Cobb | A / Shift+C | angle between two lines |
| Elliptical / rectangular / polygonal ROI | E / Shift+E / G | mean, deviation, area |
| Intensity | V | pixel value (HU, SUV, signal) and the dynamic curve |
| Arrow / Text / Pencil | Shift+A / T / B | mark and annotate |
| 3D cursor | X | the same point in the other frames |
| Segment 3D | Shift+V | grows the lesion and measures volume, axes, SUV, TLG |
| Select | — | creates nothing: chooses, moves and edits what is already drawn |
| Magnifier | U | local magnification, while holding the button |
| Zoom by quadrant | Q (default) | goes through the four quadrants at full size |

## Frames, series and layout

- Layout on the toolbar, or the **View ▸ Frame layout** menu (from 1×1 to 4×4). The initial layout is in Settings ▸ System ▸ When opening the program.
- `[` and `]` (suggestion) switch the series of the active frame. Switching sequence keeps the position: the new slice passes through the point that was in view.
- Dragging a thumbnail from the strip onto a frame puts that series there.
- **AI stamp (0.100.14)**: the thumbnail gets a lilac **AI** stamp in the top corner when the series is an AI result (SEG, tables, check images) or was analyzed by one (the series the SEG came from). Hover to see which tools. In the browser, the same stamp appears in the series strip.
- The frame's lower right corner says the plane (clickable), the dynamic phase, the window and the FOV.
- **Annotation text size (0.100.40)**: in the small arrow of the **Annot.** button, *Larger text*, *Smaller text* (in steps of 10%, from 60 to 250%) and *Normal text size* change the corner text (patient, series, window, FOV) in all windows; the menu shows the size in use. The three actions can get a key in Settings ▸ Viewer ▸ Shortcuts. It is the same adjustment as *Text size of the corner information*, in the settings, where the text size of the measurements is also found.
- **Typed zoom**: double-clicking the "Zoom N%" in the corner opens the menu — *Fit to window*, *1 image pixel = 1 screen pixel (1:1)*, 50 to 400% and **Type the zoom…** (accepts `150`, `150%`, `2x`, `1:1` and `2:1`). The number is the same as in the corner: 100% is the image fitted to the frame.
- **Slices not shown**: when scrolling fast (wheel, drag, Shift), the image moves several slices between two screen repaints and the ones in the middle never appear. When that happens, next to the position bar, in amber for a second and a half, "N slice(s) not shown" appears. Going to a slice (click on the bar, double-click on the image number, sync) gives no warning.

![Brain MRI in the display protocol: four series, with one frame's reference lines on the others.](layout_rm_cranio.png)

## Integrity stamps

A strip at the top of the frame warns of what may make the image unfit for reading. Clicking it explains each stamp.

| Stamp | Color | When |
|---|---|---|
| LOSSY COMPRESSION — unfit for the report | red | mammogram compressed with loss (by the Lossy Image Compression attribute or by the file's syntax), with the method and the ratio. The ACR and the FDA do not accept it for final reading |
| Lossy compression | amber | any other modality compressed with loss |
| Table Modality LUT | red | the file converts the pixels by a table; Ipê applies only slope/intercept, so HU and densities may not be the real ones |
| DIFFERENT PATIENTS IN THE LAYOUT | red | the frames on the screen have studies from different patients (name or ID do not match) |
| Non-square pixel | amber | different spacings along the row and the column |
| Derived image | amber | ImageType DERIVED\SECONDARY (reconstruction, capture, map) |
| Sync between different frames of reference | amber | the frame is in a sync group (current) with frames from another Frame of Reference — another study, or the repositioned patient. They move by the offset from when they were linked, not by registration |

The reconstruction (MPR, MIP) inherits the compression stamp of the source series.

**On the copy.** In Settings ▸ Viewer ▸ Annotations, *On the copy (Ctrl+C)* chooses the annotation level of the copied image, separate from the screen's — for example, Partial 1 (without the patient data) for teaching, with no need to anonymize the file. The *minimal stamp* puts at the foot of the copy the series, the window, the scale, the processing applied (MIP 10 mm, subtraction, DSA, filter, fusion) and the serious stamps, even with the annotations hidden. The *Integrity stamps* item is in Settings ▸ Viewer ▸ Annotations; the red stamps appear at any level, except None.

## Window: from the file, typed and presets by modality

The window menu (the arrow of the Window button, or a double-click on the "W … L …" in the corner) offers:

- **From the file (Switch WL)**: all the windows recorded in the DICOM, with the name (mammography usually brings NORMAL, HARDER, SOFTER) and the VOI LUTs. The *Switch WL* action (no default key; choose yours in Keyboard shortcuts) cycles through these windows; in mammography it switches the views in sight together. The window name appears next to the W/L until you drag the window.
- **Type the window…**: width and level, for example `400 40` or `1500/-600`.
- **Save the current window as preset…**: records the window in view in the list of the frame's modality. MR, mammography, PET and the others can have their own list; without one, the general list (the CT one) applies. Keys 1–9 apply the preset of the active frame's modality. The lists can also be edited in Settings ▸ Viewer ▸ Window presets, choosing the list at the top. The display protocols keep using the general list.

## Sending to the film: F1 and F2

With the focus on a frame of the study:

| Key | What it does |
|---|---|
| F1 | sends the frame's image to the film, with the window, zoom and rotation it has on the screen |
| F2 | sends the frame's series — whole or a range, chosen in a window |

Both come by default and can be changed in Settings ▸ Viewer ▸ Keyboard shortcuts. Outside the study (in the database list, for example), F1 goes back to opening this guide. The **Film** button on the toolbar does the same as F1, and its menu offers *all frames* and *key images of the study*.

## Syncing frames

**Sync** button. The arrow next to it opens the options: Automatic in the same study, Window/level, Zoom and pan, Reference lines and Series strip. All are kept between sessions.

![The Priors panel (on the right) lists the patient's other studies; from here they come to the tab and link to the current study.](anteriores.png)

**Align automatically with the other study** (sync menu) does the **rigid registration** — 3D rotation and translation — between two studies of the same patient: open the other study in a frame beside it (Priors button) and leave the current study's frame active.

- The similarity measure is chosen automatically: **correlation** for the same modality and the same sequence; **mutual information** for different modalities or sequences (CT × MR, T1 × T2, PET × CT). The status bar says the rotation, the shift and the quality (good, fair, poor).
- The frames now scroll together by the center offset. When the other study is **rotated 1° or more**, the program offers to **write it in this one's plane**: a new series in the other study ("… · registered on <date>"), with this one's geometry and Frame of Reference — then the two move together slice by slice, and the 3D cursor, the reference lines and the ROIs land in the same place. The original files do not change.
- The registration (the whole matrix) is kept for both studies; adjusting by hand with **Alt+wheel** makes only the translation count again.
- It takes 5 to 15 s on CPU (it stops by itself at 90 s with the best finding; the Cancel button stops earlier). Rigid means the same shape: it serves well for skull, spine and bones; breast and abdomen deform between studies, and the result in those is approximate.
- **Checking the registration** (sync menu ▸ *Check the registration with the other study*): the other study goes over the active frame, in gray and with its own window, already with the stored registration matrix — **Checkerboard** (alternating squares of one and the other: the edge must have no step), **Curtain** (the divide follows the mouse), **Difference** (what remains bright is what did not align) or **50% blend**. The series already written in this study's plane enters without the matrix (it is already aligned). *Turn off* removes it.
- **Checked on the archive**: on a real 3D skull MRI, with known rotation and translation applied, the registration landed with a mean error of 0.4 mm (maximum 0.5 mm) in 6 s; two sequences from the same session (FLAIR and SWAN) gave 0.5° and 1.6 mm.

## Measurements

The **Measurements** button opens a window with everything measured in the study: series, image, type, value, lesion and text. Clicking a row takes you to the image with the measurement already selected. The list comes from the database, not from the open frames — a measurement made last week is there.

![Ruler and ellipse on the CT: the ruler gives the length; the ellipse, the mean ± standard deviation, minimum, maximum and area.](medidas.png)

- The **Select** tool edits what already exists: a click chooses, dragging moves, dragging the end resizes, Delete removes.
- **Edit lesion…** (or double-click on a segmentation row) reopens the segmentation with the threshold and the nipple you used (chapter 6).
- The measurements go out to a spreadsheet (CSV/Excel) and to DICOM SR.
- **Draft**: right-click on the measurement ▸ *Draft*. The measurement becomes **dashed**, on screen and in the database, but does **not go out**: it does not go to the SR, the GSPS, the report, the spreadsheet, the exported viewer or the lesion follow-up. Unchecking it turns it into a measurement that counts. In Settings ▸ Viewer ▸ Text and marks over the image, *New measurements start as draft* makes every measurement start that way (the ones that become a number; not calibration or spine).
- **Intensity profile**: right-click on a ruler or polyline ▸ *Intensity profile…* shows the graph of the value (HU in CT) along the line, in mm, with minimum, maximum and mean — the density transition, the wall of a lesion, the enhancement of a vessel. The graph follows the line when it is moved, and *Copy values* takes the table to a spreadsheet.
- **Delete this image…** (right-click on the frame) removes only that image from the study — the duplicate, the wrong capture. It asks for the delete permission, is refused in a study with a lock and on the last image of the series, takes along its measurements and key image, and stays in the access log.

### 3D ruler, uncertainty and reference ROI

- **3D ruler** (Measurements menu): click point A on one slice and point B on another slice — or in another frame, such as the axial and the sagittal. The distance comes out in 3D, with the right-left, anteroposterior and craniocaudal components; for two points on the same slice, the label says "(2D)". The third click starts a new ruler.
- **Thick slices**: a ruler drawn on a thick-slice reconstruction (the sagittal of a 5 mm axial) warns when its direction has a 5 mm pixel — the craniocaudal measurement inherits that error, the anteroposterior does not. On the original image, a ruler smaller than the slice thickness also warns.
- **Uncertainty** (Settings ▸ Viewer ▸ Text and marks over the image): shows ± the pixel in the ruler's direction and ± perimeter × pixel ÷ 2 in the ROI's area. Off by default; the warnings above always appear.
- **Clone the ROI**: right-click on an ROI ▸ *Clone this ROI in the other frames*. Each frame in view receives a new ROI **at the same position in the patient** (in mm, not at the same pixel: a series with another matrix or another FOV receives the ROI at the right size), on the slice closest to its center, with the mean, deviation and area of the image there — T2 → ADC, pre → post, current → prior. Within the same study the Frame of Reference applies; between different studies, first link the frames in a sync group (or register): without a common reference, the status bar says it did not copy and why. It also does not copy to a non-parallel plane or to a series that does not cover that point.
- **Symmetry axis by hand** (0.99.61): when the midline of the body found automatically does not serve (rotated patient, very asymmetric breast), right-click at the place of the axis ▸ *Symmetry axis (mirrored ROI)* ▸ *Mark the axis here*. It applies to the series, on this computer, appears as a dashed blue line on the axial and coronal, and *Back to the automatic axis* undoes it.
- **Mirrored ROI**: right-click on an ROI ▸ *Mirror to the other side (lesion / contralateral ratio)*. The new ROI ("Contralateral") goes to the mirror on the median sagittal plane: on an axial or coronal, the midline of the body on that image; on a sagittal series (bilateral breast MRI), the middle of the range of slices — and the frame goes to the slice on the other side. The original ROI now shows *lesion / contralateral* (its mean over that of the other side), on any map: ADC, enhancement, BPE. The status bar says where the axis ended up. Oblique plane, a series that does not cover the other side and a color image do not mirror, and the bar says why.
- **Reference ROI**: right-click on an ROI ▸ *Use as reference ROI*. The other ROIs of the series now show their mean in % of the reference (lesion/liver, lesion/aorta, lesion/muscle). Only one per series; it is marked "Reference (100%)" and follows if you move it.

## Measurement scale and calibration

To measure in millimeters the program needs to know the pixel size. In CT, MR and mammography this comes from the file (PixelSpacing). In ultrasound it does not: the scale changes at each image, because depth and zoom change during the exam, and the device records one calibrated region per rectangle of the screen. The program reads that region and measures in millimeters without you configuring anything.

The frame's lower left corner says where the scale comes from, and it is clickable:

| What appears | What it means |
|---|---|
| Scale: ultrasound region | came from the device's own tag, image by image |
| Scale: calibrated on this image | you calibrated by hand here; it applies only to this image |
| Scale: calibrated on the series | you calibrated by hand and marked it to apply to the whole series |
| No scale — measurements in pixels | the file does not carry the pixel size and nobody calibrated; the measurement comes out in px, saying it is px |

To calibrate by hand: **Calibration line** tool, draw over a distance you know (the image's ruler, for example) and enter the real length. The window also asks how far the calibration applies — only this image or the whole series. In ultrasound the default is only this image; in the other modalities, the series.

- The order of trust is: calibration of this image, calibration of the series, ultrasound region, the file's spacing. Whoever calibrates by hand has already seen that the tag did not serve.
- A dual-panel image has one region on each side: the measurement uses the region it is in. A measurement that crosses from one panel to the other goes back to pixels — distance between two different images is not distance.
- The spectral Doppler window does not calibrate distance: its axes are time and velocity, and the program refuses it on purpose.
- Ultrasound secondary capture (a screenshot of the device) usually comes with no region at all: then manual calibration is the way.

## Slice mosaic in the frame

Right-click on the frame ▸ **Image ▸ Slice mosaic** ▸ 2 × 2, 3 × 3 or 4 × 4 (or the *Slice mosaic in the frame* shortcut, which goes through the sizes): the frame shows **consecutive** slices of the same series, from the current one (the first, top left, has its number in yellow). It serves to skim a volumetric series without scrolling slice by slice, with another frame beside it scrolling normally.

- The wheel **turns the page**: the set moves together (4, 9 or 16 slices); the synced frames follow by the first one.
- Window/level, invert and the color table apply to all the images of the mosaic. Key images appear with ★.
- The mosaic is **for viewing only**: the measurement tools do not act on it. **Double-click** on an image goes back to the normal frame **on that** image.

## Key images

K (suggestion) marks and unmarks the frame's image as a key image; Shift+K shows only the marked ones. They go into the PDF report and the film with one click.

**Saving in the study (KO + GSPS).** **Key** button ▸ *Save key images and annotations in the study*: the key images become a DICOM **KO** object (Key Object Selection, "Of Interest") and the measurements, arrows and texts become a **GSPS** (presentation state), with each measurement's number written beside it — calculated with the same scale as the screen (manual calibration, ultrasound region, tag). Both stay in the study, go to the PACS together with it and open in other viewers (Weasis, OHIF, the device's workstation). A **draft** measurement is left out.

- **A KO that arrives in the study** (from another system, or ours coming back from the PACS) marks the key images here, once: unmarking afterwards does not bring them back.
- **GSPS from other systems**: with more than one in the same study, only the most recent appears; the others stay in the CAD/AI button, turned off. Our own GSPS, when reopened, stays turned off — the measurements are already in the database and would be drawn twice.
- **Bringing the measurements in to edit**: in the CAD/AI button, an SR or GSPS from another system has *Bring the measurements in to edit* — ruler, polyline, polygon, point and text become Ipê measurements (editable, in the measurements panel, in the report). The original object stays turned off.

## Reconstructions: MPR, oblique, curved and 3D

- **MPR** builds the volume and opens the three planes. You can also reconstruct only the active frame as axial, coronal or sagittal.
- The orientation line in the frame's corner is clickable: it chooses the plane, and **Oblique** turns the frame oblique without changing the image — from there the **Rotate plane** tool tilts it.
- Thickness (slab) on the MPR bar, with mean, MIP or MinIP.
- Curved MPR (click the points along a vessel) and 3D (volume rendering, with cuts, sculpting and mesh export STL/GLB/3MF).
- **Structures in 3D** (0.99.82): with the 3D open, the **Structures** button on the 3D bar (or right-click ▸ *Segmented structures*) shows as colored surfaces everything that is segmented in the study and turned on: AI organs, liver segments and lesions, nodules, hand-segmented lesions, lymph node levels, SEG and RTSTRUCT from other systems. The structures follow the volume's rotation, cut, plane and sculpting; what is behind the VR bone appears faded. Turning an object off in the CAD/AI list removes it from the 3D the next time you turn it on.
- The reconstructed plane always comes out in the reading convention — axial with anterior on top and the patient's left on the right — even when the acquisition was sagittal.
- **Remove the CT table**: right-click on the MPR or the 3D of a CT ▸ *Remove the CT table (MPR and 3D)*. The program finds the body (what passes through the middle of the volume) and erases what is outside it, slice by slice — the table goes, the lungs and airways stay. It applies to volumes built from then on (close and reopen the MPR/3D); the original series does not change.

![MPR in the three planes, with the 3D cursor and the segmentation structures also in the reformatted planes.](mpr.png)

![3D in the frame itself: MIP of the whole-body PET (the mode, the preset, the opacity and the views are on the top bar).](3d_mip_pet.png)

> **The volume is built in memory.** In Settings ▸ System ▸ Performance there is a ceiling; above it the program asks before building. The 3D runs on the CPU, and the detail (side of the volume) is also adjusted there.

# Multiple monitors

The program treats the set of screens as one workstation, not as several independent viewers: moving to the next step, changing protocol or changing the layout applies to the whole set.

## Setting up

Settings ▸ Monitors ▸ Monitor role, layout and order…. Each screen gets a role:

| Role | What goes there |
|---|---|
| Database | the main window, with the study list |
| Viewer | the open studies |
| Comparison | the prior studies, already linked to the current one |
| Do not use | the program puts nothing on that screen |

The **Order** column says which screen is 1, 2, 3 — and that number is what mammography uses when a step says "with 2 screens, show on Monitor 2". The **Order by position on the desk (left → right)** button is a good starting point; a repeated number is refused. **Identify monitors** flashes the number on each screen.

With two or more monitors marked as Viewer, the study opens split across them. With only one, it opens as a tab, as always.

- **Move the current study to monitor** (View menu) takes the open study to another screen.
- **Bring all studies back** returns everything to the main window.
- The series strip can stay only on the first monitor — Settings ▸ Monitors ▸ *Monitor role, layout and order…* ▸ *Series strip only on the first monitor*, with three options: only in mammography, whenever the study opens split, or never.
- The grid of each screen is remembered by type of study (chapter 5, *Layout memory*).

> **On Linux** the monitors' role depends on X11 reporting the screens' geometry; in some Wayland environments identification may fail.

# Mammography: display protocols

Mammography does not use the generic display protocol of the other studies. It has its own tab, with **steps**: each step is an arrangement of frames, and going to the next step changes all the monitors at the same time. It is the way screening reading really works — CC, then MLO, then comparison with the prior.

## Where the editor is

- Settings ▸ Study protocols ▸ **Mammography**;
- or, with a mammogram open, the last line of the **step:** combo on the study bar — *Edit protocols…*.

## Creating a protocol from scratch

On the left is the **Protocols** list — the first active one that matches is used. Buttons **+ New**, **Duplicate**, **Remove**, **Default**.

1. **+ New** and give it a **Name:** (e.g. "Screening 2 screens").
2. **Study description contains:** — empty applies to any mammogram; `RASTREAMENTO|DIAGNOSTICA` matches either of the two words. This is what chooses the protocol when the study opens.
3. Check **Active**. The other three boxes are about presentation: *Chest wall facing the center* (mirrors the image when needed, so the two breasts face each other), *Snap the image to the edge of the chest wall* and *Zoom by quadrant on all frames together*. **Align vertically:** (0.99.61) — *by the nipple* (default: on the same screen row, the nipple of both breasts is at the same height) or *by the middle of the breast* (as before). **Double-click** on a view shows only it (1×1) and reframes it for the large frame, without the alignment with the other breast; another double-click goes back to the step.
4. In the **Steps** group, **+ Step**. Give it a **Step name:** — it appears in the study's combo (e.g. "Current × prior CC").
5. Define the step's **Layout** (rows × columns).
6. Fill in the frames: either in the **As text:** field, or in the grid of combos, one per frame.
7. Repeat for the other steps and use ↑ and ↓ to put them in the order you read.

## The cell syntax

Each frame gets a code. The order is: view (optional) + side (required) + optional markers.

| Part | Values | Note |
|---|---|---|
| View | CC, MLO, ML, LM, XCCL, XCCM, AT, FB, SIO, SPOT, MAG, ANY | no view = any one. FB, SIO and ANY work but do not appear in the on-screen list |
| Side | D (right) or E (left) | required |
| Tomosynthesis | tomo or dbt | takes the tomo stack instead of the 2D |
| Contrast (CEM) | rec, recomb, sub or cem | the recombined image |
| Prior | ant / ant2 | ant = the prior study; ant2 = the prior of the prior |
| Another study (0.99.61) | US, RM, RM:text | the frame shows the patient's **latest ultrasound** or **latest MRI** (up to the study date, breast ones first); in MRI, the subtraction or the post-contrast, or the series whose description has the text after the colon (`RM:T2`) |

In the **As text:** field, columns are separated by `x` and rows by a comma:

```
1 × 2   CCD x CCE
2 × 2   CCD, MLOD x CCE, MLOE
2 × 2   CCD, CCD ant x CCE, CCE ant     (current above, prior below)
1 × 2   CCD tomo x CCE tomo             (tomosynthesis)
1 × 2   CCD rec x CCE rec               (contrast-enhanced, recombined)
2 × 2   CCD, US x CCE, RM               (mammogram with the latest US and the latest MRI)
```

A code the program does not recognize is refused on the spot, with the message "Unrecognized code(s): …". On the study screen, a frame with no definition shows *(empty frame in the protocol)*, and an image that does not exist shows "… not found (no prior study)" — instead of staying black with no explanation.

## Splitting the step among monitors

Inside the step: *In this step, with [1 to 4 screens] show on [Monitor N]*. You define, for each number of screens, what goes on each monitor. The **Split automatically** button undoes this and returns the step to automatic splitting.

With no arrangement defined, the automatic split follows this order: if the rows divide by the number of screens, each screen takes a block of rows (two rows on two screens = CC on one, MLO on the other); otherwise it tries by columns; otherwise it distributes the frames in order. With fewer images than screens, each screen gets one.

## Using it in the study

With the mammogram open, the **Mammography:** bar brings the protocol combo, the **step:** combo, and ◀ / ▶ to move. The default keys are **→** (next step), **←** (previous step) and **Q** (zoom by quadrant). Also on the bar:

![Mammography in the 4-view protocol (CC and MLO, right and left), with each breast snapped to the outer edge of the frame.](mamografia.png)

![The same study with tomosynthesis turned on in the first frame: the readout at the bottom left shows the slice and the depth.](mamografia_tomo.png)

- **Quadrant ↻** (Q) and **1:1** — full-size reading. Since 0.100.78 the quadrant has **four areas**: posterior and upper → anterior and upper → posterior and lower → anterior and lower → the whole breast (Shift+Q goes back). The quadrant applies to all frames together by default; the **Quadrant together** button turns it off during the study (only the active frame);
- **Magnifier** — hold the button; the wheel changes the magnification;
- **Thickness: thin ▾** — tomosynthesis slab: 1, 5, 10 or 20 slices, in MIP or mean;
- **LE ⇄ Recomb.** — switches between low energy and recombined in the contrast-enhanced exam;
- **Implant** — corrects the prosthesis in all frames (Alt+I); see below;
- **Density…** — measures the breast density of what is in the frames (chapter 6);
- **2D ⇄ tomo** jumps between the 2D and the tomosynthesis in the same list;
- **Breast in frame** reframes the breast (see below);
- **Zoom and pan** (0.99.61, the same sync button as in the main bar) — turned on, zoom and pan in one frame show the same place on the other breasts, mirrored. **Since 0.100.78, in mammography all syncs come turned off** (zoom and pan, window and slice scrolling) and are kept separate from the other modalities: turning one on here does not turn it on in CT, and vice versa. Zoom by quadrant (Q) still applies to the frames together (it belongs to the protocol, not to the sync; the **Quadrant together** button turns it off during the study);
- **Invert breast only** (0.99.61) — inverts the tissue and leaves the background black, in all frames and in the following steps;
- **Findings…** (0.99.64) — right-click on the image ▸ **BI-RADS finding here** ▸ *New finding* puts the mark "A1" and keeps the distance to the nipple; on the other view, *A1* marks the same finding. The table shows, for each finding, the breast, the views, the distance from the nipple (mean of the two) and the location — quadrant (or junction, central region, retroareolar), clock hour looking at the patient from the front and third (anterior, middle, posterior). On the CC, the lateral side is the top one (or the one PatientOrientation says); on the MLO, the upper one. Choose the type and **Send to the BI-RADS report** — the findings go into the report's BI-RADS panel, to complete description, size and category; sending again replaces the same findings, it does not duplicate;
- **★ Slice** (0.99.61) — marks the tomosynthesis slice (or the 2D image) of the active frame as a key image; the status bar says which slice and the thickness. In Shortcuts ▸ Mammography there is *go to next / previous marked slice*, to return to the stars in a tomo of dozens of slices;
- **✕** leaves the protocol.

### Implant (0.95; "correct" only since 0.96)

The **Implant** button (Alt+I) finds the prosthesis in each frame and **corrects** it: the silicone drops to the gray level of the surrounding tissue, but the fine detail remains — the tissue in front of or behind the prosthesis shows, and the edge does not become a step (method from patent US 8,160,346). **The window (WW/WL) does not change**: it stays as it was before turning the button on, even if you had adjusted it by hand. The old "erase" (smooth area) was removed.

How the prosthesis is found: it is the bright region with a **sharp edge and convex shape**, occupying 5 to 85% of the breast. Before searching, the program reads what the device writes on the image: with **BreastImplantPresent = NO**, or on a view with a **displaced implant** (label ending in ID, such as RCCID) or **spot compression / magnification** (RSCC, LMSCC…), it does not search, and the status bar says why. If there is still a prosthesis, right-click inside the silicone → **Find the implant from here**.

Checked on the archive: 28 2D images from 5 studies, 2 with a prosthesis — the 7 images with the implant in view were found, and none of the other 21. Without the device's information, searching by the image alone confuses the edge of the spot compression paddle with a prosthesis; on a device that writes none of this, use the click. A heavily calcified capsule leaves a bright and dark ring at the edge.

### Which image goes into the frame

For an MLOD cell, the program looks for the image with the same side and view and prefers, in this order: the one that is "for presentation", the one named exactly that view, and finally the most recent.

- What decides the view, when it exists, is the label the device recorded (GE, private tag 0045,101B): RMLO is the MLO; RSMLO, RSCC, RMSCC and RCCS are variants of it (supplementary, magnified), and all carry the same ViewPosition and the same view code — the DICOM standard does not tell the two apart, the service's label does.
- Without this label (tomosynthesis and V-Preview do not carry it), the series name applies: CESM_PROC_RMLO names the MLO, CESM_PROC_RSMLO does not. A name that does not mention a view (2D_PROC) breaks no ties.
- The supplementary one is not hidden: a second frame with the same view shows it, and the frame's label then carries the series name ("MLO D · CESM_PROC_RSMLO").
- If the study has only the supplementary one, it goes in — a filled frame with a warning in the label is better than an empty frame.
- The **synthesized 2D** of the tomosynthesis (V-Preview on GE) is a view, not a volume: it is a single image, with the side and view in the functional groups. It goes into the 2D cell; if the study also has the acquired 2D of that view, the acquired one is what opens, and the synthesized one stays behind it in the same frame list. When the synthesized one is on the screen, the label says "CC D · synthesized 2D".

## Framing on opening

Half of a mammogram's field is air. Fitting the whole image is fitting the air — so each protocol step has a field **On opening, frame:**

| Option | What it does |
|---|---|
| Breast to frame | finds the breast, discards the air and scales to fill the frame, with the chest wall against the edge. It is the default |
| Whole image | the usual fit to window (the whole detector fits in the frame) |
| Full resolution | 1 image pixel = 1 monitor pixel; the image is larger than the frame and is navigated with pan |

- The zoom comes from the frame's size, which depends on the monitor and on the step's layout. There is no fixed number.
- The two breasts of the step stay at the same scale — comparing side by side at different scales is not comparing.
- The breast is never smaller than in the fit to window.
- **Breast in frame** on the bar reframes at once — to use after changing the zoom by hand.
- An image **dragged** onto a frame (or opened in it with a double-click in the series list) also goes in framed; in a protocol frame the set is reframed together.
- If the breast is not found, the frame opens with the whole image and the status bar says in how many frames that happened.

> **No protocol matched?** The study falls into a common arrangement (ordered by view and side, in 2×2 or 1×2) and the log says which description did not match. The protocol also does not come up if no image has a recognizable side.

## Display protocols for the other studies

**Display protocols** (Settings ▸ Study protocols) handles CT, MR, US and the like — in the mammography way: each protocol has **steps**, and **← →** move from one to the other.

**When opening the study**, the first active protocol that matches (modality and "study description contains") opens at step 1. A bar appears above the frames: the protocol name, the list of steps (choose any), ◀ ▶, **Save the screen as a step…**, **Edit protocols…** and **Leave the protocol** (leaves the frames as they are). Three come by default for you to adjust: **Chest CT** (mediastinum, lung and lung in MIP, each with axial and coronal), **Breast MRI** (without contrast, dynamic, MIP of the subtraction) and **Brain MRI** (T2/FLAIR/diffusion and post-contrast with coronal).

**The tab** has three parts:

- on top, the protocols, one per line: Active, Name, Modality, Study description contains (`|` = or), how many steps and **Prior on the comparison monitor**. New, Duplicate, Remove, ▲ ▼ (the order decides which one wins first) and **Add the default ones**;
- bottom left, the steps of the chosen protocol (+ Step, Duplicate, Remove, ▲ ▼);
- on the right, the step's drawing: name, layout (rows × columns) and one button per frame. Click a frame and edit below:

| Field | What it does |
|---|---|
| Series | words from the series description; with `\|`, alternatives **in order of preference** (`T1 POS\|T1 GD\|T1` wants the post-contrast before the plain one). The same series can be in several frames (axial in one, coronal in the other) |
| From the prior study | the series comes from the patient's prior study of the same modality |
| Plane | as acquired, axial, coronal or sagittal (MPR) |
| Dynamic phase | whole series, pre-contrast, post-contrast 1 to 9 or last phase. The series is searched only among those that are part of a dynamic (▦); the 1st phase of the dynamic is the pre, so "post-contrast 1" is the 2nd phase of the group |
| Reconstruction | none (as the series), **MPR** (thin slice in the chosen plane), MIP, MinIP or mean with the thickness in mm, **3D MIP** or **VR**. The last two do the same as the 3D button: each frame becomes its own volume, with the whole 3D bar (mode, preset, opacity, color, Views, Cut, Sculpt, Rotate…) applying to the active frame |
| Half (half breast) | whole patient, only the right half or only the left half. The volume is cut at the center of the field (right-left). With 3D MIP or VR, the 3D of that half only; with MIP/MinIP/mean of thickness, the **sagittal** MIP of the whole half |
| View | which side you look from — the same **Views** as on the 3D bar: Anterior, Posterior, Right, Left, Superior, Inferior. In 3D it is the camera; on a slice, it applies when the slice is of that plane (lateral on a sagittal, frontal on a coronal, from above or below on an axial) |
| Window | a preset (Lung, Mediastinum…) or width/level typed by hand (`1500/-600`); "from the file" leaves it as it came |
| Color | gray or a color table |
| Position | automatic (the same place when switching series), first slice, middle of the stack or the same point of the previous step's active frame |
| Sync | frames with the same number scroll, zoom and change window together |
| With several screens | which monitor the frame goes on; "the program splits" divides the step as in mammography (by rows, otherwise by columns) |

**Save the screen as a step…** is the quick way: arrange the study on the screen (layout, series, a 10 mm coronal MIP, lung window, synced frames) and save. The window asks in which protocol (or a new one, with this study's modality and description) and whether the step goes in as new or replaces the one on the screen. Afterwards, in the editor, replace the saved series with alternatives (`|`) to serve other devices.

**Step with the dynamic assessment (0.94).** In the editor, each step has **Open the dynamic assessment (maps and curves)**, with the layout of the maps (the same as the Dynamic button) and the dynamic series (empty = the study's dynamic, detected automatically). On reaching that step, the program does what the Dynamic button does, without the window: it takes the phases, uses the **last parameters** you used on the button (thresholds, pre, initial, late, motion correction) and opens the maps with the curves panel. Moving to another step closes the dynamic; coming back opens it again. The default breast MRI has the **Dynamic assessment** step at the end — and whoever already had the breast MRI saved gets this step once. To change the parameters, use **Parameters…** in the dynamic panel: the next time the step opens, it uses the new ones.

**The step's reconstruction is a 3D volume (0.93).** Click on a frame where the step built a reconstruction (MPR, MIP, MinIP or mean of thickness) and the **3D — mode** bar appears, already in its mode. The first time you touch it (change the mode, preset, color, Views, Cut, Sculpt, Rotate…), the frame becomes a 3D: the same volume (the same phase, in the dynamic), cut at the thickness that was on the screen and looking from the same side. The other frames stay as they are. **Back to the series** undoes it. The 3D is built on a reduced grid (Settings ▸ System ▸ Performance), so it can come out less sharp than the thickness MIP. The MPR bar also now shows the frame's thickness (62 mm, 165 mm…) instead of "thin".

**Half-breast MIPs (0.90; in 3D since 0.92).** The default breast MRI has the **MIP of the phases (half breast)** step: 2 × 2, four **3D MIPs**, with post-contrast 1 on top and post-contrast 3 below; on the left the right breast seen from the **Left** (nipple to the left), on the right the left breast seen from the **Right** (nipple to the right). Each frame is its own 3D: click it and use the 3D bar — rotate, Views, cut, switch MIP for VR — without touching the others. The window of each MIP comes from the projection itself. Whoever already had the breast MRI saved gets this step at the end of the protocol once (the other steps do not change). For another combination — the 2nd post, the subtraction, the whole breast — change the phase, the half or the front of each frame in the editor. The two phases of the step stay built in memory, so the four frames come from two volumes. The middle is the center of the field of view: in a study with the patient off-center, the half may carry a piece of the other breast.

When a frame's series does not exist in the study, the frame says **Series not found** with what it looked for, and the status bar counts how many were missing. The reconstruction the protocol asks for on opening asks no question: a volume above the memory limit (Settings ▸ System ▸ Performance) is left out, with a warning. With the study on several screens, the step belongs to the workstation: changing step on one changes on all. Protocols made before 0.88 remain valid and become one-step protocols when the tab is saved.

### Saved analysis state

When the study is closed (by the tab's X, when switching studies or when leaving the program), Ipê keeps **how it was**, for each user: the layout, what was in each frame — the series, from which study, the slice, the phase and the view (window, zoom, pan, inversion, colors, rotation, flips and filter) —, the active frame, the left-button tool, the priors brought into the tab (which come back linked by the saved alignment) and the Measurements and Lesions panels. On reopening, the study comes back like that, and the status bar says when the state is from. The dynamic and the MPR are not rebuilt on their own — the calculation can take a while —: **View ▸ Analysis state ▸ Relink the dynamic as it was** opens the dynamic window with the same phases and parameters, and the MPR relinks on its button.

**View ▸ Analysis state** also has:
- **Reopen as I left it** — rebuilds the state at any time;
- **Back to the default arrangement** — forgets this study's state (and does not save it on closing this time);
- **Use the prior study's setup** — in one command: the layout and the views of the patient's prior study, each frame with the equivalent series of this study (same modality and description);
- **Open the prior alongside, as it was** — the prior enters the tab with its frames as you left them, next to those of this study.

**Resuming the session after a crash (0.100.8).** While Ipê is open, it notes which studies are open and keeps each one's analysis state **every 2 minutes**, and not only on closing. If the program (or the computer) crashes, on the next opening it shows the studies that were open and asks whether to reopen: **Reopen** opens each one as it was the last time the state was kept (layout, slices, measurements, panels), with what was in front back in front. Closing the program properly erases the note. In **Settings ▸ Viewer ▸ Analysis state on opening…**, **After a crash, the studies that were open**: ask (default), reopen without asking or do not reopen.

**Settings ▸ Viewer ▸ Analysis state on opening…**: reopen as I left it (default), ask or open as default. The state stays only in Ipê — in this computer's database or, in client mode, on the central server, for all workstations —, it does not travel with the study. It does not apply when the study opens with chosen series, by a protocol with steps, split between monitors, in mammography mode or in a meeting: there the protocol rules.

### Layout memory

Outside mammography, the program learns the grid without anyone configuring it: you adjust the layout of a shoulder MRI, and the next shoulder MRI opens that way. The label is modality + the words of the description that matter — side, contrast and numbers do not count.

- The memory is per monitor and per number of screens: the arrangement of one screen is not imposed when the same study opens on two.
- A display protocol written by you always rules over the memory.
- Only the grid is kept, never which series was in which frame.

# Breast: density, dynamic MRI and lesions

This chapter gathers what the program does specifically for the breast — the most developed part of it, and the one with the most written caveats.

## Breast density

The **Density** button on the bar, in a mammography study (see below), or **Density…** on the mammography protocol bar. The measurement covers the whole study, through the **NYU network** (a neural network in ONNX that gives the A–D category from the four views). Since 0.100.46 density has been removed from the File menu.

Until 0.100.47 the area % by the Otsu threshold and by fuzzy clustering also appeared. In the checks, they ended up very far from the confirmed categories, and since 0.100.48 only the network is measured and shown (what had already been saved with them stays in the database, off the screens).

> **What is missing for the number to enter the report:** blind reading — comparing the program's measurement with your category, without seeing the number beforehand. Until that is done, treat the value as guidance, not as a report.

### The Density button (0.100.44)

In mammography studies, the **Density** button sits on the bar (with its own button, outside the AI list). Clicking opens **Measure and review**; the small arrow shows the options:

- **Measure in the background (stays saved in the study)**: measures the four 2D views of the study without opening a window; the status bar says when it finishes, with the result.
- **Measure and review…**: opens the study's density. If it was already measured, it shows what is saved; if not, it measures on the spot. First and largest, the **NYU network**: the category and the probability of each one. The category marked by default is the network's (or the one you already confirmed); change it if you disagree and click **Confirm** or **Confirm and send to the report**, which puts the composition into the study's BI-RADS report (in a signed report, or one without the BI-RADS part, the sentence goes as text). *Measure again* redoes the calculation without losing your confirmation.
- **Review several studies in a queue…**: the queue below.

The measurement covers the whole study, not only what is on the screen, and is saved in the study (on the central server, when you use one), with who confirmed it and when.

### Measured densities (0.100.46)

**Reports ▸ Breast density: measurements and confirmations…**, or **Density** button ▸ *Measured densities…*. One row per measured study: date, patient, device, the **NYU network** (category and confidence), the **confirmed** category, who confirmed and when, and the status (not confirmed, equal to the network, different from the network). Filter by period and by status. On top, how many studies were measured and confirmed and the percentage equal to the confirmations, with the kappa. A double-click opens the study; *Export CSV…* takes the table, with the network's probabilities.

The NYU network has traveled in the Ipê package since 0.100.46: nothing needs to be copied to other computers.

### Reviewing the density (study queue)

**Density** button ▸ *Review several studies in a queue…*, or **Review density…** on the mammography bar. It is the way to find out, on your studies and your devices, whether the program's suggestion is any good.

1. Choose the period and click **Build the queue**: the mammograms in the database in that period enter (with *Only those I have not yet reviewed*, the ones you have not reviewed yet), the most recent first.
2. Each study opens in a viewer tab, and the window shows the **NYU network** suggestion (A–D category, with the confidence). Below, the device and the warnings (missing view, prosthesis). A study that was already measured (by the Density button) is not measured again, and your answer also counts as the study's confirmation.
3. Answer with a click or a key: **A**, **B**, **C**, **D** (or **1** to **4**), **N** for not assessable. The answer is recorded and the next study opens. **→** skips, **←** goes back (the button of the answer given stays marked). With *Close the previous study when moving on*, each study's tab closes when you proceed.
4. **Control**: in part of the studies (10% by default, adjustable) the suggestion appears only after your answer. Someone reviewing with the answer in view tends to agree with it; the control studies measure how much.
5. Below, the network's **agreement** so far: weighted kappa, exact hit and dense (C/D) × non-dense (A/B), in total and in the control studies. **Export CSV…** takes everything, study by study, with the network's probabilities.

The review stays in the database (on the central server, when you use one), one per study and per reviewer: reviewing the same study replaces the answer. These reviews show how much the network gets right on your devices.

### Vascular calcifications (0.100.51)

In a mammography study, the **Vessels** button (a vessel with calcified stretches) looks for vascular calcifications of the breast (arterial calcification) in **all 2D images** of the study: the four routine ones, the repeated ones, the other views (profile, XCCL…), spot compression and magnification (density, by contrast, uses only the four routine ones). Tomosynthesis is left out. The network is **SCU-Net** (Emory, MIT license), which comes in the Ipê package.

- **Measure and review** (the click on the button): opens the window with one frame per view and what the network marked — since 0.100.91 with a **white outline with a black border**, kept ~1 mm away, and **numbered arrows** at the ends of each vessel (the numbering follows the list of vessels in the scales, from the longest to the shortest; the punctate ones are only outlined). The marks look the same on the color monitor, on the B&W monitor and in the outside PACS (they used to be red, and red becomes a dark gray in B&W); the area in mm² of each image and of each breast (the largest among the full-field images); and the grade **suggestion**. When a view has more than one image, the frame shows *(1/3)* and the ◀ ▶ arrows — or the mouse wheel over the image — go through the others. Spot compression and magnification appear marked *outside the count* (the area in them comes out larger). If the study has not been measured yet, it measures on the spot (a few seconds).
- **Measure in the background** (in the button's menu): measures and saves in the study without opening the window.
- **Your grade**: **absent, mild, moderate or marked**. The suggestion comes marked by default; change it if you disagree and click **Confirm** or **Confirm and send to the report** (the sentence, for example "Moderate vascular calcifications.", goes as text to the report). **Measure again** redoes it without losing the confirmed grade.

The suggestion is **provisional**: it counts only elongated stretches (3 mm or more on the longest side, the vessel way; isolated dots are left out) and uses area cutoffs that are still uncalibrated (5, 30 and 100 mm² in the breast with the most). What counts is your grade; the areas are saved along with it, to calibrate the suggestion with your confirmations and, later, arrive at a point scale.

**Prosthesis**: the prosthesis edge fools the network. Ipê finds the prosthesis in the image (even when the device does not declare it) and takes out of the count what falls on it and in a 5 mm band around it; even so, in a study with a prosthesis there is no grade suggestion — check on the images.

**Scales.** Below the suggestion appear the published scales, estimated from what the network marked (hover to see how each is made):

- **Margolies** (0–12), per breast: vessels (1 point per vessel, up to 6) + extent in the most affected vessel (0–3) + density of the worst area (0–3: visible lumen/one wall, two walls in tracks, no lumen). The worst breast counts: 0 negative, 1–3 mild, 4–12 moderate to marked.
- **CSBI** (0–3): 1 a few punctate; 2 coarse or in tracks in fewer than 3 vessels; 3 three or more vessels.
- **Loberant** (0–3): 1 few punctate or short linear; 2 more abundant; 3 continuous.
- **BAC-SS**, on the MLO: Nv (vessels) + Ov (1 if the calcium covers the artery from side to side by ≥ 1 mm) + L (summed length in 4 classes: up to 12, 33, 84 mm and above).

They are estimates: "vessel" means stretches within 2.5 mm of each other; "tracks", two parallel stretches; "no lumen", a stretch 1 mm or more thick; the extent is the length of the vessel over the depth of the breast. Density is the least reliable part — check on the images. Studies measured before 0.100.55: **Measure again**.

In **Ipê Web**, the **Vascular calcifications** button (next to Breast density) does the same, measuring on the server: the previews with the marks (with ◀ ▶ and the wheel when the view has more than one image), the suggestion, the grade and the report. Confirming requires the permission to write reports. The panel opens large and can be **resized from the lower right corner**; the browser remembers the size.

### Automatic: measure on arrival, confirm on opening, SR in the study (0.100.57)

Every mammogram that arrives — received over the network, downloaded from the PACS (Q/R), imported or sent to the central server — has its **density** and **vascular calcifications** measured automatically, in the background, one study at a time (follow and cancel in **AI tasks**). Nothing is confirmed automatically: the measurements wait.

- **On opening the study** (in Ipê or Ipê Web), the **density** window opens with the suggestion marked; once confirmed (or closed), the **calcifications** one opens. Only what has not yet been confirmed appears, and once per open study.
- **Once both are confirmed**, Ipê writes three series into the study: the **SR** (*Density and calcifications (Ipê) SR*: the confirmed composition and the network's probabilities, the confirmed grade and the suggestion, the area per breast and per image, the scales, who confirmed and the references to the images), the **images with the calcifications marked** (outline and numbered arrows) (*Vascular calcifications (Ipê)*, one per image with calcification) and a table **summary** (*Density and calcifications (Ipê)*, for PACS that do not show SR). Confirming again (another grade) redoes the three.
- **The mammograms that were already in the database** are checked once, in the background, after opening the program (or the server) in this version: the task *Density and vascular calcifications — database mammograms* shows how many are left; the newest first. What does not finish continues at the next opening.
- Preferences ▸ CAD/AI ▸ **Density and calcifications (breast)**: turn on/off the measurement on arrival and the confirmation on opening; **Check the database again at the next opening**.
- **Accept the measurement without review** (0.100.78): the mammogram that arrives is measured and the SR, the marked images and the summary are written at once, as the network suggested, marked as **not reviewed** (in the SR and in the table). On opening the study you can still confirm or correct: the SR is redone, now with what you reviewed. The sweep of the old mammograms in the database only measures (it does not write SR).
- **After writing the SR, send to:** (0.100.78) the checked DICOM nodes (the PACS) receive the SR, the marked images and the summary — both without review and after confirmation (confirming again resends). The same applies in Ipê Web, in Registers ▸ AI automations.
- On a computer connected to a central server, the server does the measuring; the confirmation can be done on any of them.

### Where the AIs run in Ipê client (0.100.100)

In Ipê connected to a central server, **Preferences ▸ CAD/AI ▸ In Ipê client, run the AIs**:

- **On the central server (default)**: the AI requested in the viewer goes to the server's AI queue (the same as Ipê Web and the automatic ones). The progress window says the step; when finished, the new series (masks, mosaics, tables) come to the open study and the findings appear. It needs the **Request CAD/AI by hand** permission.
- **On this computer**: runs with this computer's AI package and, when finished, **the generated series and the findings go up to the server by themselves** — whoever opens the study elsewhere sees the same result. It needs the AI package installed here and the **Run the AIs on this computer** permission (by default: administrator and physician; the administrator changes it in Users ▸ Profiles). Without one or the other, the AI goes to the server, with a warning.
- In **batch from a spreadsheet**, the same choice: with "On this computer", the server searches, downloads and does the rest, but asks this computer for the AIs — leave the batch window open while it runs. What does not work out here, the server does itself.
- Segmentation by box (MedSAM2), which is interactive, always runs on this computer.

### Study link: opening a study in Ipê Web without a password (0.100.108)

Right-click on the study, in the database ▸ **Create study link (Ipê Web)…**. The link opens **only that study**, straight in the Ipê Web viewer, **without asking for a password** — whoever receives it does not see the list, the database, the reports or other studies.

- **For whom**: a name, so you know later who has the link.
- **The link can also**: *Run and review AI*, *Send to the PACS and other nodes*, *Attach PDF and images*. With nothing checked, view only (with measurements).
- **Valid for**: 1, 3, 7 or 30 days.
- **Create link** generates the address and already copies it; the list below shows the study's links, how many times they were used and when they expire. **Revoke the selected link** cuts off access at once, even for whoever has it open.

In **Ipê Web** (0.100.109), the same is on the **send** button of the viewer bar (since 0.100.112, a menu: *Send to a DICOM destination…* and *Study link (no password)…*): *Create and copy*, and the list of the study's links with *Revoke*. The link works through the central server's Ipê Web (in Ipê client, the server creates it). Creating a link requires the **export** permission. Each creation, use, denied attempt and revocation is in the access log. Whoever has the link sees the study until it expires: send it only to those who should see it.

### Mammography: density, calcifications and removing the silicone by hand (0.100.106)

In the **AI** tab of Ipê Web — and right-click ▸ **AI** in the database, in desktop Ipê — mammography shows three tools: **Breast density (BI-RADS)**, **Vascular calcifications of the breast** and **Silicone implant: remove the silicone**. They run on the whole study, in the server's AI queue, and do not need the segmentation package. *Remove the silicone* writes the copy " · without implant" even with the correction on arrival turned off — it is the way for old studies, which arrived before it. The density and calcifications measured this way appear for review, like those from arrival.

### Ipê Web: opening a study by external call (0.100.103)

Another system (RIS, a reporting system, a shortcut) opens the study in Ipê Web through an address:

- `https://<server>:8053/web/#/abrir?acesso=12345` — by access number;
- `https://<server>:8053/web/#/abrir?id=98765&data=20261123&mod=MR` — by patient ID, with date and modality (optional; the date also works as 2026-11-23 or 23/11/2026);
- `https://<server>:8053/web/#/abrir?uid=<Study Instance UID>` — only for what is already on the server.

Ipê Web searches the server first. If the study is not there, it searches the PACS nodes that the server shares (Settings ▸ Network ▸ node ▸ *Share with the clients*), **downloads and opens** when it arrives, showing the progress. With more than one study, it shows the list to choose from. Login is still required: without a session, Ipê Web asks for the password and returns to the address. Searching the PACS requires the search permission; downloading, the download one.

When the study comes from the PACS, it opens as soon as the first images arrive (0.100.105): the series appear in the strip and the series in the frame grows by itself, with a notice of how much has arrived.

**Stay signed in (0.100.104):** check *Stay signed in on this computer (1 day)* at login. The login then applies in all tabs of that browser and in the opening links, for 1 day, even when idle; *Sign out* forgets it in all tabs. Without checking, it applies only in the tab (and drops after 12 h idle). Do not check it on a shared computer.

### AI from the database, AI queue and liver table (0.100.101)

- **Right-click on the study ▸ AI**: the list of AIs that serve the study, like the viewer's AI button. Each one offers the options: **run on the suggested series** (or **redo**, if already done — marked with ✔), **run on another series** and open the study to see the result. The ones the rule left out stay in *Other AIs*, with the reason, and run anyway. With several studies selected, each AI is queued on all of them, on the series it chooses in each. In Ipê client, the same choice of where to run applies (server or this computer).
- **Queue**: requesting an AI while another runs on this computer is no longer refused — Ipê warns, queues the new one and it starts by itself when the other finishes. The queue appears in **AI tasks…**, where it can also be removed.
- **Image summary** (0.100.102): the liver AI writes into the study the series **"Liver on MRI: summary (Ipê)"** (OT), like the breast density one — PDFF and grade, dual echo, R2* and LIC, stiffness and range, each one's result and who reviewed. It is redone at each review in AI Findings (in desktop Ipê and in the Web), with the corrected numbers, and goes along to the configured destinations.
- **Reports ▸ Liver on MRI (steatosis, iron, stiffness): measurements and confirmations…** (also in the menu of the viewer's Liver button): one row per study with PDFF and grade, dual echo, R2* and estimated iron (LIC), stiffness and range, the review status, who reviewed and when; filters (not reviewed, with steatosis, with iron overload, with above-normal stiffness), a double-click opens the study and the CSV takes the table. The numbers are the ones that count: those corrected by the physician over those from the AI.
- **Batch in Ipê client (0.100.107)**: with *Bring the studies to this computer too* checked, the study goes from the PACS to the server and from the server to this computer's database; also checking *Delete from the server the studies the batch downloaded from the PACS, after they arrive complete on this computer*, it stays only here. The client only releases the delete when the study arrived complete (it retries what was missing); what was already on the server before the batch is never deleted. Leave the batch window open to the end: closed, the copy stops and the server deletes nothing. Since 0.100.111, each study starts coming **as soon as it reaches the server**, without waiting for the line's AIs and sends; at the end of the line only what is missing comes (the AIs' series), and the journal shows each study that arrived here.
- **What the AIs save and send: SEG, tables and color overlay series (0.100.124)**: in Settings ▸ CAD/AI, in the group *What the AIs save and send*, check what should go to the destinations — **SEG**, **tables and check images** and **color overlay series** — and choose the **destinations** that apply to all AIs. The color series is the study with the masks painted on, one image per slice, at the position of the original slice: any PACS scrolls it, even those that do not show SEG. It comes from the saved SEG, so it applies to every AI that saves SEG. It comes turned off by default (it takes space). The SEG and the tables always stay in the Ipê study; the boxes decide what is sent. **In each AI** (in its settings) the *What this AI saves and sends* box overrides the choice for all AIs: SEG, tables and overlay as As in all / Yes / No, and destinations added to the global ones or only the tool's own.
- **Exporting the AI results in batch to Excel (0.100.123)**: select the studies in the database, right-click ▸ **Export AI results (Excel)…**. The .xlsx gathers what the AIs **have already saved** in those studies (nothing is run): the *Studies* tab (one per row, with which AIs have a result) and one tab per AI, with the numbers of each finding (what the physician corrected counts in place of the AI's number) and the review status; mammography enters with density and vascular calcifications. You can **anonymize** (Case 001, 002…, no name, ID, accession or description). To run the AIs and export from a patient spreadsheet, use the batch.
- **Batch from a spreadsheet**: the study that is **already in Ipê** goes through the arrival rules (automatic AI, routing, printing), like a downloaded study — option checked by default in the *What to do* step (the study downloaded by the batch already went through them on finishing the download).
- **"On this computer" column** (in Ipê client): says whether the server's study is also in this computer's database — **complete** or **partial** (only part of the images).

### Research: the mammograms of a list, in batch

To measure the density and vascular calcifications of the mammograms of a list (a study), use **Network ▸ Batch from a spreadsheet…** with the ready-made template **Breast density and calcifications** — see "Batch from a spreadsheet" in the chapter *Search and download*.


## Dynamic breast MRI

The program reproduces the CADstream workflow: it detects the phases, corrects motion, calculates the parametric maps, classifies the kinetics in six colors and measures the lesion over the enhancement.

![Breast MRI: T2 and the dynamic phases side by side, synced.](rm_mama.png)

![The dynamic window: the detected phases, the pre-contrast, the SER phases and the kinetic map parameters.](dinamica_fases.png){70}

### Opening the dynamic

**Dynamic** button on the bar. The parameters window shows the series it recognized as phases and lets you choose:

| Field | What it is |
|---|---|
| Pre, initial and late | which phases are the pre-contrast, the peak and the late one |
| Minimum enhancement (%) | below this the voxel does not enter the kinetic map |
| Fast (%) / Late (±%) | the thresholds of the six classes: medium 50–100%, fast above; persistent / plateau / washout by the variation of the late phase |
| Minimum tissue signal (%) | mask: pre-contrast of at least N% of the reference signal |
| Correct motion | registration by 3D translation between the phases |
| Include rotation | rigid registration (rotation + translation) of each phase onto the pre, slower (up to about 40 s per phase); only resamples in 3D the phase that rotated 0.75° or more — in the archive's breast MRIs the rotation between phases did not exceed 0.5°, and then the translation is kept |
| Layout | which maps go to which frames |

The values are kept: the next study opens with the last ones you used.

### Aligning the phases (motion correction)

When the patient moves or breathes between the phases, the subtraction shows a "ghost" at the edges. The **Breast dynamic: align the phases** AI fixes this **in 3D**: it aligns all the phases with each other (joint, deformable registration with elastix) and writes **into the study itself** the aligned phases (*Aligned dynamic 1…N · Ipê*) and the post − pre subtractions (*Aligned subtraction…*). The original series is not touched, and the new images say in the header that they were aligned by AI.

- **Install (once)**: Settings ▸ CAD/AI ▸ *Install the breast dynamic alignment (elastix, ~1.5 GB)…*. It needs the internet and disk space; it stays in an environment of its own.
- **Do by hand**: in the database, the study's **AI** menu (or the Ipê Web AI menu) ▸ *Breast dynamic: align the phases*. The task appears in the AI queue; it takes a few minutes and uses 1 to 2 GB of memory.
- **Do automatically on arrival**: Preferences ▸ CAD/AI ▸ *Breast dynamic: align the phases* ▸ *Align automatically when the dynamic breast MRI arrives* (comes turned off). It runs on the server, one study at a time.
- **Only when it is worth it**: the program measures how much of the |post − pre| residual the registration removed — the contrast enhancement stays, only the misalignment goes. If it removed less than the limit (default 12%), nothing is written and the study stays as it was. When requested by hand, it always writes.
- Other options: whether or not to write the subtractions, the deformation mesh (32 mm corrects breathing and body motion; smaller corrects finer and takes longer) and the nodes to send the result to.
- **Redo** replaces the previous aligned dynamic. To view, open the study's *Aligned dynamic* and *Aligned subtraction* series; the Dynamic window does not use them by itself yet.
- **Caution**: always check against the original. This version was tested on synthetic studies; MRI in multiframe (Enhanced) files is not yet supported.

### The maps

| Map | What it shows |
|---|---|
| MSI | initial enhancement rate (signal/min) |
| PEI | peak enhancement, in % over the pre-contrast |
| SER | enhancement ratio: < 0.9 persistent, 0.9–1.1 plateau, > 1.1 washout |
| Kinetic | the six classes in color: the hue says the late behavior (blue persistent, green plateau, red washout) and the brightness says the intensity |
| Subtraction | post minus pre |
| Temporal MIP | the greatest enhancement of each voxel in **any** post-contrast phase (maximum of the subtractions): the lesion appears at its peak, even if outside the initial phase |
| Temporal mean | the mean enhancement of the post-contrast phases |
| Arrival (BAT) | the time (s) until the voxel's enhancement reaches 10% of its peak, interpolated between phases |
| Washout | the greatest **descent** slope after the peak (MSI unit); 0 when the curve does not fall |
| iAUC90 | the area under the enhancement curve in the first 90 s (PEI unit) |
| Mean time (MRT) | the mean time of the enhancement, ∫t·enhancement / ∫enhancement (s) |

The last four (0.99.48) also come out per curve, in the BAT, Washout, iAUC90 and MRT columns of the table and in *Copy values*.

**Pharmacokinetics: Tofts, Ktrans** (0.100.67; *Ktrans (Tofts)…* button on the panel). Calculates, voxel by voxel, the Tofts model: **Ktrans** (min⁻¹, the passage of the contrast from plasma to interstitium), **ve** (the fraction of the extravascular extracellular space), **kep** = Ktrans/ve (the return to plasma) and, in the **extended Tofts**, **vp** (the plasma fraction). The maps enter the *Active frame* list (Ktrans goes by itself to a map frame without ROIs), and each ROI or point gets the Ktrans, ve and kep columns in the table and in *Copy values*. The window asks for:

- **Arterial input**: the *population (Parker)*, which is the mean curve of the contrast in plasma measured in patients, for the standard dose; or the **ROI on an artery** — first draw an ROI inside the aorta or the internal mammary on a dynamic frame, and it appears in the list.
- **Injection start**, counted from the time of the pre phase (by default, half a phase: the contrast enters when the pre ends and the image counts for the middle of the acquisition).
- **Tissue T1 before the contrast**: assumed (there is no T1 map in the routine study) — about 1250 ms at 1.5 T and 1450 ms at 3 T for the fibroglandular tissue. **TR** and **angle** come from the study; without them, the concentration comes out by a linear approximation. Contrast **relaxivity** and **hematocrit**.

> **Read the window's warning.** The model asks for one image every 5 to 15 seconds. The routine breast MRI makes one phase every 60 to 90 s: the arterial peak is not seen, T1 is assumed and the arterial input is the population one. In that case Ktrans is **indicative** — it serves to compare regions of the same study and studies of the same protocol, not as an absolute value nor for comparison with the literature. In tests with simulated curves — ideal condition, with the right T1 and injection time —, with one phase per minute the error is around 5 to 15% for Ktrans up to 0.25 min⁻¹ and grows a lot above that; with one image every 5 s, it is below 3%. What applied to the maps is written at the top of the panel while they are turned on. Where the fit does not close (no enhancement, noise, vessel), the map stays at zero. **Turn off**, in the same window, removes the maps and the columns.

**Color maps** (0.99.64, like ColorViz/AngioViz): *Time in color* paints each enhancing voxel by the time of its peak — red early, yellow and green in the middle, blue late — with the brightness by the maximum enhancement (the 99th percentile of the enhancing tissue is full brightness, equal on all slices); it shows the order of arrival, which the 6-color kinetic map does not show. *Phases in color* puts the enhancement of the initial phase in red, the intermediate in green and the late in blue: what washes out is reddish, the persistent is bluish. Outside the enhancing tissue (the maps' threshold), black. They are color images: they save as a series, but do not reformat nor enter the per-ROI calculations.

**Phases left out of the calculation and baseline** (*Parameters…* button). In *Phases left out (motion)* write the number of the phase that moved (for example `4`, or `4, 7`): it leaves the maps and the curve calculations, and the rest is recalculated with the real times. The initial phase, the late one, all the pre ones and two consecutive phases cannot be left out (the curve would lose the whole stretch). In the graph the phase is still drawn, marked "out"; in the list of views it appears "(out of the calculation)", and the panel title and the summary line say which ones were left out. *Baseline: mean of all phases up to the chosen pre-contrast* uses the mean of the pre phases as the baseline — with two pre or more, less noise. With only one pre phase, the panel warns.

**Landscape.** With the subtraction turned on in the phase menu (frame corner), *Landscape (anatomy on the subtraction)* returns 10, 20, 30 or 50% of the anatomy to the subtraction — to find the nipple, the clip or the skin without changing series. It applies to all phases and appears in the corner ("subtraction + 20% anatomy"). Digital subtraction (DSA) has the same option in its menu.

Each map keeps the color you chose last, separately. The legend beside it always shows the table in use.

**Changing the plane**: the **Plane:** box at the top of the panel, or the frame corner — Acquisition, Axial, Coronal, Sagittal and **Oblique** (rotatable). It applies to the maps, the subtraction and the phases. Turning the plane calculates all the slices at once (a few seconds, with a bar and a stop button). **Back to the acquisition plane** returns to the slice that was in view. The reconstructed frame does not enter the curves — an ROI on a reconstructed slice would cross several original slices —, but you can **segment on it**.

### Time-intensity curves

With the **Intensity** tool, click on a point, or draw an ROI (ellipse, rectangle, polygon) on any frame of the dynamic. The curve appears in the panel, with the classification on the same scale as the map. **Worst pixel of the ROIs** finds, inside the ROI, the most suspicious pixel and marks it with ✳.

### Measuring the lesion

**Segment 3D** tool: click on the lesion and the program grows the region in three dimensions over the enhancement, not over the raw signal — in the raw signal the fat is as bright as the lesion.

- **Threshold**: the *includes more ← → includes less* bar tightens or loosens the region, and it redoes itself when you stop dragging — volume, patterns and distance included. The − and + buttons do the same in steps.
- The lesion appears drawn on **all series and planes** of the study: on the reconstructions, on the other phases, on T2, on diffusion. It is kept in millimeters, in the patient's space, and comes back drawn when you reopen the study.

| Number | What it is |
|---|---|
| Volume | the volume of the grown region, in mL |
| Angiovolume | the volume of the part that enhances: excludes necrosis, fibrosis and cyst |
| Peak enhancement | greatest percentage increase in the peak phase, with the mean beside it |
| Perpendicular axes | the three largest axes perpendicular to each other — not the box on the series' axes |
| Largest axis | the one that goes into the report |
| Percentage of the six patterns | the distribution the map shows in color, as a number |
| Kinetic heterogeneity | Shannon entropy of the six classes, normalized from 0 to 1 (the CADstream formula is not published — and the screen says so) |

> **A thin, long region is a vessel, not a mass.** When the elongation exceeds three times the diameter of the sphere of the same volume, the program warns. It does not decide for you: it warns, and the threshold adjustment is the brake.

In the lesion window: **Save as measurement**, **Save and link to a lesion…** (follow-up), **Save as DICOM SEG**, **3D surface (STL)…** and the two buttons that follow.

### Distance to the nipple

The **Distance to the nipple** button measures from the **edge** and from the **center** of the lesion to the nipple. There are two ways to find the nipple:

- **Mark the nipple** (recommended): click the button and then the nipple, on the image. The distance comes out **at once**, from your point, and the point applies to **the other lesions of the same breast** in the study — in an acquisition of both breasts, each breast has its own. When the study is reopened, the point comes back from the saved lesions.
- **Automatic**: without a mark, the program looks for the nipple through the skin surface — the most anterior point of the skin on the lesion's side. It takes about 15 seconds on the first lesion of the study. It errs on a breast cut off in the field or with a retracted nipple; that is why the screen says whether the point is yours or the program's.

The distance enters the saved measurement, the measurement's label, the measurements panel, the report and the capture. The distances to the skin and to the pectoral muscle were removed from the program.

### Lesion capture (2×2)

**Save capture (SC)…** writes into the study a 2×2 image of the lesion, as a new series "Capture: <name>":

- sagittal and coronal on top, axial and the enhancement curve below; the images are the **2nd phase** of the dynamic (the first post-contrast), with the lesion's edge in its color, the **whole plane** (no zoom), orientation letters and a 10 mm ruler;
- the curve is the mean signal of the whole lesion per phase, with curve type, SER and kinetic class;
- footer with volume, angiovolume, enhancements, axes, dominant pattern, heterogeneity, distance to the nipple, threshold used and "semi-automatic measurement — check".

If the lesion already has a capture, the program asks: **Replace the previous one**, **Create new** or Cancel.

### Editing a lesion

In the **Measurements** panel, **Edit lesion…** (or double-click on the row) reopens the window with the name, the method, the threshold and the nipple you used; **Save** updates the same measurement. If the dynamic is not open, the program offers to open it with the phases in which the lesion was measured.

### Numbers for the whole study

**Study numbers…** button on the dynamic panel. It measures over the breast mask and returns: breast volume in the mask, the study's angiovolume, background parenchymal enhancement (mean and median) and the percentage of each of the six patterns — with the formula written beside it.

> **How far this number counts today.** The mask cuts at the chest wall, but keeps skin, vessels and pectoral muscle. So the number serves to compare the same patient and the same service over time — not to become a category in the report nor to compare with a published number. The enhancement measured only in the fibroglandular tissue is on the next button.

### Fibroglandular tissue and background enhancement

**Fibroglandular and enhancement…** button on the dynamic panel. The program separates, in the breast, the **fibroglandular tissue** (FGT) from the fat and measures how much it **enhances** in the first post-contrast phase.

- **Where it separates**: on the study's **non-fat-saturated T1** (the "A T1", "Axi T1" or "Ax T1 FSE"), which is where fat and gland are most distinguishable; without it, on the **Dixon** (the FAT:/WATER: pair, by fat fraction); without both, on the **pre-contrast of the dynamic**, with the warning that the number is less reliable.
- **How**: removes the skin (3 mm), corrects the coil gradient using the fat as a reference and separates with an automatic threshold (Otsu) in each breast. It also removes the **muscle** (the dark one against the chest wall, up to 25 mm from it) and the lateral chest wall (what lies behind the most anterior point of the lung). An **implant** (dark, smooth, thick block) leaves the calculation, with a warning.
- **The result**: for each breast, the percentage and the volume of the FGT; and, with the dynamic open, the **median enhancement** of the FGT and how much of it enhances more than 20%. The mask is carried to the dynamic's grid by position in the patient, so the dynamic can have another resolution.
- **Copy sentences** takes two ready sentences for the report; **Save the mask (SEG)** writes the breast and the FGT as a segmentation series (*Breast and fibroglandular · Ipê*), to check over the images.

> **The program returns a number, not a category.** The percentage by volume comes out well below the visual impression (a study reported as "scattered" measured 10%), and the voxel-by-voxel measured enhancement has not yet been calibrated against reports. The quantity category (a–d) and the background enhancement one (minimal to marked) stay with the physician; the number serves to follow the same patient and to see asymmetry between the breasts.

### Dynamic ready on arrival

In **Automation ▸ Dynamic ready** you can have the program, as soon as a study arrives and matches the rule, detect the phases and decode the frames in the background — the study opens instantly. Nothing is written as a series and nothing is sent.

## Diffusion (ADC) in any MRI

**Diffusion** button on the bar, in **every MRI** (since 0.100.37; before, only when some series said DWI, DIFUSAO, TRACE… in the description — devices that call diffusion by another name were left without the button). It opens a panel that is not modal: you can draw on the frame with it open.

- **Diffusion series**: the study's, chosen automatically by the description; the other MRI series stay in the list, because not every device writes "DWI".
- **b values**: read from the file — the standard one (0018,9087) and each manufacturer's own places (GE (0043,1039), Siemens, Philips). One box per b: uncheck the b you do not want in the fit. When the file does not say the b, type them in the order they repeat in each slice (e.g. *0, 1000*). In the anonymized GE series, which loses the private tag, the image without b in a series where the others have b > 0 is the b0 — the panel warns that it deduced it.
- **Warnings before calculating**: only one b; no b0; highest b below 500; slices without all the b; different TE between the b; more than one image per b in the same slice.
- **Calculate and save the ADC**: regression of ln(S) against b over all checked b (with two b, it is ln(S0/Sb)/b). Unit **×10⁻⁶ mm²/s**, the same as GE's ADC. A pixel with b0 signal below the *noise threshold* (5% of the 99th percentile, by default) stays 0; with three b or more, a pixel with a fit worse than the *minimum R²* (0.25) does too. The map is written as an MR series of the study ("ADC (Ipê) · b0-1000"), with the DWI's geometry — it syncs, measures with the usual ROIs (the pixel value is the ADC), goes to the film, to the export and to the PACS — and opens in the active frame.
- **Synthetic DWI**: S(b) = S0·e^(−ADC·b) at a chosen b (50 to 5000), written as "Synthetic DWI b1500 (Ipê)". It is a calculated image: do not use it to calculate ADC.
- **Measure the selected ROI**: draw an ROI (ellipse, rectangle or polygon) on a frame with diffusion, the ADC from here or the device's; the table brings, for the same ROI, the **ADC from here**, the **device's ADC** (when the study has it) and the **signal at each b**: mean, SD, median, minimum and maximum. **Send to the report** takes the sentence with the mean, the SD and the minimum.

**Checked on the archive** (16 series from five GE devices, b0 and b1000 or b750): in the skull the ADC from here is the device's (ratio 1.0002, median difference 0). In the breast the difference is noise (median of 120 to 330 × 10⁻⁶ mm²/s): the device calculates the breast with averages and directions that it does not record in the DWI series, and the Pioneer zeroes 94% of the image. That is why the table shows both.

## Dynamic series: joining and splitting

Two opposite problems, in the same place — Settings ▸ Study protocols ▸ **Dynamics**:

- **Join**: the device writes one series per phase (breast MRI). The series that match become a dynamic, and this is recorded in the database.
- **Split**: the device writes all the phases in the same series (triphasic CT). The series is split into phases only on the screen, with one thumbnail per phase in the strip, and "Undo the group" returns the whole series. Nothing is written, no file is touched.

The rule is modality + description contains, compared without accents and without case, and applies when the study opens. When you mark a dynamic or split a series by hand, the program notes the rule as **pending**: it appears in the table and does not act until you confirm. Three states — **Confirmed** (always applies), **Pending** (does not act) and **Ignore** (applies only to the study where it was born).

# Case lists, smart lists and meeting mode

The **Case bank**, in the left panel of the database screen, organizes studies in folders and lists. When creating one (**+ List**), the program asks the type:

| Type | What it is for |
|---|---|
| Normal | a collection of studies that you assemble by hand |
| Meeting | the same as normal, but each case gets a friendly name, history, answer, notes and tags — it is the list of a clinical or teaching session |
| Smart (filter) | you do not put studies in: you write a filter, and the studies that match appear by themselves — including those that arrive later |

## Creating a smart list

1. In the left panel, **+ List**.
2. Give the name and choose **Smart (filter)**.
3. Fill in the filter. Only the filled fields enter the calculation.

| Field | What it does |
|---|---|
| Search | matches patient name, ID, accession or description. `\|` separates alternatives |
| Modality | All, CT, MR, MG, US, CR, DX, PT, NM, XA, OT |
| Study from the last | N days (0 = any date) |
| Description contains | a piece of the study description |
| Region contains | body part |
| Institution / unit contains | part of the name is enough |
| Origin | Any, Imported, Received over the network, Downloaded from the PACS, Prefetch, Anonymized |
| Only studies | with key images · with measurements · with comment · protected · not yet opened · that are in no list |

Everyday examples:

```
MRI from the last 3 days        Modality: MR · Study from the last: 3 days
Breast MRI                      Modality: MR · Description contains: mama
What I have not read yet        Only studies: not yet opened
Cases with measurements, to review   Only studies: with measurements
```

The smart list stays in the same tree as the others, in green, with the count beside it. The content is recalculated every time you open it.

> **What the smart list does not do.** It does not accept dragging a study into it (the filter rules), it does not appear in the "Add to list" menus, and its cases have no friendly name, history or answer — in a meeting they appear as "Case 1", "Case 2".

## Meeting mode

It serves to go through the cases of a list one by one with the patient data hidden across the whole program — clinical session, class, peer review.

### How to enter

- **▶ Meeting mode** button in the left panel (presents the selected list);
- right-click on the list → **▶ Start meeting**;
- right-click on a study in the list → **▶ Meeting from this case**;
- **Meeting** button on the start bar.

### The meeting bar

| Button | Shortcut | What it does |
|---|---|---|
| ◀ Previous / Next ▶ | Alt+← / Alt+→ | move through the cases |
| Cases ▾ | — | menu with all of them, to jump straight to one |
| History | Alt+H | shows the case's clinical history text |
| Reveal answer | Alt+R | shows answer, notes and tags |
| Full screen | F11 | hides the window frame |
| End meeting | — | goes back to normal |

### What changes while the meeting is on

- the database table becomes anonymized, with the case's friendly name in place of the patient;
- all viewer tabs have Anonymize turned on and locked — and the film too;
- the PACS, Management and Film panel windows become unavailable, with the explanation on the screen;
- only one case open at a time: when moving to the next, the previous one closes.

The **Hide** button on the start screen does the same hiding of data outside a meeting.

## Case package (opens in the browser)

Starting with 0.100.56 a list becomes a **case package**: a folder with the complete viewer — the same as Ipê Web, with MPR, MIP, fusion, mammography and measurements — and the anonymized studies, for class, a congress or to send to colleagues. Whoever receives it installs nothing.

### Preparing the cases

In **Organize list** (right-click on the list), each case has two parts:

| Part | Fields |
|---|---|
| Presentation | Case name, Tags, **History** (clinical, data, the question), **Series to open** (none checked = all) |
| Result | **Answer** (diagnosis), **Report / result** (the **Use the study's report** button copies the report text — check it and remove names), **Biopsy / pathology**, **Teaching notes**, **Result series** (they appear only when showing the result: the specimen, the pathology PDF, the image with the marking) |

The **markings** made in Ipê (arrows, measurements, ROIs) go in the package and appear only in the result. PDFs and photos attached to the study enter as documents of the case (those of a result series, only in the result).

### Exporting

Right-click on the list → **Export case package (opens in the browser)…** → choose the folder. Ipê creates a folder with the list's name containing:

- `Abrir casos (Windows).exe`, `Abrir casos (Mac Apple)`, `Abrir casos (Mac Intel)`, `Abrir casos (Linux)` — two clicks open the browser with the cases (a little server only for this computer; the black window stays open while the cases are viewed);
- `LEIA-ME.txt` (in Portuguese, English and Spanish);
- the site and the `casos` folder with the studies.

The studies go out **anonymized**: name "Case N", no birth date, institution, physicians or accession, dates shifted (keeping the interval between studies), new UIDs with no way back, burned-in text blacked out on captures and on ultrasound (the **device's saved screens** — the color elastogram, graphs — lose the whole header and footer, where name, age and birth date sit, since 0.100.94). Attached PDFs and photos go as they are — check them. The images go compressed losslessly (HTJ2K).

### Opening

- **Flash drive or file**: copy the folder and use the system's "Abrir casos". On the Mac, if it does not let you open it, right-click ▸ Open.
- **On a website**: copy the whole folder to any static file hosting (the folder's address opens the cases). No Ipê server needed.

It opens the list of cases (with search); each case opens in the viewer with the **Case** tab on the right: the history and the **Show the result** button, which brings the diagnosis, the report, the biopsy, the notes, the series and documents of the result and the markings on the images (**Hide the result** goes back). **Previous / Next** move between cases. Report, AI, sending, PACS and film are hidden — the package has no server. The measurements you make stay only in that browser tab.

### Hiding profiles

The arrow on the **Hide** button (in the viewer) chooses **what** is hidden. The choice applies to all tabs and to the database list (the Hide button on the start screen); the meeting always uses *Hide everything*, with the case name.

| Profile | Name | ID | Birth date | Sex and age | Study date | Institution, accession, physician | Device |
|---|---|---|---|---|---|---|---|
| **Hide everything** (the usual) | "Patient hidden" | — | — | — | — | — | shown |
| **Screen** | pseudonym | pseudonym | — | shown | shown | — | shown |
| **Teaching** | pseudonym | — | — | shown | **shifted** | — | shown |
| **Publication** | "Patient" | — | — | shown | — | — | — |

- **Pseudonym**: `PACIENTE-` and six characters, the same for the same patient while the program is open (the current and the prior study of the same patient have the same pseudonym); it is not written anywhere.
- **Shifted date**: all the dates of the same patient move back by the same number of days (30 to 329, drawn per patient) — the real date disappears, the interval between studies stays.
- The frame's corner shows the profile in use (a padlock and **Teaching**, for example), and so does the tab's title.
- **Hiding on screen does not change the files.** To take the study along, use Export: with the screen hidden the export comes out anonymized, and in the Teaching profile the **Shift the dates** option already comes checked (the same shift as on the screen).

# External call (RIS, link and API)

The external call is what makes the RIS, a script or a button on a page open the right study in Ipê. There are three entry points — command line, `ipe://` link and local HTTP API — and all three generate the same request internally.

> **What goes in and what never does.** From outside, only open, download and status are accepted. Delete and export are not exposed, on any of the three entry points.

## The three entry points

1. **Command line** — `ipe-cli.exe`:

```
ipe-cli open --accession 123456
ipe-cli open --study-uid 1.2.840.113619.2...
ipe-cli open --patient-id 00987
ipe-cli open C:\folder\study             (imports and opens)
ipe-cli retrieve --accession 123456      (downloads without opening)
```

2. **ipe:// link** — for the web RIS, an e-mail or a shortcut:

```
ipe://open?accession=123456
ipe://open?accession=123456&node=PACS&janela=viewer
ipe://retrieve?studyuid=1.2.840...
```

Register the link once on each computer: **Network ▸ Register the ipe:// link on this computer**, or `ipe-cli register-url`. The registration is in the user's profile and records the executable's path: if the program moves, register again. On **macOS** no registration is needed: `ipe://` and `dicomviewer://` belong to the application itself, and the link opens Ipê (or goes to the one already open).

**Link aliases** (0.100.32). If the RIS already has another viewer's button, Ipê can answer by its name: in **Network ▸ External call ▸ Link aliases**, write the names separated by commas (for example `osirix, horos`). On saving, Ipê registers itself in the system for those names. The alias accepts Ipê's format (`osirix://open?accession=123`) and that of OsiriX/Horos:

```
osirix://?methodName=displayStudy&StudyInstanceUID=1.2.840...
osirix://?methodName=displayStudy&PatientID=12345
osirix://?methodName=displayStudy&AccessionNumber=123456
```

Only open and search are accepted; `downloadURL` (downloading from any address) is refused. The same rules as `ipe://` apply: with the token it opens directly, without the token the choice *ipe:// link without the token* applies. If the real program (OsiriX) is also installed, the system decides who answers; Ipê asks to be the default when registering. On macOS each alias becomes a minimal application in `~/Applications/Ipe links`, which only passes the link on to Ipê; removing the alias from the list deletes that application.

3. **Local HTTP API** — for scripts and for the RIS on the same machine:

```
GET http://127.0.0.1:8042/api/open?accession=123456&token=YOUR_TOKEN
GET http://127.0.0.1:8042/api/retrieve?studyuid=1.2.840...&token=YOUR_TOKEN
GET http://127.0.0.1:8042/api/status?token=YOUR_TOKEN
Response: {"ok": true, "resultado": "aberto"}
The token also works in the header: Authorization: Bearer YOUR_TOKEN  (or X-Token)
```

## All the parameters

They apply equally on the link and on the API. On the command line, the same parameter appears as an option with two dashes.

| Parameter | Command line | What it does |
|---|---|---|
| accession | --accession | order number. It is the most used by the RIS |
| studyuid or study_uid | --study-uid | StudyInstanceUID |
| patientid or patient_id | --patient-id | opens the patient's most recent study (just one) |
| node | --node | where to search if the study is not in the database: exact node name or exact AE title. Without this, it searches all nodes marked "use in search" |
| janela (or window, modo) | --janela | viewer = only the viewer in this call; completo = the whole program. Without the parameter, the Network setting applies |
| token | — | HTTP API only; required |
| requestType | — | IHE IID: PATIENT (the patient's studies) or STUDY (the requested studies) |
| accessionNumber, studyUID, patientID | — | the IHE IID names; several values separated by commas (or the repeated parameter); patientID accepts `123^^^ISSUER` |
| mostRecentResults (or recentes) | — | how many studies to open, from the most recent (up to 4) |
| modalitiesInStudy (or modalidades) | — | only studies with these modalities: `CT,MR` |
| lowerDateTime / upperDateTime (or data_de / data_ate) | — | period: `2025-01-01` or `20250101` |
| containsInDescription (or descricao) | — | only studies whose description contains the text (accent and case insensitive) |
| c | — | encrypted link (below) |

A value the program does not understand is refused with a reason ("janela=minimizado: use viewer or completo"), instead of being silently ignored.

### IHE Invoke Image Display

The program understands the **IHE IID** profile (the same as Weasis ViewerHub): `GET http://…:8042/IHEInvokeImageDisplay?requestType=PATIENT&patientID=123&mostRecentResults=2&modalitiesInStudy=CT&token=…` (or `/display`). By patient without a filter it opens the most recent study; with a filter, those that pass (up to 4). The filters also apply when the study is fetched from the PACS. IID parameters the program does not use (viewerType, diagnosticQuality, keyImagesOnly) are accepted and ignored.

### Encrypted link

The ordinary link carries the patient ID in plain text — and the link stays in the browser history. The **encrypted link** is `ipe://open?c=…`: nothing about the patient in sight, only whoever has the **API token** can build it, it opens directly (like the link with the token) and **is valid for 24 hours**. To build it: **Network ▸ External call ▸ Build encrypted link…**, or `ipe-cli link-cifrado "accession=123&node=PACS"`. The RIS builds it the same way, with HMAC-SHA256 (the standard library of any language):

```
key = SHA256(token);  kc = HMAC(key, "ipe-cifra");  ks = HMAC(key, "ipe-selo")
text = "accession=123&t=<seconds since 1970>"
nonce = 16 random bytes;  stream = HMAC(kc, nonce + i in 4 bytes) for i = 0, 1, 2…
encrypted = text XOR stream;  seal = HMAC(ks, nonce + encrypted)[:16]
c = base64url(nonce + encrypted + seal), without "="
```

## What happens with the request

1. The program searches the local database by accession, study UID or patient ID.
2. Found: opens up to 4 studies (1 when the search was by patient ID). With `retrieve`, it answers `ja_no_banco` and downloads nothing again.
3. Not found: searches all configured nodes (or only the named node), answers `buscando` at once and downloads the 4 most recent.
4. Nothing found: the status bar shows each node's error and the answer is `nao_encontrado`.

> **A study called from outside opens while downloading.** It is the opposite of the manual search default, and on purpose: in the external call there is nobody to answer a question. In Network ▸ External call, the box *External call opens the study while downloading*.

## "Viewer only" mode

When the call opens only the viewer, the study appears in a maximized window and the database does not appear — nor is there a path to it from that window:

- the menu bar has only View, User and Help;
- Export, Save measurements as DICOM SR and Send to film are hidden;
- the study opens on all monitors marked as viewer, split by the same criterion as the normal path;
- closing a monitor's window closes the study on all of them;
- when the study closes, the program stays in the tray: the DICOM node keeps receiving and the next call opens at once.

**Another patient with one already open.** If the call brings another patient while one is still open on some monitor, Ipê asks: close the previous one on all monitors, keep both or do not open. In Network ▸ External call, *Call with another patient open* decides without asking. Opening the next with the previous in view is how one patient's image ends up reported under another's name. The film does the same: putting images of another patient on a film that already has images asks for confirmation.

It is turned on in **Network ▸ External call ▸ Open only the viewer (without the database)**, or by a call with `janela=viewer` / `janela=completo` — the parameter rules over the setting.

> **This is not user control.** Whoever has access to the machine can still open the program through the shortcut. For a workstation where the operator sees only what the RIS sent, combine this mode with a user without search and export permission (chapter 14).

## Configuring the HTTP API

Network ▸ *External call* block:

| Field | Note |
|---|---|
| Local HTTP API on | by default, on |
| HTTP port | 8042 by default |
| Token | generated automatically on first run; Generate new and Copy buttons. With no token configured, every call gets 401 |
| Accept calls from other computers | off, the API listens only on 127.0.0.1. On, it accepts only the IPs in the list |
| Allowed IPs | separated by commas |

Only GET is accepted. Every value goes through a sieve of characters and length; everything that arrives by link or HTTP goes to the log with its origin.

## Installed and portable

The package brings two executables: `Ipe.exe` (the windowed one) and `ipe-cli.exe` (the console one) — on Windows, a windowed program has no standard output, so the commands that answer with text need the second. In the portable version (ZIP), everything works the same, except the `ipe://` link, which does not come registered — run `ipe-cli register-url` once.

### Language

Since 0.99.33 the default is **English**. The Windows installer asks the language on the first screen (English, Portuguese or Spanish, with English checked) and records the choice for the program; the `instalar.bat` and `instalar.sh` scripts ask the same. The portable version asks the first time it opens. Afterwards, **Settings ▸ System ▸ Language** changes it, and on the command line: `ipe-cli set-language pt-BR` (or `en`, `es`). Whoever already used the program stays in the language they had chosen.

The translation covers the screens, menus, messages and the AIs. What comes from the study stays as it is (series description, institution, patient) and so do the acronyms. The names of the DICOM series that the AIs create ("Encéfalo", "Lesões hepáticas"… — the program recognizes them by name), the batch spreadsheet headers, the keyword lists and the report templates also stay in Portuguese. In 0.100.118 all windows, menus and messages were checked in English. Found a Portuguese text on the screen in English or Spanish? **Settings ▸ System ▸ Language ▸ Edit translations** fixes it on the spot, and it is worth letting us know so it enters the next version.

# DICOM network, PACS and automation

## Nodes and receiving

**Settings ▸ Network ▸ DICOM nodes…**. The *This computer* tab defines the AE title, the port and who can connect — that is how the device or the PACS sends studies here. The other tabs register the remote nodes.

![Settings ▸ Network ▸ DICOM nodes, This computer tab: the DICOM node and the external call.](config_rede.png){75}

### Two kinds of node: DIMSE and DICOMweb

In a node's record, the first field is **Connection type**, and it changes the fields that follow:

| | Classic DICOM (DIMSE) | DICOMweb (HTTP) |
|---|---|---|
| How it talks | C-FIND, C-GET / C-MOVE, C-STORE | QIDO-RS, WADO-RS, STOW-RS |
| Identification | AE title on both sides | username and password, OAuth2 / OIDC or token |
| Needs an open port here? | only with C-MOVE | no |
| Crosses firewall and proxy? | hard | yes, it is HTTP |

The DICOMweb address is the base, usually ending in `/dicom-web` (for example `http://192.168.1.216:8042/dicom-web`). **Test network** works on both.

> **Three things about DICOMweb.** There is no C-MOVE there: the download comes back over the same connection. An AE identity does not apply to a DICOMweb node — the login is what identifies. And the password, the token and the client secret are kept **encrypted** on this computer (on Windows by the system's own protection; on the others, by a local key in the settings folder): a database copied to another computer does not open the passwords — type them again there. Passwords saved before 0.99.55 are encrypted the first time the program reads them. Use a read-only user when the PACS allows it.

**Authentication** of the DICOMweb node:

| Option | When to use | Fields |
|---|---|---|
| Username and password (Basic) | Orthanc, dcm4chee without central login | username and password |
| OAuth2 — client credentials | cloud PACS, integration between systems | token / issuer, client ID and secret, scope |
| OAuth2 — username and password (Keycloak) | dcm4chee-arc or Orthanc with Keycloak, each physician with their own login | token / issuer, client ID (and secret), scope, username and password |
| Fixed token (Bearer) | the PACS handed over a ready token | the token, in the Password / token field |

In **Token / issuer** goes the *token endpoint* (ends in `/token`) or just the address of the **OIDC issuer** (in Keycloak, `https://login.example/realms/pacs`): the program reads `/.well-known/openid-configuration` and finds the endpoint by itself. The token stays in memory until close to expiring and is renewed without asking for the password again; if the PACS refuses (401), the program asks for another one once. **Test network** already does the login.

| Node field | What it is for |
|---|---|
| Name / AE Title / Host / Port | identification of the remote node |
| Use in search | it enters the search when no node is named |
| Use in priors | it enters the pre-search for prior studies |
| Use in sending | it appears in the list of destinations of "Send to" |
| Retrieval | C-GET (the images come back over the same connection) or C-MOVE (the PACS opens a connection back and needs this computer registered) |
| Open while downloading | per node; empty = uses the preferences default |

### Identities: speaking "as" another device

Some modalities only talk to those they know — the room's OsiriX, for example. In **Settings ▸ Network ▸ DICOM nodes…**, **Identities** tab, you register those AEs (name, AE title, C-MOVE destination and on which nodes they can be used). Then:

- in the PACS search, the **As:** field chooses which identity to search and download with;
- in **Send to ▸ node ▸ as…**, the chosen identity is the one that sends.

### When DICOMweb complains

| Message | What to check |
|---|---|
| HTTP 401 — username or password refused | the node's username and password |
| HTTP 403 — access denied | the user exists but has no permission for this operation |
| HTTP 404 — address not found | the base: /dicom-web is missing or extra, or the port is wrong |
| the certificate was not accepted | HTTPS with a self-signed certificate: check accept unverified certificate |
| I could not talk to the server | address, port or route |

## Search and download

**PACS** button (or Ctrl+Shift+F). Search by patient, ID, accession, date and modality, in one or several nodes at once. The result brings the series, and you can download series by series — this depends on the PACS answering the series C-FIND; when it does not, the download is of the whole study.

Right-click on the search results:

| Item | What it does |
|---|---|
| Download to ▸ | the study (or the checked series) goes **from the node directly to another destination**, without passing through this computer: a C-MOVE requested from the source node, with the *As:* identity. **Other AE…** accepts an unregistered destination. The source node decides whether it accepts the destination |
| Send to ▸ node ▸ as… | downloads the study here (if it is not yet) and, when done, sends it to the chosen node with the chosen identity. A study already complete here goes out at once |
| Download directly to the client | only on the **Ipê client** (0.100.110), for the central server's nodes: the node sends to the server, the server passes the study to **this computer's** database and deletes its copy when the study arrives complete here (up to 3 attempts for what is missing). What was already on the server before the download stays there. The server does not run the arrival rules on a pass-through study; this computer's run when it arrives. It is also a button beside *Download and open* |

The download uses the **As:** identity of the search; sending uses the one chosen in the menu — they are two, on purpose. The tasks appear in the transfer queue, with progress, cancel and the reason for each error ("X does not know destination Y: it needs to be registered in X").

### Batch from a spreadsheet (0.100.97)

**Network ▸ Batch from a spreadsheet…** does the same with each study on a list: finds, downloads, runs the AIs, sends, prints and exports — and writes a spreadsheet with the results. It serves for studies (validating the AIs against the reports, density × calcium score) and for mass work (running emphysema on all of a month's chest CTs, sending the results to the PACS).

The window has five steps (on the left) and, at the top, the **templates**: choose one and press **Use**; **Save as template…** keeps the configuration to repeat it (without the spreadsheet). To only bring the list's studies into the database, without running any AI, use the ready template **Download only** (0.100.115): no AI, not even the automatic one on arrival (*Downloaded study: apply the arrival rules* unchecked), and the studies stay in the database at the end.

1. **Spreadsheet**: CSV/TSV, XLSX or ODS (the old `.xls`: save it as `.xlsx`). Ipê chooses the tab that looks like a list and guesses each column's type from its title — **patient ID, accession number, exam date, Study Instance UID, birth date, name, modality, description**; what it does not recognize stays as *other information (keep)*. Check it in the preview and change it in the selector above each column. *Other patient data* marks a column that must leave the anonymized spreadsheet (phone, address…).
2. **Finding the study**: in **Search by (in order)**, check and order the attempts — **Study UID**, **accession number**, **ID + date + modality**, **ID + date**, **ID + modality (any date)**, **ID only (any date)**. Ipê tries the first checked; if it does not find it, the next (by default: UID, accession, ID + date + modality, ID + date). A row with only the ID, without a date, is only done with "ID only" or "ID + modality" checked. The **Ipê: found by** column says which attempt found it. Adjust the **date tolerance** (± days), the **modalities** (empty = any), **description contains**, what to do if it finds **more than one study** (the one with the most images, the closest to the date, or all) and whether it checks the **birth date** (different = another person with the same ID: not used).
3. **From where**: first Ipê's database; if the study is not there, the **checked nodes, in the order** of the list (drag or Up/Down) — it downloads from the first that has it. The ID saved with or without leading zeros is found anyway.
4. **What to do** (everything optional):
   - **Run AIs**: check which. The one that does not suit the study is skipped, with the reason; the one the study already has does not run again (unless with *Run again*). The mammography ones (density, calcifications) run right here; the others go through the AI queue (they appear in *AI tasks*).
   - **Check the MRI protocol**.
   - **Send** to nodes: the originals, the AI results or both.
   - **Print** the AIs' **check series** (the density and calcification table, the liver stiffness mosaic, the emphysema…) to a print destination or a DICOM printer — one image per sheet.
   - **Export** to a folder: the check series as **PNG** or **one PDF per study**, and, if you want, **the DICOM generated** by the AIs.
   - **Delete from Ipê, at the end, the studies downloaded only for the batch** — what was already in the database is never deleted.
5. **Run**: the **output spreadsheet**; **Anonymize the output**; **Only run between** (e.g. 20:00 and 06:00 — outside that the batch waits); **How many rows now** (start with 5 or 10). **Simulate** only searches and counts (it neither downloads nor runs anything): use it before a large batch to see whether the columns are right. **Start** / **Stop**.

**The output spreadsheet**:
- **Results**: the original columns and, beside them, Ipê's (status, Study UID, accession number, date, description, where it came from, AIs, protocol, sent, printed, exported). With "all studies", one row of the list becomes several.
- **AI · …**: one tab per AI, with each study's numbers (density with the A to D probability; calcifications with the area and scales; the liver with PDFF, R2* and stiffness; …).
- **Summary** and **README**.
- **Anonymized**: without ID, name, birth date, accession and UID (*Case 0001*…); the correspondence stays in a separate file (`…-chave.xlsx`), which must not leave the institution. In the anonymized export, images that carry the patient's name written on them are left out.

**Not found**: the note says why — the node's error, the studies the node returned and the filter removed, or (searching again by the ID only) whether the patient has studies on other dates/modalities, with the closest ones. Use the Simulation to get the columns and the tolerance right before running for real.

**You can stop and continue**: choose the same output spreadsheet and the batch continues from where it stopped (the *not found* and the *with error* are tried again, if the box is checked). The window shows no patient name — only the row number and the result.

- **On the Ipê client** of a central server, the batch **runs on the server**: the nodes are those the server shares with the clients, the AIs and printers are its own. The window is the same; it follows the progress and, at the end, downloads the spreadsheet (and the key, if anonymized) to the chosen path and the exported files to the chosen folder. You can close the window: the batch continues on the server — send it again with the **same output spreadsheet** (the batch's name is its name) to continue or follow it. Check **Also bring the studies to this computer** to have each study done in the local database; if the batch deletes what it downloaded, the server only deletes after the copy.
- **On an Ipê with its own database** (including the server's own), the batch runs right there.
- **Permissions**: search and download; send, print and export when checked (exporting with identification asks for *export identified*).

> These are **automatic measurements, without confirmation**. Before analyzing, **check a sample** — open a few studies by Study UID and look at the check series.

## Send

**Send to** is in the right-click of the study list, of the database series and of the PACS results, always with the same submenu: one item per node marked *use in sending*, and in each node *as this program* or *as* an identity allowed on that node. On series, only the selected ones go. The queue and the access log say what went, where to and how.

## Automation

**Network ▸ Automation…**:

| Tab | What it does |
|---|---|
| Scheduled searches | searches the PACS by itself at the chosen time and warns or downloads |
| Priors | when a study arrives or opens, searches the patient's priors by your rules |
| Routing | a study that arrives and matches the filter is forwarded to another node |
| Ready dynamic | detects the phases and decodes the frames in the background. Nothing is written and nothing is sent |
| Cleanup | deletes old studies by age, by modality or by lack of use — protected studies never enter, nor do anonymized copies |

The **History** tab shows what each rule did and when.

## Central server (intranet)

**Settings ▸ Network ▸ Central server…** puts an installation in the server role, with login and shared database; the others join as clients. The database is a **PostgreSQL** (next), which handles many workstations at the same time.

### The database: PostgreSQL (since 0.100.36, the only one)

Ipê's database (patients, studies, measurements, reports, lists, users, service settings) is a **PostgreSQL**. **Nothing needs to be installed**: PostgreSQL 16 comes inside Ipê. It starts by itself when Ipê (or `ipe server`) opens, keeps the data in the data folder (`postgres`, beside Storage; changing the database folder takes it along) and shuts down when the last Ipê program on the computer closes. It only accepts connections from this computer — the other workstations arrive through Ipê's central server, as always —, and the password is created and kept by Ipê itself, together with the data. Each location (external disk, another folder) has its own PostgreSQL inside its own folder, and keeps going along with it — between computers of the same system (Windows with Windows, Mac with Mac).

**For those coming from an earlier version:** on the first opening after the update, Ipê moves the old database (the SQLite file `dicomviewer.sqlite`) to PostgreSQL, with a progress window — in a large database, a few minutes, only once. Everything goes along, and each table's count is checked at the end. The old file is kept as `dicomviewer.sqlite.migrado`, in the same folder, as a safety copy (it can be deleted after checking that everything is there). The same applies to the other locations, the first time each one is opened.

The main database can also live on **your own PostgreSQL server** — installed separately, on another computer or in the cloud. In **Settings ▸ Database ▸ Database server (PostgreSQL)…**:

1. Install PostgreSQL (postgresql.org) and create a user and an empty database for Ipê — for example, in `psql`: `CREATE USER ipe PASSWORD '…'; CREATE DATABASE ipe OWNER ipe;`.
2. On the main database computer (the central server), check *Own PostgreSQL server*, fill in server, port (5432), database, user and password and click **Test the connection**.
3. To take what already exists: **Copy this computer's database there…** copies everything from the database in use, table by table, and checks each one's count at the end. The destination database must be empty. Close Ipê on the other workstations first.
4. **OK** and open Ipê again: the window now shows *In use now: PostgreSQL user@server:5432/ipe*.

To go back to the PostgreSQL that comes with Ipê, check the first option (the Copy button brings back what went into the own server). The **images stay in the data folder** (Storage): only the information goes to the database. The own server's password is kept encrypted on this computer (`banco.json`, in the settings folder).

On the server without a window, the same by command line: `ipe banco status`, `ipe banco postgres --host 10.0.0.2 --banco ipe --usuario ipe --copiar` (asks for the password) and `ipe banco embutido --copiar` (back to Ipê's own). The `IPE_DATABASE_URL` variable (`postgresql://user:password@server:5432/ipe`) takes precedence over whatever is configured — for servers set up by script.

![Settings ▸ Network ▸ Central server: this computer's mode (local, server or client).](config_servidor_central.png){65}

**Open while downloading.** On the client, a study that is not yet on the computer opens in a few seconds: first one image of each series arrives (the strip shows all of them and the display protocol assembles the frames), then the rest of each series keeps arriving and the frames grow by themselves. The status bar shows *Downloading from the central server: N of M image(s) (P%)…*. Only the open study (and the prior the protocol asks to compare) is downloaded. Reopening a study that has already arrived is immediate; the cache has the limit set in **Settings ▸ Network ▸ Central server**, and the studies open for the longest time leave first.

**Printing on a DICOM printer through the server (0.100.49).** On the server, open the printer in **Settings ▸ Printing ▸ DICOM printers** and check **Share with clients**. In the client's Ipê, the composer's **Print** window shows that printer as *Name (through the server)*, along with the computer's own DICOM printers; in Ipê Web, it appears in the film Output. The one who sends the sheets to the printer is the server, with **its IP and AE** (the printer's source AE, if filled in) — useful when the printer only accepts a registered IP: register only the server in it. The client does not receive the address or the AE. The film goes as a recipe, the server draws the sheets with the same code and counts the printing in the access log. A DICOM printer that is not shared only works on the server itself (up to 0.100.48 Ipê Web showed all of them).

**Searching the PACS through the server (0.100.37).** On the server, open the PACS node in **Settings ▸ Network ▸ DICOM nodes** and check **Share with clients**. On the client, that node appears in the PACS search as *Name (through the server)*, along with the computer's own nodes (and also in the priors search). Searching and downloading work as always, but the one who talks to the PACS is the server, with its AE title and password — the client does not receive the address or the credentials — and the downloaded study **enters the server's database**, in the database of whoever asked (their own or the shared one). The client's download queue shows the progress of the download on the server, and cancelling there cancels on the server. Searching asks for the search permission; downloading, the download one; everything goes to the server's access log. Ipê Web has the same (next). With a server node chosen, the *As* field disappears (the AE is the server's) and the window says that the search and download are through the server. *Visible to* in the node's record is another thing: it says which users of the server itself use the node. If the server shares no node, or did not answer, the PACS list on the client says so; the list is requested again each time the PACS window opens.

**How much of each series has arrived (0.100.0).** While the study downloads, the thumbnail of each series in the strip shows *34/120 im* with a bar underneath: blue and with ⬇ on the one arriving now, green on those waiting their turn (hover: the position in the queue). The frame shows **⬇ 34/120** under the image number until its series is done. **Putting a series in a frame** (clicking or dragging) moves it to the front of the queue. Two series download at the same time, and what arrives enters the database without stopping the network. If a series does not download completely, the status bar says how many images were missing and why; and the server keeps in the access log (actions *cliente_entrou* and *cliente_download*) each client's version and what each download did (0.100.1).

**Network signal (0.100.1).** On the client, the status bar shows the network to the server: **bars** from 0 to 4 (like a phone's), the **round trip** in milliseconds and the **throughput** in Mbit/s — for example *3 ms · 870 Mbit/s*. The worse of the two counts: four bars ask for less than 10 ms and 300 Mbit/s or more; three, less than 30 ms and 80 Mbit/s; two, less than 80 ms and 20 Mbit/s. The program measures on opening (with a 2 MB test) and on each study opened (only the round trip, so as not to compete with the download for the network; the throughput becomes that of the download itself). Click on the bars to measure again; *no connection*, in red, when the server does not answer.

**Faster to open and to download (0.100.38).** Server and clients on 0.100.38 or newer:

- **The client's download** became about three times faster in the measurement (720 CT slices: from 2.9 s to 0.8 s, server and client on the same machine). The server sends along with each image its data that goes to the database, and the client writes the file straight into place and the database in batches — before, each image was written twice to disk, read again and written to the database one by one.
- **The first image arrives sooner**: the middle image of all the series comes in a single request (before, two requests per series, one after the other), and the rest only starts arriving after the study opens.
- **The connection to the server stays open** between requests (opening a study makes about twenty calls to the server; each one opened a new connection and, in https, redid the negotiation).
- **On the server**, the request for each Ipê Web image became about four times lighter (from 220 to 930 images per second in the measurement): permissions and "who sees this study" are checked once every few seconds, not on every image (a change made on the server takes effect at once); the image with the send copy ready goes out without the original file being opened; and small responses no longer wait for the network's acknowledgment (it was 40 ms more per response on Linux, and up to 200 ms with a Windows client).
- **The data the browser asks for on opening** (each series' metadata) is kept on disk, in the `CacheWeb` folder, and that of today's and yesterday's studies is ready every 2 minutes (that of the last 14 days, every 30).
- With a server of an earlier version, the new client works as before, without the gains.

**Less data on the network (HTJ2K).** The client receives the images compressed **losslessly** in HTJ2K (2 to 4 times less data in a CT; the same image, checked pixel by pixel). The server's archive **does not change** — what goes is a send copy, which the server prepares in the background for the studies of the last 14 days (every 30 minutes, when nobody is requesting images) and keeps in the `CacheWeb` folder, beside the archive (which can be deleted at will). An image that does not yet have the copy ready goes as it is, without waiting. Turn it off in **Settings ▸ Network ▸ Central server ▸ Receive the images compressed losslessly**. Sending one of these images to a DICOM node that does not accept HTJ2K goes decompressed.

### Web viewer (0.99.91)

The central server brings a **viewer in the browser**: on any computer on the network, open **`http://server-IP:8043/web/`** (or `https://…`, with Ipê's certificate) in Chrome or Edge and sign in with the same username and password as Ipê. Nothing needs to be installed. If the browser offers to **translate the page**, refuse: since 0.100.64 the page already asks not to be translated (the translator swapped the texts for nonsensical ones); Ipê Web's language is that of the program itself. The address appears in Settings ▸ Network ▸ Central server, with the link.

In this first phase:

- **Study list** with search by name, ID or accession, by dates and by modality; each person sees only what they can see in Ipê (the same permissions and the personal database). Double-click opens the study.
- **Series strip** with the thumbnails; clicking puts the series in the active frame (yellow outline), or **drag the thumbnail to the frame** you want (0.99.95).
- **Available images** (0.99.95): as soon as the study opens, the browser downloads the series in the background — first those in the frames, then the others, in the order of the strip. Each thumbnail shows the percentage and a little bar until it is ready, and the top of the screen shows the study's total; at 100%, they disappear. If the browser's memory fills up (very large studies), the preload stops and the rest comes when it is shown.
- **Faster loading** (0.99.96):
  - **Fewer bytes on the network**: the server sends each image without compression (and mammography in JPEG-LS) as **lossless HTJ2K**. It is a send copy, checked pixel by pixel and kept in a cache folder (`CacheWeb`, beside the archive, which can be deleted at will); the archive file does not change. In a CT, it goes from 2 to 5 times less.
  - **Progressive loading**: the large image appears first in a smaller version and gains definition while it arrives. The volume (MPR) comes interleaved: 1 in every 4 slices first, and it is completed right after.
  - **Browser cache**: reopening a study only checks with the server whether the image changed (the password still applies); almost nothing goes over the network.
  - Decoding uses all the computer's cores but one, and the series metadata goes compressed.
  - **All series start at once** (0.99.99): the browser asks for the information of all the series at once (not one after the other), the server reads the headers in parallel and already prepares the whole study as soon as it opens; the next series no longer waits for the previous one. The send copies made in the background wait while the browser is requesting images, so as not to compete with them for the processor.
  - **Load** (bar): shows how many images and how many MB came over the network, in how long (MB/s), how long the browser took to decode each one, in what format they came and how many came from the cache. It serves to know whether what weighs is the network or the computer.
- **Frames** from 1×1 to 4×4 (layout icon: hover over the grid and click) and ready protocols (MPR, PET/CT). **Ready windows** (yours, by modality) in the **Image** tab and in the right-click menu.
- **Formats**: HTJ2K (the send copy), JPEG-LS, JPEG 2000 and JPEG are decoded in the browser itself; what is in other formats (color, stored JPEG 2000) goes as it is in the database. Mammography uses the device's window (including the sigmoid).
- **Security**: nothing of the patient is saved in the browser; reloading the page asks for the login again and an idle session ends by itself. Each study opened goes into the access log ("opened in the browser"). On the internal network, use HTTPS with Ipê's certificate.

**The screen (0.99.97), Weasis-style.**

- **A bar of icons** (hover to see the name). Icons with a small arrow open a menu: the ROIs (elliptical, rectangular, freehand) and the angles (angle, Cobb) show the chosen tool; click the arrow to change.
- **Each mouse button with its own function, as in Ipê**: click the function's icon **with the mouse button that should do it** — with the left, it goes to the left; with the middle, to the middle; with the right, to the right. The yellow mark under the icon shows which: left, middle or right (a function can be on two buttons). The footer summarizes the three, and the choice is saved in the browser. The wheel still scrolls the slices.
- **Right button**: **click and hold** (dragging) does its function — by default, zoom; **click and release** opens the **image menu**: Window (the ready ones, the file's, invert), Zoom (fit, 1:1, 2×), Rotate and mirror, Plane (Original, A, C, S, MIP), Button functions, Series, Frames and cine, Delete the image's measurements and Restore. On top of a measurement, the menu starts with it: copy the value, edit the text (arrow) and delete.
- **Left panel**: the series (with the percentage downloaded) and the patient's **prior studies** (click to open). **Right panel**, in tabs: **Image** (ready windows, invert, rotate, mirror, zoom), **Measurements** (all of the study's, with the value and who measured; click to go to the image; copy and delete), **DICOM** (the tags of the active frame's image, with filter) and **PET** (SUV, color, opacity, window top and segmentations). Both panels collapse (the arrow at the top) and open again from the thin strip that stays in their place.
- **Footer**: available images, network speed and decoding, **Load** (the full panel) and each button's function.
- **Measurements in two clicks (0.100.3)**: the ruler and the other measurements also draw as "click, move, click". A line started and not finished is undone by clicking in another frame, changing tool or pressing **Esc** — the mouse never gets stuck.
- **Double-click enlarges (0.100.5)**: double-click on a frame takes it to 1×1; another double-click returns to the previous arrangement, with each frame as it was (slice, zoom, window). A double-click on a measurement still belongs to the measurement.
- **List with quick filters and preview (0.100.20)**: above the list, three rows of buttons — **Period** (Today, Yesterday, 7 days, 30 days, All, Other period…), **Modality** and **Status** (No report, Draft, Signed, With AI to review) — filter with one click and are remembered. Beside the name, the **AI** badge (stronger when there are findings waiting for review) and the report's (**R** draft, **L** signed). **One click** on a study shows the **preview** on the right: the series (with the AI badge), the study's AI and the findings by state, the report (state, date and the start of the text) and the patient's prior studies, with the **Open the study** button; the ↑↓ arrows move through the list. **Two clicks** (or Enter) open, as before.
- **Linked windows (0.100.20)**: in the viewing windows, the chain icon **Link the windows** (on at the start) makes the scrolling, window/level and zoom of one window follow in the others: in the same study, by position in the patient (frames in the same plane); in the **prior study** window, moving the same millimeters — turn it off, align the two studies and turn it on again. **Since 0.100.21**, with the windows linked, the slice you scroll in one window appears in the others as a **light-blue dashed reference line** (in frames of another plane of the same study — for example, the axial of one window over the sagittal or the other's scout); and you can **drag a series from one window's strip and drop it on a frame of another window**, even of another study (the comparison window).
- **Viewer appearance (0.100.19)**: the **Appearance** icon (end of the bar) chooses where the **series** go (left, bottom or top — in the last two, a strip that scrolls sideways and leaves the full width for the images) and the **buttons** (on top, or in a column on the left, which gives the bar's height back to the image). **Reading mode** (the icon beside it, or the **F** key) hides the bar, panels and footer and leaves only the images; **Esc** or **F** goes back. The right panel (Image, Measurements, DICOM, PET, Film, AI) comes **collapsed**; the small arrow on the edge opens it. Everything is saved in the browser.
- **Monitors and windows (0.100.19)**: the **Monitors** button, in the list, opens the configuration (saved in the browser, like Ipê's Monitors tab): studies **in this window** or in **separate windows**; for each window, the **order** (▲▼ — Window 1 starts at the first series, 2 at the following ones), what it **shows** (the study, the **prior study** for comparison, or not used), the frames' **layout** and the **monitor**. *Detect monitors* (Chrome and Edge, over HTTPS or on the computer itself) lists the monitors from left to right, and each window opens on the chosen monitor; without that, drag each window to its place once — the position is saved.
- **Real monitors (0.100.55)**: with the browser's permission (Chrome and Edge, with Ipê Web over **HTTPS** or opened on the server itself), the panel **detects all the monitors by itself** — however many there are, each with its resolution and orientation (landscape or portrait) — and shows one row per monitor: this window's keeps the list, and for each of the others you choose **study**, **prior study** or **not used** and the layout; the windows are numbered from left to right. Without the permission (for example, Ipê Web over HTTP across the network), the browser does not say how many monitors there are: choose **how many viewing windows** you want (1 to 8) and drag each to its monitor once. The desktop Ipê already detects all the monitors (Preferences ▸ Monitors).
- **Linking in a single window (0.100.55)**: the same chain icon (**Link the frames and windows**) also appears when the study opens in this window: the screen's frames scroll together (those in the same plane, by position in the patient; a prior study moves the same millimeters), with the same window/level (same modality, not in mammography) and the same zoom. In a single window it starts off; with separate windows, on.
- **Several windows, one per monitor (0.100.18)**: in the list, the box **Open in this window / 1, 2 or 3 viewing windows** chooses where the studies open. With viewing windows, the list stays in its own window (monitor 1) and each study opens in the other windows (monitors 2, 3…), for any study — as in Ipê. The windows stay open between one study and another: **Close** in one of them closes the study in all, and they wait for the next; **Exit**, in the list, closes all. The 2nd window starts at the series following those of the 1st; in mammography, the 2nd window is the protocol's second screen. **The first time**: (1) the browser only lets one window open per click — allow the *pop-ups* of the server address (the icon that appears in the address bar); (2) drag each window to its monitor: the position and size are saved. In Chrome and Edge, over HTTPS, the browser asks whether it may *manage windows on all screens*: if you accept, each new window already opens on a monitor, filling it completely.
- **Phone and tablet (0.100.18)**: on a phone the list becomes cards (one tap opens the study) and the viewer shows one image at a time, with the toolbar scrolling sideways; **Series** and **Tool panel** (the first two icons) open the panels as drawers over the image. Gestures: **one finger** does the function chosen on the bar (at first, scroll the slices), **two fingers** pinching zoom and pan, **three fingers** move; holding the finger opens the menu. On a tablet in landscape the layout is the computer's, with narrower panels. The session now survives page reloading (the phone reloads by itself) and ends when the tab is closed.
- **Close and exit (0.100.5; 0.100.15)**: with a study open, **Close** (top corner) closes the study and returns to the list; in the list, **Exit** leaves Ipê Web. Closing or reloading the tab with a study open asks for confirmation.
- **The search comes back (0.100.15)**: on closing the study (Close or ← Back), the list returns with the same search and the same filters (name, dates, modality), with the study that was open marked. It applies to that browser tab; **Exit** forgets the search.
- **Study list (0.100.2)**: click on a column title (Date, Patient, ID, Description, Modality, Images) to sort; click again to reverse (▲ ascending, ▼ descending). The choice is remembered in the browser.
- **Overlay (0.100.2)**: the **Overlay** icon turns on and off, all at once, everything on top of the image — the **CAD/AI** findings (SR), annotations from another system (**GSPS**), radiotherapy contours (**RTSTRUCT**), the corner texts, the measurements and the reference lines —, like Ipê's CAD/AI button. The small arrow beside it chooses item by item: each type of object (what you hide stays hidden in the next studies), each object, the corner texts, the measurements and the reference lines. The objects are read on the server by the same reader as Ipê; the measurements that Ipê itself saves do not appear twice. The SEG chosen in the segmentation icon also appears in the slice frames.
- **CAD/AI in the overlay (0.100.14)**: in the Overlay's small arrow, **CAD/AI (findings, segmentations, levels)** turns only the AI on and off — the findings, the SEG on the slices and the level names —, without touching the texts and measurements; the choice is remembered. The **spine levels** (C1…S1, vertebrae and discs) and the **lymph node levels** appear as in Ipê: in any series and plane, including the MPR (on a sagittal, all of them; on an axial, the level of that slice).
- **Reference lines on the slices (0.100.2)**: with two or more slice frames, the **active** frame's plane appears as a line in the others (an axial on the scout, a sagittal on the axial…). With the **Reference lines** tool on a mouse button, clicking (or dragging) in a slice frame takes the other frames to that point's slice — Ipê's localizer. **Since 0.100.58**, the clicked point appears as a **yellow cross** in all the frames whose slice passes through it (like the desktop Ipê's Shift), in the exact place on the image; scrolling far away hides it, and **Esc** removes it. Going to an AI finding marks the point the same way.

**Volume: MPR, oblique and MIP (0.99.92).**

- **Change the plane with one click**: at the top of each frame, **A**, **C** and **S** reconstruct the series in that plane (axial, coronal, sagittal), **MIP** puts the rotating MIP and **Original** returns to the slices as acquired.
- **MPR** (bar): the active frame becomes four — axial, coronal, sagittal and the rotating MIP — with the **reference lines**. The left button becomes "Reference lines": dragging the center takes the other planes to the point; dragging a line's end rotates the line, and the other frames become **oblique** planes.
- **Oblique** (bar): two clicks in the active frame mark a line; the other volume frame becomes the plane containing that line, perpendicular to the plane where it was drawn (like Ipê's oblique).
- **Thickness**: 3, 5, 10 or 20 mm, in **MIP**, **MinIP** or **Average**, in the active volume frame; the corner says the plane and the thickness.
- **Rotating MIP**: **Rotate MIP** turns on the rotation around the patient's axis; the mouse wheel over the MIP rotates it gradually. **Clicking a point on the MIP** takes the other frames to the brightest point along that line of sight. In CT the MIP opens with a wide window; in PET, inverted.
- A series that does not make a volume (single image, slices with different orientations or sizes, several frames in one file) stays in slices, with the reason warned. Volumes larger than 1.5 GB are not assembled in the browser.

**Measurements (0.99.93).** On the bar: ruler, angle, Cobb, elliptical, rectangular and freehand ROI, pixel, arrow and calibration (on any mouse button).

- **The number is Ipê's**: the same scale (this image's calibration, then the series', the ultrasound region and the file's spacing), the same ROI rule (the pixel counts if its center is inside) and the same text — mean ± SD, minimum and maximum, area.
- **They stay in the server's database**, in Ipê's format: what is measured in the browser appears in Ipê (and what was measured in Ipê appears in the browser), with who measured. Moving an end updates the measurement; to delete, right-click the measurement (menu ▸ Delete this measurement) or use the **Measurements** tab. It only applies to the slice frames ("Original"): in the MPR the measurements stay on the screen only, as in Ipê.
- **Ultrasound**: the distance uses the device's own calibrated region; a ruler that crosses two regions (from the 2D to the Doppler, for example) stays in pixels. **Calibration**: draw a known distance and type the millimeters — in ultrasound it only applies to that image; in the other modalities, to the series.

**PET/CT (0.99.94).**

- **PET/CT** (bar): PET reading as in Ipê — the **fusion** (the soft-tissue CT with the PET on top), the **PET** in inverted gray and the **PET MIP**. The two axials move together (slice, zoom and position); clicking on the MIP takes the slices to the brightest point. The program chooses the active frame's PET (or the largest in the study) and the largest CT.
- **SUV by Ipê's calculation**: the PET reaches the browser already in SUV (by weight, with the dose and times from the file); without weight or without radiopharmaceutical data, the warning says what is missing and the values stay in Bq/ml. The ROI and the pixel value on the PET bring the SUVmax and SUVmean as in Ipê.
- **Fusion color** (Ipê's tables: Hot Iron, PET, rainbow…), **opacity** and **SUV window top**. What is below 8% of the window is not painted, as in Ipê.
- **PET window on the mouse (0.100.2)**: with window/level on a button, drag on the PET, the MIP or the fusion — **up and down changes the top**, **sideways the floor** —; the window applies to all the frames of the same PET and appears in the corner (*SUV 1–9*). On the fusion, **Shift + drag** adjusts the CT underneath.
- **PET/CT arrangement (0.100.2)**: in the **PET** tab, choose the grid (1×1 to 2×3) and what each frame shows — **CT + PET**, **CT**, **PET** or the **PET MIP (3D)** — and the plane (axial, coronal, sagittal). The arrangement is remembered for the next PET/CT; **Default arrangement** returns to fusion, PET and MIP.
- **Maximum SUV near the cursor**: choose the icon (with the mouse button you will use) and click near the lesion in a PET volume frame (the fusion, A, C or S): the program finds the hottest voxel within a 3 cm sphere and takes the slices to it; the value appears in the corner.
- **Segmentation (SEG)**: the segmentations saved in the study (the tumor burden, the organs and lesions from Ipê's AI) appear as colored masks in the volume frames, with Ipê's colors. Since 0.100.112, the most recent one from the AI already appears when the study opens (as in the desktop Ipê); the others stay in the segmentation button. The **measurement lines** of the cavum cephalometry and the skull indices also appear, in any plane that contains the line.

**Mammography with one and two screens (0.99.98).**

- The mammography study **opens in Ipê's protocol** (yours, from Settings ▸ Mammography, or the default): the **Mammography** bar above the images says the protocol and the step (**4 views**, CC, MLO, current × prior…). The arrows move between steps; clicking the step's name opens the list. The protocol can also be changed there.
- **The same rules as Ipê**: each frame's image (the presentation one, the most recent), the patient's **prior study** in the "prior" frames (with the date in the corner), the breasts **back to back** (mirrors when the chest wall came from the other side), the **framed breast** (air is left out), the wall against the edge, the same zoom on both and the **nipples at the same height**.
- **Double-click** enlarges the frame; another double-click returns. **Each frame is a stack of the view, as in Ipê (0.100.2)**: the mouse wheel goes through all the 2D images of that breast and view and then through the tomosynthesis slices. **Frame tomosynthesis** (bar) jumps from the 2D to the middle of the tomo and back. **When scrolling from the 2D to the tomo (0.100.4)** the new image stays at the same scale in millimeters and with the chest wall in the same place, even with manual zoom — the tomo has another size and another spacing. **Since 0.100.17** the framing from the opening of the step applies to all the images of the stack, as if they were piled up: going back and forth with the wheel returns exactly the zoom and position from before (the pixel size comes from the server, which reads the 2D's ImagerPixelSpacing and the tomo's functional groups). Manual zoom becomes the new framing for all of them.
- **Magnifier (0.100.4)**: **Magnifier on the left button** (bar) — hold the button and move over the image: the circle shows the image's own pixels enlarged (not the screen's), with the frame's window; the wheel, with the magnifier open, changes the magnification (1.5× to 8×, remembered). The same button returns the previous function. The magnifier is also in **Zoom and magnifier**, for any mouse button and any study.
- **Quadrant zoom (0.100.77; four areas since 0.100.78)**: the **Quadrant zoom** button on the mammography bar (or the **Q** key; **Shift+Q** goes back) enlarges all the frames of the step together, each on its own side, as in the desktop Ipê: posterior and superior → anterior and superior → posterior and inferior → anterior and inferior → the whole breast. The chest wall stays against its edge and the two breasts stay mirrored; scrolling the tomosynthesis keeps the quadrant. Changing step returns to the whole breast; with two screens, the second follows.
- **Synchronization in mammography (0.100.78)**: in Ipê Web's mammography mode, scrolling, zoom and what comes from another window do not move together by default. Quadrant zoom stays on the frames together by default (**Quadrant together** button to turn off). The frame-linking button, in mammography, turns on and off only its own synchronization (saved separately); each image's window never passes to the others.
- **Two screens**: opens a second browser window with the other half of the step — the CCs on one screen, the MLOs on the other, for example, as Ipê splits it. The second window enters without asking for the password (it receives the first's session), and the two change step together. In Chrome and Edge with the "window management" permission, it already opens on the other monitor; without the permission, drag it there. Closing the second returns to one screen. If the browser blocks the window, allow windows from the server address.
- **Leaving mammography mode** (bar) returns to the ordinary viewer. Reading in the browser depends on the monitor: to report, use the calibrated monitor (DICOM GSDF).

**Breast dynamic (0.99.98).**

- **Breast dynamic** (bar, on MRI studies): the server finds the phases as Ipê does (the dynamic's series, or one series with all the phases) and the browser assembles four frames — the **initial phase**, the **kinetic map**, the **SER** and the **subtraction** — which move together through the slices. Each frame can show another map: MSI, PEI, initial enhancement, time to peak, temporal MIP and mean.
- **The maps are calculated in the browser, slice by slice, with Ipê's calculations** (the same thresholds, the same noise and the same tissue mask; checked pixel by pixel in the tests). The pre, initial and late phases are switched on the bar.
- **Over the phase**: a calculated map or a map that Ipê **has already saved as a series** ("SER (dynamic)", "Kinetic (dynamic)"…) goes on top of the initial phase, with Ipê's color table and the bar's opacity; what has no value stays transparent.
- **Time-intensity curves**: draw an ROI (ellipse, rectangle or polygon) or mark a **point** (pixel value, 3×3 mean) in any frame; underneath appears the curve and the table with the **class** (medium/rapid × persistent/plateau/washout), the initial enhancement, the SER, the peak, the TTP, the BAT, the washout, the iAUC90 and the MRT — Ipê's numbers.
- **Curve under the cursor (0.100.2)**: as in Ipê, hovering the mouse over the image shows the point's curve (3×3 pixels), dashed, along with the saved ones; the **Curve under the cursor** box on the bar turns it off.
- **Each frame's label (0.100.2)**: in the phase frames, **◂ ▸** move between phases; clicking the text (or the right button) opens the frame's menu — what to show (any phase or map), **Subtraction (phase − pre-contrast)** of any phase, **Landscape** (10 to 50% of the anatomy back in the subtraction, as in Ipê) and the **color** (Ipê's tables, or gray). The bar also chooses the **map color over the phase**.
- **Motion correction (0.100.8)**: the motion correction selector on the bar — **No correction**, **Translation** or **Rigid** (with rotation), as in Ipê. The server does Ipê's calculation (each phase's 3D translation over the pre and, in rigid, the rotation of the phase that rotated) and the browser applies it when assembling each slice: the maps, curves, subtractions and the frame of the phase that moved come out corrected. The selector's hint says how much moved (the largest shift and the largest rotation). It comes on as you left it in Ipê; changing the pre redoes the calculation.
- **Dynamic series (0.100.58)**: the **Series…** button on the bar lists the study's MRI series, with those that entered checked; check the pre and the post-contrast ones (or a single series, with repeated phases) and **Use these series** — the dynamic opens again with them (motion correction too). **Detect automatically** returns to detection. When the server does not find the phases, the same list opens for you to choose.
- **Layout and what goes in each frame (0.100.58)**: **Layout** on the bar (1 × 1 to 3 × 3); the frames that were there stay, and the new ones come with the late phase, the late subtraction, MSI, PEI and TTP. In each frame's label, **Show** chooses any phase, the **Subtraction (phase − pre)**, a map or, in **Study series**, any series of the study — a series that is a dynamic phase becomes the phase; the others (T2, diffusion…) move along with the dynamic by position in the patient, even with another thickness. A series put in the frame by the series list (without going through the label) is handled the same way (0.100.60). A series of **another plane** (sagittal, coronal) does not move by scrolling: the click of the **Reference lines** takes it to the point, and it stays there while you scroll the dynamic (0.100.59). In the **subtraction** the **◂ ▸** move between phases in the frame itself, as in the desktop Ipê — the default fourth frame is the initial phase's subtraction.
- Only in Ipê, for now: phases left out of the calculation and the baseline by the mean of the pre phases.

**Searching the PACS and downloading (0.100.37).** In the study list, the **Search the PACS…** button appears when the server shares some node with you (see *Searching the PACS through the server*, above). Choose the node, fill in name, ID, accession or a period (a search without filter is not accepted, so as not to burden the PACS) and click **Search the PACS**. Each study in the result has **Download** — the server downloads to its database, into yours — or **Open**, when it is already on the server. Underneath, **Downloads through the server** shows the progress of each one, with **Cancel** and, at the end, **Open the study**.

In 0.100.80: **Today** and **Yesterday** set the date and already search; **Study no.** searches by the study number in the PACS (the *Study ID*; if your PACS calls the accession number the study number, use **Accession**) — the table shows both columns; and clicking on a column title sorts by it (▲ ascending; click again, ▼ descending).

**DICOM Management in the browser (0.100.63).** For **administrators**, the study list gains the **DICOM Management…** button — the same routine as the desktop Ipê's window (see *DICOM Management: are the modalities' studies in the PACS?*), served by the server:

- **The one who talks to the modalities and the PACS is the server**, with its AE Title or with the identity chosen in *Speak as*. The equipment and the PACS need to accept the server; each row's **Test** button does a C-ECHO and says whether the node answers.
- **All the server's active DIMSE nodes** appear — here there is no need to check *Share with clients* on the node.
- Check the modalities, choose the PACS, the period, what to ignore and **Check**. The table brings each study's status (complete, incomplete, missing, with another UID, no count, error); clicking on the row opens the series. **Only those with a problem** filters; **Check those with a problem** selects.
- **Send what is missing** and **Send the whole study** send to the checked PACS; the two **…to ▾** send to another sending destination of the server (what is missing is counted there). The **Send queue** shows each study; after sending, the study is checked again. **Export CSV** saves what is on the screen.
- **Everything runs on the server**: you can close the page — the check and the sending continue, and on returning (you or another administrator) the screen shows the same state. One operation at a time. Checks and sends go to the access log, with the user.
- The choices are kept on the server (the same as the program's Management window on the server computer).
- **Automatic tab (0.100.65)**: the rules with a schedule, the same as the desktop Ipê's window (they are in the database). **New rule…** / **Edit…** open the editor: name, on, modalities (with *Speak as*), destination (*Send as*, C-MOVE destination), send only what is missing or the whole study, how to send, period, a single modality, series to ignore, image by image; **When** — every N minutes between two times, or every day at a time, on the checked days of the week; and *try again* in X minutes, up to N times, if there is an error or a node is down. In the list: turn on/off in the box, **Duplicate**, **Delete** and **Run now**. Underneath, the **last report** of the chosen rule (completed now, with error, modalities down, same accession with another Study UID) and the **history**. The rules run on the server while it is on; do not leave the same rule on in two programs at the same time (the studies would go twice).

**Prints and Panel in the browser (0.100.68).** For **administrators and technologists**, the study list gains the **Prints…** button — the desktop Ipê's *Prints* tab, served by the server (the one who draws the sheet, reads the header and talks to the printer is the server, with its IP and AE):

- **The list**: what arrived through the DICOM printer, what was assembled in the composer and the film that came inside the study, with the same columns and the same *Status* (In the list, Sent, Error, Waiting for patient, Stopped: device not registered…). The search box filters by patient, ID, origin or label; the list beside shows only those received, assembled, sent or **stopped**. Click on a row to choose; the boxes on the left (or Ctrl + click) choose several. The list refreshes by itself every 20 seconds.
- **The sheet**, beside it: the preview of each sheet (◀ ▶), **Enlarge**, the job's data and the **sending history** (when, to where, who, how — by hand, by the rule or reprint — and the result).
- **Identify patient…**: the name and ID, the studies from the same device and time to choose from and the **Read the sheet header (OCR)** button, which reads the top and footer of the first sheet and looks for the patient in the database — it is a suggestion: check before confirming. On confirming, the film **follows the rule**, as in the desktop Ipê. The OCR is the server's: if it is not installed there, the button says why.
- **Send to…**: all the **destinations registered on the server** (Print settings ▸ Destinations) — *Share with clients* does not apply here —, with the **sheet template**. **Reprint…** sends again to the last destination that worked, after showing the plan.
- **Join as pages** (two or more received), **Open the study**, **Delete** (asks first; studies kept in the database are not deleted) and **Stopped…**: the jobs that wait, by device, with the reason and the **Release** button (sends each one by its rule).
- **Panel tab**: the *Film and print panel* — period, modality, who created and origin; the cards (films, % printed, stopped, study → film, film → print, study → print, sheets printed), the films per month, the tables by modality and by who created, the list of films and **Export CSV**.

The **settings** (print servers, destinations, rules, sheet templates and registration of origins) stay in the desktop Ipê on the server. Each send, identification and deletion done through the browser goes into the access log, with the user. Assembling a new film is still done in the *Film* tab inside the study.

**Registers in the browser (0.100.71).** For **administrators**, the study list gains the **Registers…** button — what used to be done only in the desktop Ipê on the server:

- **Users**: **New user…**, **Edit**, **Activate/Deactivate**, **Reset the password** and **Delete**; in **Profiles and permissions…**, the table of what each profile can do. The password given by the administrator is **temporary**: on entering Ipê Web, the person is taken to choose their own before anything else. There is always one active administrator left, and nobody deletes themselves. Whoever is deactivated, deleted or has the password reset loses the open sessions at once (browser and Ipê client). **Change my password…** changes your own password.
- **DICOM nodes**: the server's nodes, DIMSE or DICOMweb, with the same fields as the *Network* window (uses, C-GET or C-MOVE, share with clients, authentication). **Test network** applies to what is on the screen, before saving. The password, the token and the client secret **do not come back to the browser**: an empty field leaves what was there. Underneath, the **identities** (source AE Title).
- **DICOM printers**: the same as *Film ▸ DICOM printers*, with **Test connection** and **Duplicate**. Renaming a printer follows the print destinations that use it; deleting one that is in a destination asks for confirmation.
- **AI automations**: the tools of *Preferences ▸ CAD/AI* — for each one, whether it runs by itself when the study arrives, on which studies and series, and to which nodes the result goes. In the list, each tool says **automatic on arrival** or **by hand only**. Nothing changes until **Save**.
- **Access log**: who did what, with filter by period, user, action and text.

Each change goes into the access log with the name of who did it. Staying in the desktop Ipê: installing the AI models, the server's own DICOM node (AE, port, who can connect), the network automation rules and the print settings.

**Sending to a DICOM destination (0.100.9).** The **Send to a DICOM destination** button (the paper plane, beside Report) only appears for those with the permission to send to DICOM nodes.

- **What**: the whole study, the checked series (the active frame's is already checked) or just the active frame's image.
- **To**: the server's active DICOM nodes (the service's, your own and those shared with you) and, if the node has it, the identity (the AE) with which the server talks to it.
- **Along with: the measurements (GSPS) and key images (KO)**: what was measured in the study becomes a GSPS and the key images a KO, saved in the study and sent in the same send.
- The send enters the **server's send queue**, the same as Ipê's. **Sends**, in the footer, shows those you requested, with progress (sent/total), the result and **Cancel** while it runs. Each send goes into the access log, with your name.

**CAD/AI in the browser (AI tab, 0.100.12).** The **AI** tab of the right panel (beside Film) only appears for those with the **Request CAD/AI by hand** permission (by default: administrator and physician; the administrator adjusts it in **Users ▸ Profiles and permissions**). The bar's **CAD/AI on this study** button and **AI**, in the footer, open the same tab.

- **This study's tasks**, at the top: those requested and the automatic ones, with the state (queued, assembling the volume, running, saving, done), the step, the time and a bar while it runs. **Cancel** appears on those you requested (whoever configures cancels any).
- **Tools**, underneath: all of Ipê's AI tools (abdominal organs, spine, nodules, body composition, emphysema, autoPET, calcium…). First those that **suit this study**, with the **suggested series** (the same one the automatic would choose); then the **others**, with the reason they do not suit. On any of them you can choose the **active frame's series**.
- Choose the tool and the series and click **Run** (or **Redo**, if the study already has the result). The AI runs **on the server**, in the same queue as the automatic one on arrival, one at a time; the segmentation package must be installed on the server's computer. Ipê's *AI tasks* window shows the same tasks.
- When the task finishes, the result appears **in the same session**, without closing and reopening the study (0.100.15): the new series enter the strip, the SEG enters the segmentation icon (and already appears painted, if none was chosen), the spine and lymph node names enter the overlay and the series gain the AI badge.
- **Findings to review (0.100.16)**: the AIs that point out findings for the physician to review (emphysema, nodules, Genant, coronary calcium, aorta, tumor burden on PET, body composition) appear in the AI tab, as in Ipê's *AI findings* panel. Each finding shows the numbers, the state (suggested, confirmed, corrected, discarded) and who reviewed it. **Go to** takes the frames to the finding; **Confirm**, **Correct…** (change the numbers and save: the finding becomes *corrected* and the report carries your numbers), **Discard** and **Back to suggested**. **Send to the report** opens the report and puts the text of the confirmed and corrected findings where the cursor is — nothing goes to the report without review. Reviewing needs the permission to write reports (the resident also reviews; the AI tab appears for them with only the findings); each review goes into the access log. It is the same list as Ipê's: what is reviewed in one appears in the other.

**Film and printing in the browser (0.100.11).** The **Film** tab of the right panel only appears for those with the permission to print.

- **Assemble**: adjust the image in the frame with the usual tools (window, zoom, pan, rotate, invert) and click **+ Active frame**, **+ All frames** or **+ Frame's series** (the whole series, one image every N, with the frame's adjustment). Only original images enter (not MPR, MIP or maps).
- **The preview is what comes out**: the server draws the sheet with the same code as Ipê's composer (header with patient and study, ruler, texts, measurements). ◂ ▸ move between sheets.
- **Edit**: click on a cell in the preview. **Edit in the active frame** puts the image in the frame with its adjustment; change whatever you want and click **Update the cell**. **◂ ▸** change the order and **Remove** takes it out.
- **Sheet**: name, grid (1×1 to 6×5), paper (A4, A3, Letter, films from 8×10 to 14×17 in), landscape, texts, header, anonymize, ruler and black background. The film is kept in the browser until you clear it.
- **Print**, in **Output**:
  - **Download PDF**;
  - **Print on this computer**: the browser opens its print window, with the printers of the computer of whoever is using it;
  - the **server computer's printers**, by name;
  - the **DICOM printers** that the server shares (checked *Share with clients*, see *Printing on a DICOM printer through the server*, below), by name;
  - Ipê's **print destinations** (PDF or images in a folder, system printer, DICOM printer).
- **Only this sheet** prints the preview's sheet. Each print counts in the film panel (the film is saved, with who printed it and where to) and in the access log.
- Zoom and pan go as in Ipê, relative to "fit in the cell". Since the film cell has a different proportion from the screen frame, the framing may change a little; the preview shows how it will come out.

**Smaller screens (0.100.53).** The top bar shows the buttons that fit, in order; those that do not fit (on a 1366 × 768 screen, for example: Density, Calcifications, Cine, Invert, Overlay, Report, Send, CAD/AI, Reading mode, Appearance) go to the **»** button, at the end of the bar, which opens a menu with them — same name, same icon, same action; what is a panel (the report, the density) opens under the ». When the window is enlarged, they return to the bar.

**Window in mammography and tomosynthesis (0.100.52).** In the browser, each mammogram opens with the file's own window, and one image's window does not pass to the others (not even through linked windows). The window you set with the mouse on a tomosynthesis slice applies to the other slices of the same series; when scrolling to the 2D (another series of the same stack), it returns to that one's file window, and on going back to the tomo your window is still there. The *From the file* window (in the windows menu) undoes your series window.

**Breast density in the browser (0.100.50).** In a study with mammography, the **Breast density** button (the drop, beside Dynamic) opens the same density as Ipê's Density button: the **NYU network** on the study's four 2D views, with the category and probability of each. If the study has not been measured yet, the server measures it on the spot (the measurement is kept in the study, and the desktop Ipê sees the same). The category checked by default is the network's (or the one already confirmed); change it if you disagree and click **Confirm** or **Confirm and send to the report**, which opens the report beside it and puts the composition in the mammography BI-RADS (with another BI-RADS type, the sentence goes as text). **Measure again** redoes the calculation without losing the confirmation. Viewing and measuring ask only for the permission to open studies; confirming asks for the one to write reports. The confirmations enter *Measured densities* and the agreement, like Ipê's.

**Report in the browser (0.99.98).**

- **Report** (bar) opens the report beside the images, in the same report record as Ipê: what is written in one appears in the other.
- Without a report, it starts with the **suggested template** for the study, with the **automatic fields** filled in as in Ipê (patient, age, date, comparison, measurements, lesions…). **Apply template** swaps the text for another template's.
- **Insert AI findings** puts at the cursor the **confirmed or corrected** AI findings (the suggested ones do not enter), with each tool's sentence.
- **Schemas in the report** (0.100.74): the same box as the desktop Ipê — includes the study's guide schemas in the report (caption in the text, figures in the PDF and, on signing, in the SR). The schemas are drawn with the viewer's **Schema** button.
- **Save draft** (and it also saves by itself a few seconds after you stop typing). **Sign and release** asks for confirmation in the window itself; once signed, the report no longer changes — **Amend** creates a new draft with the text, and the previous one is kept.
- **Who is reporting**: opening the report locks the study for you. If another physician opens it, they see the warning and choose **Read only** or **Take over the report** (it goes into the access log); the server refuses to save or sign for anyone who does not hold the lock. Closing the report (or leaving the study) releases the lock. Whoever lacks permission to write reports only reads.
- **BI-RADS® (0.100.4)**: the same form as Ipê's report window — the type (mammography, ultrasound or MRI), the composition (or the fibroglandular tissue and background enhancement in MRI), the **findings** (**+ Finding**: side, type, descriptors from the list, size, location, distance from the nipple, change and category), each breast's category and the recommendation. The report text changes by itself, with Ipê's same sentences; in a template without the BI-RADS fields, **Take to the report text** puts the blocks where the cursor is. The final category is the most concerning.
- **PDF and DICOM (0.100.4)**: **Download PDF** generates Ipê's PDF (a draft comes out marked), with the **header** and the **signature line** (they are kept). On signing, as in Ipê, the PDF (encapsulated DICOM) and the report as **SR** enter the study — the two boxes choose.
- **Active search (0.100.4)**: on signing, BI-RADS 0 or 3 (the categories in Settings ▸ Active search) creates the request to call the patient, with the deadline; an amendment replaces the request. The patient's open requests appear at the top of the report.

For now it is only on the clinic's network; from outside, come in through the VPN.

### HTTPS on the internal network (Ipê's certificate)

Without a certificate, the central server uses HTTP and each login's password travels in the open over the network. A public authority's certificate does not work for an address like 192.168.1.10, so Ipê itself plays the role of an internal **certificate authority (CA)**:

1. **On the server:** Settings ▸ Network ▸ Central server ▸ **Generate certificate for the internal network…**. The first time it creates the service's CA (valid for 10 years) and, with it, the server certificate, valid for the computer's name and all its IPs (825 days). The Certificate and Key fields are filled in by themselves. The window shows the CA's **fingerprint**: write it down. Press OK and close and open the program: the server starts answering on `https://`.
2. **On each client:** change the address to `https://…` and click **Trust this server's certificate…**. Ipê downloads the server's CA and shows the fingerprint: check that it is the same as the server's and confirm. From then on the client only accepts that server (another computer on the network cannot pass itself off as it).
3. **Browsers and other DICOMweb viewers:** **Save the CA (.crt)…** on the server and, on each client's Windows, double-click the file ▸ Install certificate ▸ Local machine (or Current user) ▸ Trusted Root Certification Authorities.

With the certificate, the server only speaks HTTPS: whoever types `http://` in the browser is taken by itself to the `https://` of the same address (0.100.62), and Ipê clients must have the address in `https://`. Since 0.100.62 the HTTPS negotiation is done on each connection, with a deadline — before, a connection that opened and stayed silent (the browser pre-opens connections; a phone that sleeps) could stop the server until it was closed, and Ipê Web only came back by restarting the program.

Generating again (for example, when the server changes IP) changes only the server's certificate; the CA stays the same and the clients need do nothing. The CA's key stays only on the server, in the `certificados` folder of the settings; keep a copy of it with the backup.

### Profiles by group and computer

**Settings ▸ Users ▸ Profiles by group and computer…** (whoever manages users) builds preference profiles that the server sends to the workstations: each profile says which **computers** it applies to (names, with wildcards: `ROOM-MAMMO*`, `CT-0?`), which **users** and which **access profiles** (empty = all), and which preferences it carries — mouse, text over the image, shortcuts, database columns, monitors, breast dynamic, CAD/AI, language… The easiest way is to set up a computer as it should be and use **Capture from this computer…**; you can also write key and value by hand (the value in JSON).

On signing in, the profiles that match apply, in the order of the list (the lower one wins). The profile overrides what comes from the computer, and each person can still adjust their own — except for the keys marked **Force**, which nobody changes. In client mode the profiles live on the server; on a computer with several people, in its database (there only users and access profiles make a difference). This computer's name appears in the window itself.

### Updates through the central server

**Settings ▸ Network ▸ Updates through the central server…** (whoever manages users, on the server or on a client) publishes a version's packages — **one per system**, with the original GitHub name: the Windows installer (`Ipe-x.y.z-windows-installer.exe`), the macOS `.dmg` (`arm64` for Apple chip, `x86_64` for Intel) and the Linux one — on one of two channels: **test**, which goes first to the computers and people of the profiles marked *Updates: Test*, and **stable**, for everyone. **Promote test → stable** releases to everyone what has already been tested; **Withdraw** takes the package off the channel. Publishing one system's package does not touch the others'; the window shows, on each channel, what exists for each system.

Each computer only receives its own system's package. If the server does not have its package (for example, a Mac when only the Windows and Linux ones were published), nothing is downloaded, and **Help ▸ Check for update on the central server…** says so and offers to look for the version on GitHub.

On entering client mode, the program checks its channel; if there is a newer version, it asks whether to download and install. With "yes", it downloads, checks the SHA-256 and, if it is the Windows installer (or the `.dmg` on a Mac with Ipê in the Applications folder), closes the program and installs without further questions. Another kind of package (zip, tgz) is downloaded and the folder opens, to install by hand. With "no", it does not ask again for the same version; **Help ▸ Check for update on the central server…** asks right away. Each publication, promotion and withdrawal goes into the access log.

## Lossless compression

**File ▸ Archive report (format and compression)…** shows what the archive has and how much lossless compression would save. The compression replaces the file only after checking pixel by pixel, reading back from the disk, that the image is identical.

# DICOM Management: are the modalities' studies in the PACS?

The check that is done by hand — opening each modality, looking at the day's studies and checking the PACS study by study and series by series — done with one button. **Management** button on the database screen.

## Setting up once

1. Register each modality as a DIMSE node (Settings ▸ Network ▸ DICOM nodes).
2. For a modality that accepts only a known AE (the OsiriX one, for example), register that AE as an identity (chapter 9).
3. Open **Management**. In the **Modalities** panel, check the ones you want to verify and, for each, the identity used to talk to it.
4. In the **PACS** panel: the PACS node, the identity (*As:*), the **C-MOVE destination** (normally the PACS's own AE) and **How to send**:

| How to send | What it does |
|---|---|
| Direct; if the modality refuses, through the computer | the default: the modality sends directly to the PACS; if it does not know the PACS, the study goes through this computer |
| Direct only | only the modality sends to the PACS |
| Through the computer only | downloads here and resends to the PACS as the chosen identity |

Everything is remembered: the next day's routine is one click.

## Testing the node

**Test the selected node** answers, without sending anything: whether the C-ECHO passes with the identity, whether the modality searches by date, whether it reports the image count per study and per series, whether it answers at the image level and whether it knows the PACS as a destination (a test C-MOVE of a nonexistent study: the 0xA801 refusal says for sure that it does not know it; "accepted" does not prove that it does, and the screen says so).

## Checking

In the **What to check** panel: the **Period** (Today, Yesterday, Yesterday and today, Last 7 days or dates), **Ignore series** (the ones the modality keeps and deliberately does not send, like *Patient Protocol*) and *Check image by image* (slower; says which images are missing). Then, **Check**.

| Status | What it means |
|---|---|
| ✖ missing from the PACS | the study did not arrive |
| ◐ incomplete | series are missing, or series have fewer images (says which and how many) |
| ≠ other UID | in the PACS there is a study with the same accession and another UID — redone, merged or corrected. Sending would create a duplicate, and the program warns |
| ? no count | the node does not report the number of images nor answer at the image level |
| ✔ complete | everything is there. A PACS with extra images is not a defect |

The worst comes first. **Show: Only those with a problem** filters; the series appear by opening the study. If the first three studies give the same error, the check stops and says the reason once — an error that repeats in all of them belongs to the node, not to the study (for example, a PACS that accepts the connection and refuses every search: it is usually a missing permission for the AE; choose in *As:* the identity that works).

## Sending what is missing

- **Send what is missing to the PACS** sends only the series that are missing and, in the incomplete ones, only the images that are missing.
- **Send the whole study** sends everything.
- After the sending the study is **checked again** — "sent" is not "is in the PACS". The Sending column says what happened, and everything goes to the access log.
- **Export CSV…** writes the check to open in Excel.

> **Whoever accepts the destination is whoever sends.** In C-MOVE, the program only chooses the destination's name; the modality decides by its own table. If it does not have the PACS registered, direct sending does not exist — that is why the default falls back to "through the computer". DICOMweb nodes do not enter Management: checking and sending directly are C-FIND and C-MOVE.

# MR protocol check

Each MRI that arrives is compared with the **reference protocol** for the same study — and the same device, when there is one: the series that are missing, the ones that are extra and the parameters of each one (plane, 2D/3D, sequence, TR, TE, TI, angle, ETL, NEX, thickness, slice spacing, matrix, FOV, pixel, bandwidth, field, diffusion b values, pre- or post-contrast). Only the header is read; no pixels. Left out are the localizer, the calibration and what is derived (ADC map, subtraction, MIP, reformat).

**Network ▸ MR protocol check…** has two tabs.

**Reference protocols.** Three ways to register:

- **Create all from the archive**: one protocol for each study × device with enough studies in the database (by default: the last 6 months, at least 5 studies, reading the 20 most recent). It is the **dominant protocol**: the series that appears in ≥ 80% of the studies is required, in ≥ 50% it is optional; each number is the median, the rest is the most common value. It is the way to register all the service's MRIs at once.
- **Create from the archive…**: the same for a chosen study and device.
- **Use this study as the reference** (in a study's check): the good study becomes the standard — only for that device or for any.

**Edit…** shows the expected series (required or not, and the values; empty value = that parameter is not checked) and the **tolerances**: relative (TR, TE, TI ±10%; FOV and pixel ±10%; bandwidth ±15%), absolute (angle ±2°, thickness ±0.3 mm, slice spacing ±0.5 mm), equal (matrix, plane, 2D/3D, sequence, field, b values, contrast) or show only (number of images). Each protocol can have its own.

**The check.** With the box *Check incoming MRIs automatically* on (default), every MRI received, downloaded or imported is checked in the background. The result goes to the **Protocol (MR)** column of the database (✓ compliant, △ with warnings, ⚠ divergent) and the ⚠ also appears next to the patient's name. Right-click on the study ▸ **Tools ▸ Check the MR protocol…** opens its check: each expected series, the one found, the status and what changed ("TR: 1941 (expected 1700 ±10%)"). With several studies selected, it checks all of them at once.

| Status | Counts as |
|---|---|
| Required series missing | divergence |
| Different plane, 2D/3D, field, sequence, b values or contrast | divergence |
| Number outside the tolerance | warning |
| Optional series missing, extra series | warning |

The series is found by name (the description, without accents and case); if the name changed, by plane + sequence + 2D/3D + contrast. Repeated series: the last one counts (the redone one), and the check says "repeated 1×". The reference is chosen automatically — the one for the same study and device, otherwise the one for the same study on any device; in the check you can choose another.

**Checked studies.** The period, *Only those outside the standard*, **Check the period** (checks all the MRIs again, for example after editing a protocol) and **Export CSV** (one row per difference: series, parameter, value, expected and tolerance). Double-click opens the study's check.

# Report

**Report** button on the start screen, or right-click on the study → **Report…**.

1. Choose a **Template:** and click **Apply template**. There are 19 by default — mammography (screening, diagnostic, tomosynthesis, CEM), breast US, breast MRI, brain, abdomen, pelvis and **multiparametric prostate (PI-RADS)**, brain CT, chest, CT pulmonary angiography, abdomen and oncologic CT, FDG-PET, PSMA-PET, chest radiograph by the **ILO Classification** (pneumoconioses: quality, small and large opacities with the profusion on the 12-point scale, pleura and symbols) and free report. They fill in fields such as patient, age, date, comparison and measurements by themselves.
2. Write the text. The **Insert ▾** menu brings into the report what the program has already measured: study measurements, lesion follow-up, segmentations (volume, SUV, TMTV/TLG, distance to the nipple), time-intensity curves, comparison with priors, breast composition and CAD/AI findings.
3. In the **BI-RADS** panel, on the right, assemble the findings (breast, type, descriptors, size, location, distance from the nipple, evolution, category) and the management; **Take to the report text** writes everything into the body.
4. Finish: **Save draft**, **Save PDF…** or **Sign and release**.

At the foot you can include the key images in the PDF, keep the PDF in the study (as a DICOM series) and keep DICOM SR. A signed report does not change: you create an amendment, which becomes a new report and keeps the previous one. Signing requires the *Sign (release) reports* permission.

The templates are edited in **Templates…** (name, modalities, keywords, BI-RADS and the text with automatic fields between braces). There is *Restore the default ones*.

## Guide diagrams

To mark **where** each finding is on a drawing — useful above all in dermatologic ultrasound, thyroid, breast and prostate MRI. The diagram belongs **to the study**, separate from the report: in the viewer, the **Diagram** button opens the *Study diagrams* window, with the diagrams already made and **New diagram…**, **Draw…**, **Delete** and **Save in the study**. In Ipê Web the **Diagram** button is on the viewer bar, beside Report, and does the same.

| Template | What for |
|---|---|
| Face (front, right and left profile) and body (front and back) | skin lesions |
| Thyroid and cervical levels | nodules and lymph nodes |
| Breasts | clock face, quadrants and axillary tail |
| Prostate — sector map | the 41 sectors (base, mid third, apex, vesicles and sphincter) |

In the editor, the tools are on top: **Point** (one click), **Ellipse** and **Arrow** (dragging), **Freehand**, **Text**, **Move**, **Erase** and **Undo** (Ctrl+Z), with six colors. With **Number** on, each new point, ellipse or arrow gets the next number and a row in the list on the right, where you write the finding's description.

- **Link to an image**: on each mark, **Link to the open image** ties the mark to the image of the viewer's active frame. It becomes a key image and the legend now says "(series 3, image 12)".
- **Prostate**: with the **Sector** tool, choose the category (PI-RADS 1 to 5) and click on the sector to paint it; another click clears it. The legend comes out by category, from highest to lowest.
- **Save in the study** writes at once, with no report at all: the figures go to the "Report diagrams" series and the marks to an SR of the diagrams alone ("Report diagrams (SR)"), like the segmentation table and the density summary. **Saving again replaces what was there** (it does not duplicate).

**In the report** the diagram is only included, like the key images: the **Diagrams in the report** box (in the Ipê report window and in the Ipê Web report panel) does three things:

- puts in the text, where the cursor is, the legend — one line per numbered mark ("1. 4 mm hypoechoic nodule") and the painted sectors. The `{esquemas}` field does the same in the report templates;
- takes the figures, with the legend beside them, to the **PDF**;
- on **signing**, writes the figures into the study and cites the diagrams in the report's **DICOM SR** — the figure, each mark with its position and the image linked to it (with a diagram, the SR is an *Enhanced SR*). What had been written before by *Save in the study* is replaced.

Without the box checked, the report carries no diagram at all. A signed report does not change the choice; to change it, **Amend**.

**Templates** (0.100.74: **Settings ▸ Diagrams ▸ Diagram templates**; in Ipê Web, **Registers ▸ Diagram templates**). Whoever has the permission to configure registers and changes the templates, which apply to all users:

- **New template from an image…**: a drawing of yours (PNG or JPG) becomes a template;
- **New blank template…**: an empty sheet to draw the template from scratch;
- **Edit the template…**: opens the template with the same drawing tools. What is drawn there becomes part of the template, in all studies; the name and the group can also be changed. **Save as copy** creates a new template from it (the prostate copy carries the sectors);
- in an Ipê template, the original drawing is kept: **Restore the original** undoes the changes, and **Hide from the template list** removes the template from the choice without deleting anything. A template of your own is deleted with **Delete the template**.

## PI-RADS (prostate MRI)

In prostate MRI, the viewer's (and Ipê Web's) **PI-RADS** button opens the **PI-RADS® v2.1** form. It belongs to the study, like the diagram; the report only reads what is in it.

- **Gland and PSA**: the **PSA** and the date; the three diameters (AP, transverse and craniocaudal) — **Take from the rulers** uses the last three rulers drawn in the study, in that order —, or the **Automatic volume (AI)**, which segments the prostate on the axial T2 (TotalSegmentator) and brings the volume here. The volume is the segmentation's when there is one (the "Ellipsoid" choice applies over it) and gives the **PSA density** (PSA ÷ volume). Also check **Biparametric (no DCE)**, **Post-biopsy hemorrhage** and the quality.
- **Lesions**: **New lesion**, or a click on the **sector map** on the right (with no lesion chosen, the click creates one in that sector; with a lesion, it adds or removes the sector from it). For each lesion: zone, sectors, largest diameter, **T2**, **diffusion**, **DCE**, **ADC** (**From the frame's ROI** takes the mean of the active frame's ROI — draw the ROI on the ADC map), extraprostatic extension, description and **Link to the frame's image** (becomes a key image). **DCE curve…** opens the dynamic; the measured curves enter the report through the `{curva}` field.
- **Category**: comes out by itself by the PI-RADS v2.1 rule — in the peripheral zone diffusion rules (diffusion 3 with positive DCE becomes 4); in the transition zone T2 rules (T2 2 with diffusion ≥ 4 becomes 3; T2 3 with diffusion 5 becomes 4); in biparametric the DCE does not count. The program warns when the size and the score do not match (5 asks for ≥ 15 mm or extraprostatic extension). The anterior stroma and the central zone have no table of their own in PI-RADS: check. Each lesion's **manual category** and the **overall** one apply over the rule.
- **Outputs**: the painted sector map enters the study's diagram list (diagram "PI-RADS — sector map"); **Save in the study (SR and map)** writes the PI-RADS SR (series "PI-RADS (SR)": volume, PSA, density, each lesion with the scores, the ADC, the category and the image) and the figure; **Send to the report** writes the text into the open report. The report template **Multiparametric prostate MRI (PI-RADS)** uses the fields `{pirads_achados}` (volume, PSA and lesions) and `{pirads}` (the impression); there is also `{prostata_volume}`.

**Research models (optional, installed separately).** Two **research and teaching — non-clinical, non-commercial** AIs that do not come with Ipê: the weights are downloaded by you, from the source, only after reading and accepting the license (**Settings ▸ CAD/AI ▸ Research models — prostate**, or the first time you try to use them):

- **Prostate zones** (MONAI *prostate_mri_anatomy*, trained on Prostate158): turn it on in **Settings ▸ CAD/AI ▸ Prostate: volume (AI) ▸ Also separate the zones**; the automatic volume then brings the transition and peripheral zones (series "Prostate zones (RESEARCH - not diagnostic)").
- **Suggested lesions** (base nnU-Net from the **PI-CAI** challenge, weights CC BY-NC-SA 4.0): **Research model suggestions…** in the form, or the **PI-CAI** button. It uses the axial T2, the ADC map and the highest-b diffusion of the study; each suggested focus enters PI-RADS as a lesion **to be checked**, with the model's probability. It only runs by hand.

Everything that comes from these models comes marked **"research model — do not use for diagnosis"**: the red strip in the form, the SEG description, the SR and the report text. The suggested lesion stays marked as research even after being **Checked by the physician**.

## AI in the report text

The **AI ▾** button, in the report window, beside **Insert ▾**:

- **Check the report (no network)** — always available: it points out an unfilled field ("___", "{field}"), a measurement without a unit ("measuring 12") or too large (over 400 mm or 60 cm), a repeated word, "right left", an organ that does not fit the patient's sex (uterus in a male, prostate in a female), a BI-RADS category in the text different from the form's, BI-RADS 3 with routine management, BI-RADS 4 and 5 without histopathology, a conclusion that cites a side the body of the report does not cite and an empty impression. The same check runs **before signing**: if it finds something, it shows the list and asks whether to sign anyway (turn it off in Settings).
- **Refine the text (AI)…**, **Generate the impression (AI)…** and **Point out errors (AI)…** — with a configured language model. The answer opens in an editable window; nothing enters the report without **Replace the report text with this one** or **Insert in the report (at the cursor)**, and Ctrl+Z undoes it.

**Settings ▸ Reports ▸ AI in the report text…** chooses the provider: **Ollama** (the model runs on this computer or on a network server; the text does not leave the service), an **OpenAI-compatible** server (LM Studio, vLLM, llama.cpp) or the **Anthropic API** (with the service's key; the text leaves). Before leaving the program, the text loses the patient's **name, ID, accession and birth date**, which come back in the answer; for an address outside this computer, the program asks once. **Test** checks the connection. The API key is kept **encrypted**. The model only suggests: whoever signs is the physician.

## Documents attached to the study (PDF and images)

Medical request, consent form, a previous report from another service, a photo of the lesion: the PDF or image enters **inside the study**, converted to DICOM, and goes along when the study is exported or sent to the PACS. Three ways:

- **drag onto the viewer** — goes to the open study (the active frame's);
- **drag in the database with a study selected** — the program asks first ("Attach 2 files to the study of …?"), so it does not land on the wrong patient;
- **right-click on the study ▸ Documents ▸ Attach document (PDF or image)…**, or, in the viewer, the frame's series menu ▸ **Attach document…**.

The **PDF** becomes a PDF document encapsulated in DICOM (DOC modality), in the **Attached documents** series, with the file name as title. Each **image** (JPG, PNG, TIFF — each page becomes one —, BMP, GIF, WEBP) becomes a DICOM image (secondary capture, OT modality) in the **Attached images** series, and appears in the viewer like any other series. The patient and study data are those of the study itself. Word, Excel and other formats are left out, with a warning: save as PDF first.

The attachment follows the study's **routing rules** (Settings ▸ Network ▸ Automation): if the study would go to a node, the attachment goes too. Who attached it is in the access log.

To read the study's PDFs — attached ones, reports kept as PDF or PDFs that came from another system —: right-click on the study ▸ **Documents ▸ Study documents…**, double-click on the documents series in the series panel, or the frame's series menu ▸ **Study documents…**. The PDF opens inside the program; there is also **Open in the system program** and **Save the PDF…**.

**In Ipê Web** (0.100.55): drag the files from the computer onto the open study — "Drop to attach to the study" appears — or use **Attach PDF or image…** below the series. The browser asks first, sends to the server, and the server does the same as desktop Ipê (converts, stores in the study and follows the routing rules). Images enter the series list at once; PDFs stay in **Documents** (below the series) and open in a new tab. It requires the import permission; up to 40 files or 80 MB at a time.

## Report in progress (central server)

In client mode, whoever opens a study's report becomes **the one reporting**, until the report window closes. Another physician who opens the report of the same study is warned ("Dr. Ana has been reporting this study since 10:05") and chooses **Read only** (the window opens unable to save) or **Take over the report** (it goes in the access log, and the first one no longer saves). Whoever only opens the images sees the notice in the status bar. The server refuses to save or sign the report of whoever does not hold it. If the computer of the one reporting freezes, the lock drops by itself in 10 minutes.

## End of reading: sending to the PACS on signing

**Settings ▸ Reports ▸ End of reading (send to the PACS on signing)…** turns on the sending and chooses the **destination** (one of the active network nodes). On **signing** the report, the program writes the key images as a **KO** and the measurements as a **GSPS** in the study, and sends to the destination, through the sending queue (the same as the manual sending):

- **the report** of this signature (the PDF and the SR, if you keep them in the study);
- **the key images (KO)** and **the measurements and annotations (GSPS)**;
- **Ipê's series** in the study (the analyses' SEG, maps, captures).

Each item can be turned on and off. Not sent: the previous report, series from another device, the **hidden** ones and the copies that stay only on this computer (the copy without implant, the segmentation tables). The report's status bar says "sending to the PACS: …" and the sending is in the access log. It also applies to a report signed in the **browser**: the central server writes and sends by itself.

## Closing the study automatically

**Settings ▸ Viewer ▸ Close the study automatically…**: close the study (and the report window) on **signing the report**, and/or close the open studies after **N minutes** without touching the mouse and keyboard (the report draft is saved first). It prevents the next patient from being looked at — or reported — with the previous one still on the screen.

## Active search (BI-RADS 0 and 3)

On **signing** a report with the BI-RADS form, the final category decides whether the patient enters **active search**: by default, **BI-RADS 0** with a **30-day** deadline and **BI-RADS 3** with **180 days**, counted from the signature. The amendment replaces the study's open request (or closes it, if the new category asks for no return). In **Settings ▸ Reports ▸ Active search (deadlines by BI-RADS)…** you can change the days and also turn on 4A, 4B, 4C and 5 ("awaiting histopathology").

**Reports ▸ Active search…** shows the requests — open, overdue (in red), returned or closed — with the deadline and the status ("12 days left", "3 days late"). The **Contacted**, **Scheduled**, **Returned**, **Close…** (with the reason) and **Note…** buttons go to the history, with who and when; **Open the study** opens the originating study (or the return one). The patient **returns by herself** when a breast study of hers with the same or a later date reaches the database (mammography, or US/MRI with "mama" in the description) — the **Check returns** button redoes this check. **Export CSV…** takes the list to the reception's spreadsheet. On the central server, the list is a single one for all workstations.

## Worklist: priority, subspecialty and deadline (SLA)

Each study in the database has a **priority** (routine, urgent, emergency), a **subspecialty** (breast, neuro, head and neck, chest, musculoskeletal, abdomen, nuclear medicine or general) and a **report deadline**: the arrival in the database + the hours of the priority (by default, routine 48 h, urgent 4 h, emergency 1 h; routine can have its own hours per subspecialty, like "Mama=72"). The **Priority**, **Subspecialty**, **Report deadline** and **SLA** columns show this; the SLA says "5 h left", "due in 40 min" (orange, under 2 h), "3 h late" (red) and, after signing, "on time" or "past the deadline (+5 h)". Urgent appears in orange and emergency in red.

The priority comes from the words of the study description (by default "URGENTE", "PS", "PRONTO SOCORRO", "UTI" → urgent; "EMERGÊNCIA", "CÓDIGO AVC", "TRAUMA" → emergency) and the subspecialty from the first rule that matches (modalities + description words). Everything is adjusted in **Settings ▸ Reports ▸ Priority, subspecialty and deadlines (SLA)…**; on each study, **right-click ▸ Organize ▸ Priority** or **▸ Subspecialty** changes it by hand ("From the rule" goes back to automatic).

The **Work ▾** button, in the database, filters and sorts by deadline: **unreported** (what is due first on top), **overdue**, **due in under 2 h**, **urgent and emergency** and **my subspecialties** (choose yours once in *Choose my subspecialties…*). On the central server the rules apply to all workstations.

**Study state** (0.99.63): the **State** column (Columns ▾) shows *Unread* (never opened and no report), *Being read* (open, or with a draft), *Urgent* (no signed report and with urgent or emergency priority) and *Reviewed* (signed report), in colors, and sorts in that order. Right-click ▸ **Organize ▸ Study state** changes it by hand — the reviewed one with no report (second reading, meeting), the one that went back to reading —, and the column marks the changed one with ✎; *Automatic* goes back to the calculation. In **Work ▾**: *Unread*, *Being read* and *Not yet reviewed*. In the viewer, the action *Study: mark as reviewed* (choose a key in Shortcuts ▸ Studies) marks the study of the active frame; again, it goes back to automatic.

## Productivity

**Reports ▸ Productivity…** counts the **signed** reports in the period (today, 7 or 30 days, this month, last month, this year or chosen dates) and groups them by **physician**, **modality**, **subspecialty**, **priority** or **day**: how many reports, how many amendments, the **median** and the **p90** of the time from the study's arrival in the database to the signature (in hours) and how many came out **on time** (by the deadline rules in the previous item). The bars show on time in green and past the deadline in orange. On top, what is **pending now**: studies without a signed report, overdue and due in under 2 h. **Export CSV…** takes the table to a spreadsheet. Whoever does not manage users sees only their own reports. A report counts as one report (no weights by modality).

## Mammography filters

The **Breast ▾** button, beside **Columns ▾** in the database, applies ready filters and shows the columns they use: **BI-RADS 0**, **3**, **4 and 5**, **6**; **dense breasts** (ACR c and d) or non-dense; **mammograms without a signed report**; **screening** or **diagnostic** (by the study description); **active search open** or **that returned**. The **BI-RADS** and **Density** columns come from the study's most recent signed BI-RADS report; **Active search**, from the study's request. Like every column, they also accept the typed filter and the filter by values.

# Film and printing

## The film composer

**Print** button on the start screen, **File ▸ Film / printing** (Ctrl+P), or F1/F2 and the **Film** button inside the study. With a study open, the film appears as a panel beside the frames; the expand button, at the corner of the film bar (or a double-click on the film), toggles between the large film and the frames.

### Assembling

- **Sheet**: grid (rows × columns), paper, portrait or landscape, and *on all sheets* to apply to the whole set. The sheets are on the left, with New, Duplicate, Move up, Move down, Delete and Compact.
- **Filling**: F1 (the frame's image) and F2 (the frame's series, whole or a range) in the viewer; dragging thumbnails from the strip to a cell; the Film button's menu brings all the frames and the key images.
- **Texts**: the text level in the cells, header, anonymize, ruler and black background.

### In the cell

| Gesture | What it does |
|---|---|
| Left, dragging | the function chosen in **Mouse (left button)**: Window, Move (the image inside its frame) or Zoom |
| ⠿ handle dragged (corner of the cell) | **swaps the image** with that of the cell where you drop it — with any mouse function; works between sheets |
| Right dragging / middle dragging | zoom / move |
| Wheel | scrolls the series slice |
| Right button | menu: Mouse (left button), copy, cut, paste, rotate, flip, invert, window, color, filter, restore, open in the viewer, remove, insert or remove a slot |
| Ctrl/Shift + click | selects several |
| Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+A / Del | copy, cut, paste, select the sheet, delete |
| Double-click | expand the film (or edit the text, if on top of a text) |

The left-button function is also on the **Mouse: …** button of the second bar, and is remembered.

### Film annotations

**➚ Arrow**, **T Text** and **✎ Pencil** annotate only on the film — never on the study's image.

- After an annotation, the mouse **goes back by itself** to the function it had (window, move or zoom).
- Hovering over an annotation changes the cursor: dragging **moves** the annotation; dragging the **tip or tail of the arrow** changes its size; **double-click on a text** edits the text (empty text deletes the annotation).
- **Ctrl+Z** undoes the last annotation.
- The **Annotations** button turns all the film's annotations on and off — on screen, in the print, in the PDF and in the JPG/PNG. Choosing an annotation tool turns them back on.

### Saving, printing and exporting

| Button | What it does |
|---|---|
| Save / Save as… | keeps the film in the database (Open… and File ▸ Saved films… reopen it) |
| also in the study | box beside Save: also writes the film **inside the study**, in the format of GE's AW workstation (see below) |
| Print… | Windows printer |
| PDF… | one page per sheet |
| JPG/PNG… | one image per sheet |
| DICOM Print… | DICOM printer (requires the print permission) |

A film printed without having been saved is saved at the time of printing, with the name it has — otherwise the print would not show up in the film panel.

### Film in the study (AW format)

With **also in the study** checked, Save writes three things into the study of the film's first image, as the AW does:

- an **SR** "AW electronic film" with the film's layout (pages, slots and positions);
- the **loose images** of each cell, with the text and annotations, in the study's modality;
- the **finished sheets** "AW electronic pages", as they would come out printed.

The film remembers what it wrote. If nothing has changed since the last write, Save does not write again; if it changed, it asks: **Replace the previous one**, **Keep both** or **Not now**. The written series appear in the Prints tab as a workstation film, like the AW's own.

## Received prints

**Prints** button (Ctrl+Shift+P): the list of what the modalities sent here and what was assembled here, with a preview. On top are the search, the **Panel…** and the **Settings…**; below, the actions on the chosen job: open, **Send to…**, **Reprint…**, **History…**, identify the patient, see the **Stalled…** and delete.

### Sending history and reprinting

Every sending is kept: when, to where, who was in the program, whether it was **by hand**, **by the rule**, **reprint** or **in the composer**, with which sheet template, and whether it worked. The last three appear below the job's details; **History…** shows all of them. This is where the Panel gets the "Printed by" of the DICOM prints (sending by the rule appears as "rule (automatic)"). The history starts in 0.84: what was sent before that has no history.

**Reprint…**: choose one or several jobs (Ctrl or Shift + click) and each one goes back to the **last destination** it went to, with the same sheet template. Before sending, the window says how many go to each destination; those never sent are left out (for those, use **Send to…**).

### The job's modality

The DICOM print does not say the modality. The program works it out like this: with the patient identified (OCR on arrival or **Identify patient**), it is the modality of the **patient's study** made up to the time of arrival (on the same day or the day before); without a patient, it is the modality written in the **origin's registration** (Settings ▸ Printing ▸ Servers, destinations, rules and templates ▸ Origins ▸ Modality). The **Modality** column of the list shows the result. It applies to the **rules by modality** and to **cleanup**.

### List columns and filters

The prints list works like the database table:

- **filter**: the box under each title filters that column, with the same syntax as the database (`ana|maria`, `!Enviado`, `>=2` in Sheets, `hoje` or `7d` in Arrival); right-click on the title opens **Filter values of…**, to check the values that stay;
- **sort**: click the title; the second click reverses and the third goes back to arrival order (most recent first);
- **arrange the columns**: drag the title to change the order; right-click ▸ **Columns** hides and shows (Patient always appears) and **Restore default columns** undoes it. The order, widths and hidden columns are saved.

Below the list it says how many jobs are in view and the **Clear filters** button.

### Preview

Click on a job to see the sheet beside it, with ◀ ▶ to move through the sheets. It works for what came from the modality, for the film that came in the study and for the film assembled in the composer (this one is drawn on the spot, just for looking). A **double-click** opens: the composer's film opens in the composer to edit; the others open the study.

### Identifying the patient of a print

The DICOM print carries neither the patient's name nor ID. **Identify patient…** (with a received job selected) opens a window with three paths:

- **Studies from the same device and time**: the database studies made on the device that sent the print, near the time it arrived — click to use;
- **Read the sheet header (OCR)**: the program reads the text burned in at the top of the first sheet (about 2 seconds), shows what it read and looks in the database for patients whose name — or ID — appears there, even with a missing space, without accents or with a swapped letter. Those that match enter at the top of the list, with the percentage ("OCR 95% · …"); when the first wins by a clear margin, it already comes chosen;
- write **Name** and **ID** by hand.

> **OCR is a suggestion.** It reads what the modality wrote on the sheet and sometimes errs — check the name before OK. If the patient is not in the database, the fields are filled with what was read. The reader comes inside the program and works without internet.

### OCR on arrival

When a film arrives through the DICOM printer, the program looks for the patient in the database by itself, without freezing the screen. It reads, in this order, and stops at the first one that identifies: the **text the modality sent separately** (annotation boxes and session label — some devices do not write the name on the image), the **top** of the first sheet, the **footer** and, last, the **whole sheet** (about 2 seconds per reading):

| The OCR… | What happens |
|---|---|
| found the patient with a clear margin | name and ID enter the job, the study of the sheets already comes out with the name, and the film **follows the rule** |
| did not find (or was in doubt between two) | the film **stays stalled**, with the Status **Waiting for patient** |

The **Status** column says why a received film did not go out: **Waiting for patient** (the OCR did not find), **Stalled: device not registered** (the patient may even have been found, but the device does not have a name in Origins yet — by default, a film from an unregistered device does not go out by itself), **Stalled: origin turned off** or **In the list (no rule)**.

To release a film that stayed waiting: select it and use **Identify patient…**. After OK it follows the rule by itself, by the same path as automatic forwarding. Hovering over the name shows where it came from (OCR, confirmed by hand, chosen among the studies).

> **The patient needs to be in the database.** The OCR compares what it read with the patients already here. A film that arrives before the study's images stays waiting for your confirmation.

To turn it off: **Settings ▸ Printing ▸ Servers, destinations, rules and templates ▸ Rules**, the box "Identify the patient by OCR when the film arrives". Off, the rule acts as soon as the film arrives, as before 0.81.

### Images sent to the printer

Some modalities (ultrasound, for example) send **ordinary images** to the printer instead of a finished film. Each print server's port accepts these images:

- they enter the database like any received study;
- when the modality finishes sending, the program assembles **one film per study with all the images**, in the order they arrived (a clip with many frames enters with up to 16, spread out). The grid and the paper come from the **Automatic rule** that matches ("my AE" is that printer's AE); with no matching rule, from the default grid written at the bottom of the tab;
- if the Automatic rule has a destination, the film goes there; otherwise, it follows **that server's print rules**, like a printed film;
- with **OCR on arrival** on (Settings ▸ Printing ▸ … ▸ Rules), the program reads the text the modality wrote on the first images (top, footer and, last, the whole image) and looks for the patient in the database. The name in the images' header is **not** proof: a device that sends a generic name would have that same name in the database. When the patient is found, the name and ID go to the film — also in the printed sheet's header — and it follows the rule. When not found, the film stays with the Status **Waiting for patient**: select it and use **Identify patient…**, and after OK it follows the rule by itself. With OCR off, the name in the images applies, as before 0.89.

The film appears in the prints list as "Assembled here" and can be opened in the composer.

**Settings ▸ Printing ▸ Servers, destinations, rules and sheet templates** (or the tab's button) has the tabs Servers (each one is a printer the modalities see), Destinations, Origins, Rules, Sheet templates, Automatic and Cleanup.

**Automatic** (film assembled by itself, for a modality that sends **the images** and not the finished film, like ultrasound): it is also a table of rules, one per line, with Origin (AE), Received by, Modality, other conditions, grid, how many images, where it goes afterwards and the template. The editor has the same three check lists — **Origin (AE title of the sender)**, **Received by (my called AE)** and **Modality** — and, in **Other conditions**, the study description (`MAMA|AXILA`). Below, **Assemble the film like this**: grid, paper, how many images (0 = all), after assembling (leave in the list or send to a destination) and the sheet template. The first enabled rule that matches assembles the film, a few seconds after the study stops arriving; one film per study.

"My called AE" is the AE the modality set as the destination. The DICOM node accepts any called AE on the same port, so you can register two destinations with different AEs on the device (for example `US_FILME` and `US_ARQUIVO`) and have a rule only for the first. The list shows the node's AE, the identities and the printers' AEs; "Another AE of mine…" adds a new name. The single setting from before 0.86 became the first rule of the table.

**Rules** (Rules tab): a table, one rule per line, with the columns **Origin (AE)**, **Received by** (your AE), **Modality**, other conditions, destination, template and whether it stops there. The box in the first column turns the rule on and off; ▲ ▼ change the order (the first that matches rules); double-click edits.

In the rule editor, the **When** is three check lists side by side:

- **Origin (AE title of the sender)**: the AEs that have already sent work, with the name given in Origins. For a device that has not sent anything yet, write the AE in "Another AE title…" and click **+**;
- **Received by (my AE)**: your print servers (AE, port and name);
- **Modality**: MG, CT, MR, US… (those of the origins enter too; "Other…" adds). The modality is that of the identified patient's study or, with no patient, that of the origin's registration; a job of unknown modality does not match a rule that requires a modality.

In each list you can check several; a list with nothing checked is "any". The job needs to match all three. To treat each device, each of your AEs or each modality differently, make one rule for each case (**Duplicate…** helps). **Other conditions** keeps the rest: registered device (AE + address), AE with wildcard (`MG*`), label, film size, number of sheets and time. Below, the **Summary** says in one line what the rule does. Rules made before 0.85 remain valid as they were; when opening one in the editor, the server and the modality appear checked in the lists.

**Cleanup** (its own tab): deletes by itself, on opening the program and every hour, the received jobs that meet **all** the checked criteria — older than N days (by arrival), **only those already printed** (default), of a **modality** (`MG`, `MG|US`) and from certain **origins** (none checked = all). **How many would go?** counts beforehand; **Clean now…** deletes at once. It is born turned off. It does not delete a composer film, a film that came in the study or the study created in the database with the sheets.

**Duplicate…**: in Servers, Destinations, Rules and Sheet templates, choose an item and use **Duplicate…** to start from a copy. It opens the editor already filled in, with the name "(copy)", and you change only what is different; the copy enters right below the original (in the rules, the order matters). The copied server gets a free port, because two servers do not share a port. The DICOM printers list (**Film ▸ Printers**) also has **Duplicate**.

> **Nothing goes out by itself by default.** A print server is born turned off, the automatic destination is born empty and, with no rule at all, the job stays waiting in the list. Whoever makes it go out is you — or a rule you wrote.

## Film and print panel

**File ▸ Film and print panel…**, or **Panel…** in the Prints tab.

- **What enters**: the films assembled in the composer **and the prints that arrived finished through the DICOM printer**. The **Origin** column says which is which (Composer or DICOM Print).
- **Filters**: period, origin, modality, user (or device), "stalled for more than N days" and only the unprinted.
- **Cards**: films (how many from the composer and how many by DICOM print), **% printed**, stalled (saved and not printed for more than N days), and the medians of **study → film**, **film → print** and **study → print** (with the 90th percentile in the detail and the % printed within 24 h), printed sheets and reprints.
- **Charts**: films per month (printed and unprinted) and % printed per modality.
- **Tables** by modality and by user or device, and the film list (sortable; double-click opens the film in the composer or, for the DICOM print, the study with the sheets). **Export CSV…** for Excel.

| Detail | How it is counted |
|---|---|
| Modality | that of the series of the images in the film: in a PET/CT, a CT-only film counts as CT. A film with two modalities counts in both |
| Printing | Windows printer, DICOM Print and sending through the Prints tab count; PDF and JPG/PNG do not |
| Times | study → film goes from the study's date/time to the saved film; film → print, to the last print. Negative time (wrong device clock) is left out of the count |
| DICOM print | counts from arrival; "created by" is the device (the name registered in Origins, or the AE). It stays as printed when forwarded, by the rule or by hand. The study is that of the identified patient (OCR or by hand), the most recent made up to arrival (on the same day or the day before); with no patient identified, modality and times stay blank |
| Old films | user and destination are only recorded since version 0.77; before that they appear as "(not recorded)" |

The panel disappears in Hide mode and in the meeting: the list has patient names.

# Nuclear medicine and oncology

## Nuclear medicine

In NM and PET studies the **NM** button appears, with: anterior and posterior side by side (with the same window on both), invert the scale, curves and ROI analysis, renogram and the uptake calculations.

SUV works on PET (with the dose and decay data from the file). On SPECT/CT, it does not: the conversion requires a calibration that is not in the DICOM. The program says so instead of returning an invented number.

> **Normal values for nuclear medicine are not in the code.** The program returns a number; the reference range is text beside it, never a verdict. When a calculation does not work out, the answer is "it did not work" — not a big number.

## Lesion follow-up

The lesion panel gives each lesion a name, and measurements from different studies are linked to it. The panel shows the evolution and calculates the response. **Lesion layout** puts one frame per lesion.

**Doubling time**: in each study in which the lesion has grown since the previous measured study, the cell gains "· DT N d" (outside PERCIST). The calculation is DT = t × ln 2 ÷ ln(V2/V1), assuming exponential growth, by **volume** when both studies have a segmented volume; otherwise, by the **largest diameter**, assuming a sphere (V ∝ d³). Without growth, "DT does not apply" comes out — never a huge or negative number. The cell's hint shows both measurements, the interval in days and the basis of the calculation; in a small lesion, 1 mm of difference in the diameter changes the result a lot.

**Follow-up between dates** (0.99.59):

- **Linking by position**: each measurement linked to a lesion keeps where it is in the patient (in mm). Draw the measurement in the follow-up study at the lesion's place: carried to the previous study by the registration (the rigid one, or the alignment saved when linking the frames), if it falls within **10 mm** of where the lesion was, the measurement **links itself** to it, and the status bar says to which and at what distance. Without registration between the two studies it does not link (there is no way to know where the point is in the other); with two lesions close by, it does not either — link by hand. The box and the distance stay in the lesion panel.
- **Follow-up…** (in the panel): the lesions measured before and still without a measurement in this study, one per line. **Repeat the measurement** opens the equivalent series at the estimated place, with the previous contour in yellow and the same tool; the next measurement links to the lesion. **Too small (5 mm)** (target; RECIST 1.1 adds 5 mm), **Absent (0)**, and, for non-target ones, **Present / stable** and **Unequivocal progression**. Measurements made before 0.99.59 have no position: Repeat opens the series, without the place.
- **Nadir**: the *Nadir* row shows, in each study, the smallest sum up to that point, and the header marks with ▼ the study that is the current one's nadir. The report summary brings the four dates — baseline, nadir, previous and current — with the sum of each.

**Lesion contour on PET by the edge (0.100.8).** In the **Segment 3D** of a PET, the method **PET: edge by gradient (like PET Edge)** outlines the lesion where the signal **falls fastest**, and not at a fixed value. The threshold in % of the SUVmax (41%) depends on the peak: in a small lesion, partial volume drops the maximum, the threshold goes down to the blurred background and the contour swells. The edge by gradient does not depend on the peak.

- The program starts from the hottest point near the click, casts rays in about 260 directions and, in each one, finds the steepest drop before the signal rises again (another lesion, the heart, the bladder). Each direction's edge is checked against its neighbors, and the lesion is what stays inside it.
- **Partial volume correction**: in a lesion blurred by the device's resolution, the steepest drop is a little inside the true edge — little in a 4 cm lesion, quite a lot in a 1.3 cm one. The program takes each ray back to the true edge using the **PET resolution (FWHM)**. In a large lesion, it measures the resolution in the lesion itself (the width of the drop); in small ones, it uses the window's **PET resolution (FWHM)** field (6 mm by default; current PET/CT, 5–7 mm). The value is saved.
- The window's note says at what percentage of the maximum the edge landed and which resolution was used. Below 1.5 × the resolution, it warns that the lesion is **near the limit** and that the volume is less reliable.
- In test spheres (7 mm resolution, PET noise, background 4:1 to 8:1), the volume was within ±15% of the real one from 1.3 cm up, and the 41% was off by twice as much or more in the small ones.

**PET in follow-up** (0.99.60, **PET…** button of the lesion panel):

- **SUL**: with the height (PatientSize) and sex in the file, each PET measurement also keeps the SUL — the SUV by Janmahasatian's lean body mass (LBM = 9270 × weight / (6680 + 216 × BMI) in men, 9270 × weight / (8780 + 244 × BMI) in women). PERCIST starts using the SULpeak; without height or sex, it stays on the SUVpeak and the cell says which.
- **Liver reference**: *Liver: click* — click on the right lobe, on the PET; the 3 cm sphere looks, within 2 cm of the click, for the most homogeneous place (lowest standard deviation). *Liver: automatic* — uses the study's liver segmentation (Organs/TotalSegmentator on the PET/CT's CT), puts the whole sphere inside it, in the right lobe. **Mediastinum**: click on the descending aorta (1 cm sphere). The references are kept per study.
- **PERCIST**: measurable lesion threshold = 1.5 × liver mean SUL + 2 × SD (without liver, 2 × pool + 2 × SD). The panel shows the reference and the threshold in each study; it warns when the baseline's most avid lesion is below the threshold and when the liver varies by more than 20% or 0.3 between studies (not comparable).
- **Deauville / Lugano** (new criterion in the panel): each lesion's score in each study is proposed from the numbers — 2 up to the mediastinum, 3 up to the liver, 4 above the liver, 5 above 2 × the liver's SUVmax (adjustable) or a new lesion, 1 absent — and is changed with right-click ▸ *Deauville in this study* (includes the X). The metabolic response comes from the highest score: 1–3 complete; 4–5 with lower uptake than the baseline, partial; equal, no response; higher or a new lesion, progression.
- **Q.Check**: this study's PET header — uptake time (50–70 min), weight, height and sex, dose, half-life, unit, decay and attenuation corrections, matrix, thickness, reconstruction and device — and the comparison with the baseline study (difference in uptake time up to 15 min, same device and reconstruction, weight, dose, liver). Glycemia does not come in the DICOM: type the one from the chart in the **Glycemia** field of the PET… window (0.99.88). It is saved in the study; the Q.Check warns above 200 mg/dL (EANM recommends rescheduling or interpreting with caution, the SUV is underestimated) and says that 150–200 is acceptable. With glycemia, the PET measurements also show the **SUVgluc** = SUV × glycemia ÷ 100 mg/dL (accepts mmol/L: values below 35 become mg/dL × 18).

The 3D segmentation measures volume, maximum and mean SUV, TLG and, adding up the lesions, TMTV. The thresholds (percentage of the SUVmax, minimum SUV, method) are saved, and the threshold bar also applies to the percentage of the SUVmax.

## PET reading and the maximum SUV near the cursor (0.99.88)

In the **Fusion** button of PET/CT studies:

- **PET reading: fusion, PET and rotating MIP…** assembles three frames: the CT with the PET fused, the PET alone and the 3D PET MIP, inverted and rotating. **Click on a focus of the MIP** to take the slices of the other frames to it. The attenuation-corrected PET is preferred over the NAC.
- **Go to the maximum SUV near the cursor (3 cm)** looks for the most avid voxel within a 3 cm sphere around the reference cursor and takes the slices to it; the status bar says the SUV. Useful to pin down a lesion's SUVmax without hunting for the pixel by hand.

## Prepared PET/CT session (0.100.32)

When the tumor burden runs — by itself on the study's arrival (Settings ▸ CAD/AI ▸ Tumor burden ▸ *Do automatically*) or through the **Burden** button — the study is ready for reading:

- **Measured references.** The liver (3 cm sphere in the right lobe) and the mediastinum (1 cm sphere in the descending aorta, found by TotalSegmentator) are saved where the **PET…** window keeps the hand measurements: the PERCIST threshold, the Deauville and the liver comparison with the previous study already open ready. A reference you measured by hand is never replaced.
- **Registration with the previous PET/CT.** The CT is registered (rotation and translation) with the CT of the patient's most recent previous PET/CT. When opening the previous in a frame beside it (Priors button), the two already scroll together. A registration that already exists between the two studies is not replaced, and a poor-quality registration is not saved (the warning appears in the message).
- **Opens in PET Reading.** The prepared study, still without a saved analysis state, opens with the fused CT, the PET and the rotating MIP. If you already left the study another way, yours applies.

Both options are in Settings ▸ CAD/AI ▸ Tumor burden: *Prepared session…* and *Open the prepared study in PET Reading*. The registration uses up to 60 s.

## Tumor burden on PET: FDG, PSMA and DOTA (0.99.88)

**Burden** button (or Applications ▸ Tumor burden) on a PET/CT. TotalSegmentator finds the organs and bones on the study's CT (and, in PSMA, the salivary glands); the organs are taken to the PET grid. On the PET, everything above the tracer's threshold that is not in a physiological uptake organ (dilated 1 voxel) becomes a **focus**:

- **Tracer**: read from the header (radiopharmaceutical, study or series description). Without it, the calculations are FDG's and the warning says so.
- **Threshold**: FDG — PERCIST (1.5 × liver + 2 SD, by the 3 cm sphere in the segmented liver; without liver, SUV 2.5), or a fixed SUV in the settings; **PSMA** — SUV 3 (qPSMA); **DOTA** — the liver mean (Krenning).
- **Physiological uptake removed**, per tracer: in FDG, brain, heart, kidneys and bladder; in PSMA, salivary glands, kidneys, bladder, liver, spleen and bowel; in DOTA, liver, spleen, adrenals, kidneys, bladder and bowel. The removed list comes out in the warnings — in PSMA and DOTA a liver lesion **does not enter** the calculation.
- Each focus (≥ 0.3 mL, adjustable) has volume, SUVmax, SUVmean, SUVpeak, TLG and **region**: prostate, bone (with the bone's name: L3, 5th right costal arch…), pelvic lymph node (below the iliac crest), extrapelvic lymph node/soft tissue or viscera (lung, liver…). The total **MTV** and **TLG** come out.
- **In PSMA**: the **miTNM** (PROMISE: miT by the prostate, miN1 pelvic, miM1a extrapelvic, M1b bone — uni, oligo up to 3 or disseminated —, M1c viscera) and each focus's **miPSMA score** by the study's references: 0 below the blood pool (aorta), 1 below the liver, 2 below the parotid, 3 above.
- Each focus becomes a finding in **Applications ▸ AI findings**. **Discarding** a focus (inflammation, muscle, brown fat, bowel…) takes it out of the total: the **report** text adds only the confirmed ones and redoes the miTNM. The mask stays in a SEG on the PET (series 987), one segment per region.

These are automatic threshold calculations: check each focus before using the number.

## The AI button (0.100.37)

The AIs live in a single button on the viewer bar: **AI**. It opens a list, like the measurements one, with the AIs that apply to the open study (by the same rule as the smart bar: nodules, emphysema, Genant, aorta and calcium on a chest CT; BraTS and FLAIR lesions on a brain MRI…). Hover over one to see what it does — run on the active frame's series, see the result — and click. At the end of the list: **AI findings** (review, confirm, discard), **AI tasks** (progress and cancel) and **Other AIs**, with those the rule left out, which run anyway. The result opens in each AI's panel, as before.

To have a button for each AI again, check **Show each AI with its button on the bar**, at the end of the same list. The **Applications** button still lists all of them.

## What each AI saves in the study (0.100.124)

Every AI that segments saves a **SEG series** (the masks, which the **CAD/overlay** button turns on and off). Some also save **separate images**: tables of numbers and check images. Mammography saves the study's own image with the marks drawn.

| AI | What it saves |
|---|---|
| Vascular breast calcifications | Mammography image with the calcifications marked, structured report (SR) and summary |
| Breast density | SR and summary image |
| Abdominal organs | SEG and a volume table image (HU, on CT) |
| Spine levels | SEG, tables of disc and vertebra measurements (images) and a second check sagittal with the levels written on it |
| Liver on MRI | SEG, summary image and image of the stiffness region |
| Skull indices and cephalometry | SEG and a check image |
| Lymph nodes, emphysema, aorta, spinal cord, body composition, coronary calcium, nodules, prostate, liver lesions, FLAIR, PET | Only the SEG (the numbers stay in the AI findings) |
| Aligned breast dynamic | Image series (aligned phases and subtractions) |

The table and check images are ordinary images, unrelated to the CAD/overlay: they appear as their own series, with the AI badge, and have the patient's name written on the image (that is why anonymization and meeting mode treat them separately).

### For a PACS that does not show SEG

In **Settings ▸ CAD/AI**, the **What the AIs save and send (all AIs)** group has three boxes and a list of destinations:

- **SEG series**: unchecked, the SEG does not go to the destinations (it stays in Ipê's study, because the CAD/overlay and the measurements depend on it).
- **Tables and check images**: go as an ordinary image.
- **Color overlay series**: the study with the masks painted (translucent core and outline), **one image per slice, at the original slice's position**. Any PACS shows and scrolls it. It is generated from the saved SEG, so it applies to **every AI that saves a SEG**. It comes **off** by default, because it takes space (one color image per slice); it is not made for studies of more than 800 slices nor for multiframe (Enhanced) studies. It appears as the series `… · color overlay · Ipê`.
- **Destinations**: the DICOM nodes that receive what the AIs save. They apply to all the AIs, added to those of each tool.

**In each AI**, in its settings, the **What this AI saves and sends** frame overrides the global choice: SEG, tables and overlay as *As in all AIs / Yes / No*, and the destinations as *those of all AIs and of this tool* or *only this tool's* (with none checked, that AI sends nowhere).

The color series is only made for AIs run after turning the option on; for studies that already have a SEG, redo the AI.

## AI tasks: progress and cancel

Ipê's AIs (abdominal organs, spine levels, cephalometry, skull indices, lymph node levels, mammography implant) run requested by hand or **by themselves when the study arrives** (Settings ▸ CAD/AI). One at a time; the others wait in the queue.

- **AI tasks** shows each one: study, tool, whether it was automatic or by hand, status (queued, assembling the volume, running, saving, done, error, cancelled), the step and the time. It opens from the viewer's **Applications** button, from **View ▸ AI tasks**, and from the **⚙ AI: 1 running, 2 queued** notice that appears in the status bar while any is active (one click opens the window).
- **Cancel the chosen one** (or **Cancel all**): in the queue, it does not start; running, the process is killed and **nothing is saved** in the study. The cancellation goes into the automatic management history. The window is not modal: you can keep working with it open.
- **Closing the study does not interrupt the AI requested on it**: it keeps running and saves the result in the study, which appears when you open it again. If the job does not stop within 15 seconds after Cancel (for example, the process hung), the task is closed by force and the study is freed for the other AIs. With a single active task, Cancel the chosen one works without choosing the row.
- **In the database**, a study that has an AI result gains **✦** beside the name (the hint says which: "AI: abdominal organs, spine"), and one with an AI queued or running, **⚙**. The **AI** column (Columns ▾) shows both in writing.
- **Abdominal organs** in the viewer: **Organs** button (abdomen or pelvis CT/MRI; in other studies, through the **Applications** button) ▸ *Segment abdominal organs of this series (AI)*. It saves the masks and the volume table in the study.

### Installing the segmentation (TotalSegmentator)

The AIs for organs, spine, head and neck, nodules and skull run in a separate Python environment, installed once through **Settings ▸ CAD/AI ▸ Install organ segmentation (TotalSegmentator)…**. You can also run the installer outside Ipê: the `instalar_segmentacao.bat` file is in the program folder, inside `_internal\ipe` (in the source-code version, in the project folder). It needs internet and about 5 GB.

**The installation window.** The installation (that of the segmentation and that of the extra models) runs in Ipê's own window, which does not freeze the program: at the top appear the current step and the elapsed time; in the middle, everything the installer writes, with error lines in red. At the end the window comes back to the front with the verdict — **Installed without errors**, **finished with errors** or **NOT installed** — checked for real (was the environment created? are the models in the folder?), not only by what the installer said. **Copy all** and **Save…** serve to send the output to whoever gives support; the text is also kept in `instalacao_ia.log`, in the logs folder (**Open the log folder**). Closing the window in the middle asks whether to interrupt or only hide; hidden, it comes back through the same menu.

The installer looks for a Python from 3.10 to 3.13 that **really opens** (a broken Python or the Microsoft Store shortcut do not count) and, if there is none, downloads a Python 3.12 just for the segmentation. At the start it lists the computer's Pythons. Windows' PYTHONHOME and PYTHONPATH variables, which make any Python break with *No module named 'encodings'*, are ignored and appear as a warning. An old environment that does not open is deleted and rebuilt; if the folder is stuck, it renames it. Microsoft's **Visual C++ Redistributable** (x64) is only needed for the segmentation, because of PyTorch; Ipê and Python do not need it. Ipê's installer checks whether it exists and, if missing, offers to open the download (https://aka.ms/vs/17/release/vc_redist.x64.exe), and Settings ▸ CAD/AI ▸ Install the segmentation warns the same. After installing PyTorch, the segmentation installer checks that it opens; if it does not (on Windows, the error *WinError 126 … shm.dll*), almost always the **Microsoft Visual C++ Redistributable** is missing, and the installer downloads it from Microsoft and installs it (Windows may ask for administrator permission and, sometimes, a restart). If it still fails, install Python 3.12 from python.org (checking *Add python.exe to PATH*) and run again. If the failure is a network one (messages with *connection*, *timeout*, *SSL* or *proxy*), allow download.pytorch.org, pypi.org and files.pythonhosted.org.

## AI findings and lung nodules

The AIs that **point out** something (the first is the lung nodule one) do not write into the report: each candidate becomes a **suggested finding**, reviewed one by one in the **AI findings** window (**Applications** button ▸ *AI findings…*, or the **Nodules** button's menu).

- Each row says the label (N1, N2…), the type, the location, the measurements, the **state** — *suggested* (amber), *confirmed* (green), *corrected* (blue) or *discarded* (gray) — and who reviewed it and when. Underneath, where it came from: the model and version, the series used and the warnings (thick slice, for example).
- **Go to** (or double-click) takes the frame with the series used by the AI to the finding's slice, with the 3D cursor on top.
- **Confirm**, **Discard**, **Back to suggested**. **Correct…** opens the numbers for you to change (diameter, volume, consistency) and a note; the finding becomes *corrected* and the report carries your numbers.
- **Follow as a lesion** (only on confirmed or corrected): creates the lesion in the follow-up ("N1 (AI)", with the lobe as location) and a measurement — a circle of the diameter, with the volume — on the finding's slice. From then on it enters the follow-up and the doubling time, like any lesion.
- **Send to the report** takes only the confirmed and corrected ones, one sentence per finding ("Solid nodule in the right lower lobe, mean diameter of 6.2 mm and volume of 120 mm³ (N1)."). With no report open, the text goes to the clipboard.
- Running the AI again replaces only the **suggested** ones. What you have already reviewed stays, with its label, and does not return as a suggestion (a candidate within 5 mm, or half a diameter, of a reviewed finding is the same finding).

**Lung nodules** (**Nodules** button, on chest CT; or Settings ▸ CAD/AI ▸ Lung nodules, to run by itself when the study arrives). It uses TotalSegmentator's open *lung_nodules* task (BLUEMIND AI model, trained on 1353 CTs, part of the LIDC-IDRI) and the lobes from the *total* task. For each candidate:

| Number | How it comes out |
|---|---|
| Largest diameter and axes | the three perpendicular axes of the mask |
| Mean diameter | mean of the two largest axes (the "mean diameter" of Fleischner and Lung-RADS) |
| Volume | voxels × voxel volume |
| Mean HU and solid part | mean HU; solid part = voxels from −300 HU |
| Consistency (by HU) | proposed: ≥ 80% solid, ≤ 20% ground glass, in between part-solid |
| Lobe | the lobe of the center (or the nearest, up to 10 mm) |

Candidates smaller than the **minimum diameter** (3 mm by default, of the sphere of equal volume) do not enter; at most the 30 largest remain. The preferred series is the thin-slice lung one; slices above 2.5 mm generate a warning (Fleischner asks for up to 1.5 mm for small nodules). The consistency by HU is a proposal: in a nodule of a few millimeters partial volume lowers the HU, and a solid nodule may look like ground glass. The SEG "Lung nodules · TotalSegmentator" stays in the study, one segment per candidate.

For those who had already installed the segmentation: run *instalar_segmentacao* again to download the *lung_nodules* and *total* models (or they download by themselves the first time, with internet).

**Nodule by click and growth between studies** (0.99.62). On CT, right-click on the nodule ▸ *Lung nodule here (segment by click)…*. It does not need the AI:

- The window segments from the point: the connected voxels above the threshold (−500 HU, the solid part; check *Include ground glass* for −750 HU), in a box of 25 mm radius. *Separate from vessels and pleura* does a 1-voxel opening, which cuts the thin bridge between the nodule and the vessel. The mask appears over the image, in any plane; if it touches the box's edge, the window warns that it leaked.
- The numbers are the same as the AI candidates': largest and mean diameter, volume, mean HU, solid part, consistency by HU, axes; and the lobe, when the study has the lobe segmentation.
- **Save as finding** puts the nodule in the AI Findings list, already **confirmed** (model "Ipê: segmentation by click"). Running the AI again does not delete it. **Save and follow as a lesion** already puts it in the follow-up.
- **The same nodule in the previous study**: the confirmed or corrected nodules of the patient's other studies, carried to this one by the registration, up to 10 mm. Without registration between the two studies, the same lobe and up to 25 mm apply, marked "probable, no registration (check)". The window and the Findings list show the growth: mean diameter, volume and the **volume doubling time** (DT = Δt · ln 2 / ln(V2/V1)).
- If the previous nodule was already in the follow-up, *Follow as a lesion* puts the new measurement **in the same lesion**. The lesion table gains the new study's column, with the doubling time. *Send to the report* adds "Compared with the study of dd/mm/yyyy (N1): …".

**Body composition at L3 and liver attenuation** (**Composition** button, on abdomen CT; or automatic in Settings ▸ CAD/AI ▸ Body composition). The numbers appear as two findings in the same window — "Body composition (L3)" and "Liver attenuation" — to check, correct and send to the report like the others.

- **Where it measures**: the axial slice at the craniocaudal middle of the L3 vertebra (found by TotalSegmentator). The series must be axial; if not, the composition does not come out (the liver still does). *Go to* takes you to the L3 slice, and the SEG "Body composition · TotalSegmentator" shows the four compartments on it.
- **How it separates** (classic thresholds, Mitsiopoulos et al., 1998): muscle from −29 to 150 HU outside the abdominal cavity, the organs and the vertebra; fat from −190 to −30 HU — visceral inside the cavity (open task *trunk_cavities*), subcutaneous in the fat regions that touch the skin, intermuscular the rest. The skin (3 mm from the outside) does not count as muscle.
- **What comes out**: muscle area (SMA, cm²), muscle density (mean HU of the muscle), visceral, subcutaneous and intermuscular fat (cm²) and VAT/SAT. With height, the **muscle index** (SMA/height², cm²/m²), with the sarcopenia reference for the patient's sex beside it — Prado et al., Lancet Oncol 2008: < 52.4 (men) and < 38.5 cm²/m² (women) —, as text, not a verdict. With weight, the **BMI** and the references of Martin et al., J Clin Oncol 2013, which depend on it: sarcopenia with an index < 43 cm²/m² in men with BMI < 25, < 53 with BMI ≥ 25 and < 41 in women; myosteatosis with muscle density < 41 HU (BMI < 25) or < 33 HU (BMI ≥ 25).
- **Height, weight and sex** (0.99.80): on clicking to calculate, a window opens with what came from the file (PatientSize, PatientWeight, PatientSex) to check or type; *Cancel* does not calculate. What you type applies to that study (the file does not change) and is used again if the AI runs once more. After the calculation, **AI findings ▸ Height and weight…** changes the values and redoes the index, the BMI and the references without running the AI. The box *Always ask before calculating* turns the window off; to turn it back on, check the box again in *Height and weight…*.
- **Liver and spleen**: mean and median HU (the edge, 2 voxels, is left out), liver − spleen and liver / spleen. On non-contrast CT the references come as text, both 100% specific for steatosis of 30% or more on biopsy — liver − spleen < −9 HU or liver / spleen < 0.8 (Park et al., Radiology 2006) and liver < 48 HU (Pickhardt et al., Eur Radiol 2012). With contrast (by the ContrastBolusAgent tag or by the series description) the screen warns that these thresholds do not apply.
- **Steatosis result** (0.99.80), which appears under the list in AI Findings and goes to the report together with the numbers:
  - *Compatible with moderate to marked steatosis (≥ 30%)*, when one of the criteria above is met;
  - *Possible mild steatosis*, when the liver is less dense than the spleen (liver / spleen < 1.0) without meeting any;
  - *No CT signs of moderate or marked steatosis*, otherwise — CT does not exclude mild;
  - *Not classified* on the contrast series.
- **Opportunistic bone density** (0.100.129): on the same **non-contrast** abdomen CT, Ipê measures the HU of the **trabecular bone** of **L1** and of **L1 to L4** (volume-weighted mean) as a third finding, "Bone density (CT)". The ROI sits inside the vertebral body: the cortex, pedicles and posterior venous plexus are left out (5 mm margin) and only the central third of the vertebra is used, away from the endplates. Mean, median, standard deviation and volume are given per level; the ROI appears in the "Body composition · TotalSegmentator" series. The provisional L1 result follows Pickhardt et al. (Ann Intern Med 2013): ≤ 110 HU compatible with osteoporosis, ≤ 135 low density, 135 to 160 gray zone, > 160 no signs of low density; the three cutoffs and the margin can be edited in Settings ▸ CAD/AI ▸ Body composition. For **L1 to L4 there is no validated cutoff**: Ipê only shows the HU (and compares it with a cutoff of yours, if you type one); to find your service's, run the batch on exams that have spine and femur DXA and compare in Excel (Batch search ▸ AI results). Series with contrast or a kVp other than 120: measured but not classified. Reference text, never a diagnosis: DXA remains the standard.
  
  If you correct the liver's or the spleen's HU, the result follows; in *Correct…* you can write another result.
- **Body composition and bone table** (0.100.132): **Reports ▸ Body composition and bone density: measurements and confirmations…** (or, in the viewer, the menu of the body composition tool). One row per study with muscle, fats, liver and the HU of **L1** and **L1–L4**, with the review status. Type the DXA T-score in the **DXA spine (T)** and **DXA femur (T)** columns (kept with the study; the worse of the two counts) and click **Compare with DXA…**: Ipê shows the AUC and the **best cutoff** of L1 and L1–L4 from the ROC curve (osteoporosis: T ≤ −2.5; low density: T < −1.0), with sensitivity and specificity at your current cutoffs. The CSV carries the whole table, with the DXA.
- Run *instalar_segmentacao* again to download the *trunk_cavities* model.

**Liver fat and iron on MRI** (**Liver** button, on abdomen MRI; or automatic in Settings ▸ CAD/AI ▸ Liver fat and iron). The liver, spleen and Couinaud segments come from TotalSegmentator (*total_mr* and *liver_segments_mr*), run on an axial anatomical series of the abdomen (by default, the "WATER" of the LAVA/Dixon; the pelvis one is left out); the mask is carried point by point, by position in the patient, to the grid of each map — which is usually thicker (in the archive's IDEAL IQ, 16 mm slices every 8 mm). The liver's edge (1 voxel in the plane) is left out. Up to three findings come out, in the AI Findings window:

| Finding | From where | Numbers |
|---|---|---|
| Liver fat (PDFF) | the device's fat fraction map (IDEAL IQ, mDIXON Quant, LiverLab), recognized by the ImageType FAT_FRACTION or by the description | median, mean, p25 and p75 (%), and the median of each segment |
| Liver iron (R2*) | the R2* map (or T2*, converted: R2* = 1000 / T2*) | median R2* (s⁻¹), T2* (ms), spleen R2*; at 1.5 T, the estimated iron |
| Liver fat (dual echo) | the in-phase / out-of-phase dual echo (both echoes in the same series, or the InPhase/OutPhase pair) | fat **signal** fraction = (IP − OP) / (2 · IP), and the IP/OP ratio |

- **Estimated iron**: LIC = 0.0254 · R2* + 0.202 mg Fe/g dry weight (Wood et al., Blood 2005), a 1.5 T calibration. **At 3 T** (0.99.50) the liver R2* is divided by 2.05 for the 1.5 T equivalent (Alam et al., JCMR 2016: liver R2* at 3 T was 105% higher) and then enters Wood's formula; the finding also shows that equivalent R2*. At 3 T a very short T2* is measured worse: in severe overload, prefer 1.5 T. At another field strength (or without the field in the file) it does not estimate.

- **Iron by both formulas** (0.100.126): besides Wood, Ipê calculates the LIC by **Hankins et al. (Blood 2009)**, LIC = 0.02802 · R2* − 0.45485 mg Fe/g, on the scanner's R2* (never below zero). The **MR field strength is read from DICOM** and shown next to the iron. The main LIC and the classification use, by default, **Wood at 1.5 T and Hankins at 3 T**; in Settings ▸ CAD/AI ▸ *Iron (LIC) formula* you can fix Wood or Hankins. Both appear in the panel, the image summary and the Excel file.
- **LIC range** (reference text, not a verdict): 3.2–7 mild, 7–15 moderate, > 15 mg Fe/g severe.
- **Fat reference**, as text: PDFF ≥ 6.4% grade ≥ 1, ≥ 17.4% grade ≥ 2, ≥ 22.1% grade 3 — high-specificity thresholds in fatty liver disease (Tang et al., Radiology 2015).
- The dual-echo signal fraction **is not PDFF**: it does not correct for T1 or T2*. In-phase with a signal lower than out-of-phase suggests iron — and then the fat comes out underestimated.
- **Redoing the measurement (0.100.89; in all AIs since 0.100.90)**: with findings in the study, the AI button only opens the review. To measure again, use the button's small arrow ▸ **Redo in the study (preferred series from Settings)…** — it is in **every** AI: abdominal organs, spine levels (in the Genant menu), cephalometry, skull indices, lymph node levels (the button gained a menu), nodules, composition, liver on MRI, emphysema, Genant, liver lesions, autoPET, BraTS, FLAMeS, spinal cord, aorta, calcium, PET burden, prostate and PI-CAI; in breast density and vascular calcifications it is **Redo the measurement in the study (in the background)**. The same item appears in the AI button's list. The series is the one the AI's rule chooses in the study (Settings ▸ CAD/AI); if it is not on screen, it goes into the active frame. The suggested ones are replaced by the new ones; if there are already confirmed or corrected findings, Ipê asks whether to discard the old ones. The "… on this series" item still runs on the active frame's series.
- **Suggested classification (0.100.88)**: as with the breast vascular calcifications, the AI Findings window has the **Classification** column and, on choosing the finding, the table of scales (hover to see where each one comes from). **Fat**: PDFF < 5% no steatosis; 5–6.4% slight steatosis; and the histological grade estimated by Tang's thresholds (6.4% grade 1 mild; 17.4% grade 2 moderate; 22.1% grade 3 marked). **Iron**: by the LIC, < 1.8 no overload; 1.8–3.2 above normal; 3.2–7 mild; 7–15 moderate; > 15 severe; beside it, the liver R2\* and the spleen's. It is a suggestion: in **Correct…** you can change the classification, and the report sentence uses whichever applies (the PDFF one goes at the end of the sentence: "… — mild steatosis (grade 1)"). Also in Ipê Web.
- **Which series is a map (0.100.87)**: the water and fat images of IDEAL IQ ("WATER: IDEAL IQ (R2\*)", "FAT: …") are **not** a map — the "(R2\*)" is the sequence's name. Up to 0.100.85 they were taken for the R2\* map and, coming after it, the iron came out of the water or fat signal: **redo the iron for GE studies with IDEAL IQ measured before**. Now the ImageType rules; with more than one map of the same type, the one the ImageType confirms stays and, among those, the one with the most slices (IDEAL IQ's R2\* covers the liver; STARMAP's, 3 slices).
- **Water-fat swap (0.100.87)**: Dixon sometimes swaps water and fat in a region (at the dome, near the lung, and with a lot of iron) — the fraction becomes 100 minus the true one (in one study, 10% in the liver and 92–98% at the dome). When part of the liver goes above 60% and the rest is well below 35%, those voxels are left out of the calculation, with a warning. With R2\* ≥ 400 s⁻¹ (1.5 T) the warning also comes that the PDFF becomes less reliable.
- **Validation (0.100.87)**: on three GE 1.5 T MRIs, with the liver found on different series (IDEAL IQ water, IDEAL IQ fat, the fat map itself, LAVA water, 3D dual echo), the PDFF varied at most 3 points and the R2\* at most 26 s⁻¹ (5%). IDEAL IQ's R2\* matched an independent fit of STARMAP's 16 echoes: 53 × 61–65, 183 × 175–185 and 558 × 570 s⁻¹.
- A fat map in 0–1000 (some manufacturers) is read as tenths of a percent, with a warning. By hand it still works: an ROI on the map itself shows the mean in % (or in s⁻¹ on the R2* one).
- **Liver stiffness on elastography (0.100.94)**: if the study has MR elastography (MR-Touch and the like: the elastogram in Pa, ImageType ELASTOGRAM), the same calculation measures the **stiffness** with an automatic ROI, without a neural network in the measurement — like the hand ROI, slice by slice: TotalSegmentator's liver carried to the elastogram grid, **at ≥ 5 mm from the edge** (capsule, fissures and the misalignment between breath-holds), **inside the device's confidence area** (on GE, the "STGRYM" elastogram has the bad area hatched in a checkerboard; Ipê compares with the whole "STGRY"), **without the large vessels** (magnitude of the acquisition itself below half that of the liver) and without small islands; a slice with less than 1.5 cm² of ROI is left out. The finding's number is the **area-weighted mean** (the report's), with the median, p25–p75, the measured area, the slices, how much of the liver was inside the confidence and the **heterogeneity** (CV between slices and IQR/median). With two acquisitions (e.g. *Standard* and *Short T2\**), it measures both: the one with more area goes as the main one and the other as an extra number. Reference range, as text (2D, 60 Hz — Venkatesh, Yin & Ehman, JMRI 2013): < 2.5 kPa normal; 2.5–2.9 normal or inflammation; 2.9–3.5 stage 1–2 fibrosis; 3.5–4.0 stage 2–3; 4.0–5.0 stage 3–4; > 5.0 stage 4 or cirrhosis. The series **"Liver stiffness: automatic ROI"** is saved: the color elastogram (0–8 kPa), the low confidence in gray, the liver in yellow and the ROI with a white outline with a black edge, with each slice's value — to check before sending the number to the report.

**Each AI's settings in the menu (0.100.90).** Settings ▸ CAD/AI lists all the AIs, one per item; each opens its page in the CAD/AI tab (automatic on arrival, preferred series, destinations, options).

**Running on the frame's series (0.100.85).** Each AI has, in the AI button's menu (or in its own button), the "… on this series" item: it runs on the active frame's series, even if it is not the one preferred in Settings. If it errors, the message says which series is recommended for that AI. Clicking the button still uses the preferred series (FLAIR, axial T2, the PET/CT's CT…). In Ipê Web, the AI tab lets you choose between the suggested series and the frame's.

### Emphysema by lobe (0.99.77)

On chest CT, the **Emphysema** button (or Applications ▸ Emphysema) separates the five lobes by AI and measures, in each lobe, in each lung and in total, the **%LAA−950** (fraction of the volume below −950 HU), the **Perc15** (the HU of the 15th percentile) and the volume, and says the distribution (upper, lower or homogeneous predominance). The result goes to the AI Findings, as an "Emphysema (%LAA−950)" finding, and the areas below −950 HU stay in a SEG that appears only on the calculated series.

The number depends on the technique, and the review warns: thin slice (≤ 1.5 mm), soft filter (B30, STANDARD; a lung or bone filter increases the noise and the %LAA), without contrast and in full inspiration; the median of the tracheal air checks the calibration (near −1000 HU). Preferably use the thin soft-filter series, if there is one. The reference (the −950 HU threshold validated by Gevenois et al., 1996; %LAA above ~5–6% is usually treated as relevant emphysema) goes as text beside it, not as a verdict.

**Noise (0.100.81).** The noise of a hard filter puts little dots below −950 HU in the whole lung and inflates the %LAA. So, on a noisy series (hard filter, or tracheal air standard deviation above 30 HU), Ipê applies a light Gaussian filter (σ 0.8 mm) before the threshold — the finding says when it did so. It is turned off in **Settings ▸ CAD/AI ▸ Emphysema**. Since 0.100.85 the preferred series is the **parenchyma/lung** one: in a study with both, the parenchyma one (with noise reduction) gave the report's result and the mediastinum one was wrong.

### Vertebral fracture — Genant (0.99.77)

On CT or MRI with the thoracic or lumbar spine, the **Genant** button (or Applications ▸ Genant) names the vertebrae (the same rule as the Spine, with the AI at full resolution), measures the anterior, middle and posterior height of each body and calculates the height loss: **wedge** (anterior against posterior), **biconcave** (middle against posterior) or **crush** (posterior against the mean of the two neighbors). From T4 to L5, 20–25% is grade 1 (mild), 25–40% grade 2 (moderate) and over 40% grade 3 (severe), by Genant's semiquantitative classification (1993).

Each vertebra with grade 1 or more becomes a "Vertebral fracture (Genant)" finding to confirm, correct or discard — deformity is not a synonym for fracture (variant, Scheuermann, Schmorl's node, degeneration), so check on the sagittal. A summary finding says how many vertebrae were measured; confirmed with none altered, it enters the report as "vertebral bodies without height reduction of 20% or more". A vertebra already reviewed does not return as a suggestion when the AI runs again.

### Liver lesions and burden per segment (0.99.82)

On abdomen CT or MRI, the **Lesions** button (or Applications ▸ Liver lesions) runs two open TotalSegmentator tasks — the eight Couinaud segments and the liver's focal lesions — and measures:

- for each lesion (up to 20, the largest): volume, largest axial diameter, mean HU (CT) and the segment where most of it is; each one becomes a "Liver lesion" finding to confirm, correct, discard or link to a follow-up lesion;
- in the summary: number of lesions, total volume, **burden** (% of the liver volume occupied by lesion), liver volume and each segment's burden.

The model does not say what the lesion is (cyst, hemangioma, metastasis): it is count and volume. It works best in a contrast phase (portal or hepatobiliary) and thin slice; the review warns when that is not the case. The masks (lesions and segments) stay in a SEG that appears only on the calculated series and in the 3D, under *Structures*.

### Coronary calcium — Agatston (0.99.89)

On **non-contrast** CT (calcium score or chest CT), the **Calcium** button (or Applications ▸ Coronary calcium) measures the Agatston score:

- **Organs**: TotalSegmentator finds the heart, the aorta and the chest bones (sternum, costal cartilages, ribs, vertebrae). Calcium is searched around the heart, with an 8 mm margin, which is where the coronaries run; bone is left out.
- **Agatston**, slice by slice: pixel ≥ 130 HU, lesion of at least 1 mm² in a slice, weighted by the maximum HU (130–199 = 1, 200–299 = 2, 300–399 = 3, ≥ 400 = 4), score = area × weight × thickness ÷ 3 mm. The **volume** (mm³) also comes out. Thin slices (up to 2 mm) are **added into ~3 mm slabs** (mean of the HU), like the reconstruction in which the score was defined: thin slices increase the score. Threshold, smallest lesion and the slice summing are in Settings ▸ CAD/AI ▸ Coronary calcium.
- **Suggested vessel** for each lesion, by position: near the aortic root and to its left, **LM**; around the heart, anterior and to the left **LAD**, to the left and behind **LCx**, to the right and posteroinferior **RCA**. TotalSegmentator's coronary task requires a license, so the vessel is a suggestion: check on the SEG (one color per vessel) and correct.
- **Outside the coronary score**, apart: calcium against the **aorta** (includes the root and the aortic valve) and what is more than 5 mm **inside the heart** (valve, mitral annulus).
- **Result**: the total and per-vessel Agatston and volume, the **CAC-DRS** (A0 = 0, A1 = 1–99, A2 = 100–299, A3 ≥ 300, with N = number of vessels with calcium) and the SCCT/STR category for chest CT (none, mild, moderate, severe).
- **AI findings**: one summary and one finding per vessel. To move a lesion to another vessel, correct the Agatston of both vessels; discarding a vessel takes it out of the total. The report text redoes the total, the CAC-DRS and the category with the confirmed or corrected vessels.

Warnings: with contrast the score is **not measured** (blood goes above 130 HU); CT without ECG gating (motion underestimates the score); kV other than 120; thin slice without summing or a thick slice. The percentile by age and sex (MESA) is not calculated.

### Aorta: diameter by segment (0.99.90)

On chest or abdomen CT, with or without contrast, the **Aorta** button (or Applications ▸ Aorta) measures the aortic diameter **perpendicular to the axis**, automatically:

- **Centerline**: TotalSegmentator finds the aorta and the landmarks (brachiocephalic trunk, left subclavian, T12, kidneys). The program traces the line through the middle of the aorta, from the root (when the series includes the heart) to the bifurcation or the end of the series, and adjusts it to the center of each perpendicular slice.
- **Perpendicular planes** every 2 mm: in each one, the **maximum diameter**, the one **perpendicular** to it and the diameter by area.
- **Segments** and the largest diameter of each: **root** (the first 15 mm), **ascending** (up to the brachiocephalic trunk), **arch** (up to 10 mm after the left subclavian), **descending thoracic** (to the lower edge of T12), **suprarenal abdominal** (to the middle of the kidneys) and **infrarenal**. Without the arch branches, the arch is the 30 mm stretch on each side of the highest point; on an abdomen-only series only the abdominal segments come out.
- **AI findings**: one summary and one finding per segment; clicking goes to the point of the largest diameter. The SEG paints each segment a color. The report text carries the confirmed or corrected segments ("Ascending aorta: maximum diameter 46 × 45 mm, perpendicular to the axis, outer wall").

The measurement is **outer wall to outer wall** (the mask takes in the wall and thrombus). ACC/AHA (2022) asks for the root and the ascending aorta from inner edge to inner edge, on ECG-gated CT; without ECG, the root does not count. The references appear as text in the finding, never as a verdict: ascending, arch and descending ≥ 40 mm are usually reported as dilation, and ≥ 55 mm is the surgery threshold (ACC/AHA 2022); in the infrarenal, an aneurysm is ≥ 30 mm, with the ACR (2013) follow-up interval for the measured size.

### Extra models: MedSAM2, autoPET, BraTS, FLAMeS and spinal cord

(The **research** models for the prostate are separate, with their own license: see *PI-RADS (prostate MRI)*.)

Five AIs that do not come with the segmentation and are installed once, with internet, in **Settings ▸ CAD/AI ▸ Install the extra models (MedSAM2, autoPET, BraTS, FLAMeS, spinal cord)…** (the window says what is already ready and what is missing). They run in the same environment as TotalSegmentator, on CPU. Before anything, the window checks whether the environment's **PyTorch and torchvision** match and, if not, reinstalls both together: it is the fix for the error *operator torchvision::nms does not exist*, which takes down the whole TotalSegmentator (emphysema, organs, everything) when some `pip install` swaps one of the two.

- **Segment by box (MedSAM2).** A left-button tool (*Left button tool ▸ Measure*): draw a box around the lesion on a slice of the original series. MedSAM2 makes the contour on that slice and propagates it up and down (up to 60 slices on each side); only the part contiguous with the box's slice remains. The window that goes into the model is the screen's — adjust the window so the lesion shows well before drawing. The result opens in the **3D Segmentation** window (method *AI: contour by box*), with volume, axes, SUV on PET, link to a follow-up lesion and save the SEG. It works for CT, MRI and PET.
- **autoPET (lesions on FDG PET).** **autoPET** button (or Applications ▸ autoPET) on the PET of a PET/CT: the nnU-Net from the autoPET II challenge finds the avid lesions (leaving out the physiological uptake of brain, heart, kidneys and bladder) using the PET in SUV and the study's CT resampled to the PET grid. The **MTV** (total metabolic volume), the **TLG** and the SUVmax come out, and each lesion (up to 20) with volume, SUVmax, SUVmean, SUVpeak and TLG, as a finding to check — discard the physiological uptake that slips through. It needs the SUV factor (weight, dose and times in the file).
- **BraTS (glioma on MRI).** **BraTS** button on a brain MRI with post-contrast T1, T1, T2 and FLAIR: the program finds the four by the description, registers the T1, T2 and FLAIR to the post-contrast T1 (rigid registration), strips the skull (TotalSegmentator's brain) and MONAI's SegResNet separates the **enhancing** part, the **necrosis** and the **edema**, with the volumes and the largest axial diameter of the enhancing part. One finding to check; the review warns when the registration ended with low similarity. It is MONAI's example model, trained on BraTS 2018 — check each part.
- **FLAMeS (white matter lesions on FLAIR).** **WM lesions** button on a brain MRI: the program finds the study's FLAIR (the one with the most slices; the "T1 FLAIR" does not do), strips the skull with SynthSeg and FLAMeS marks the hyperintense lesions. One finding comes out with the **number of lesions**, the **total volume**, the count by region — **periventricular** (touching a lateral ventricle), **juxtacortical/cortical** (touching the cortex), **infratentorial** (brainstem and cerebellum) and **deep** — and the largest lesion. If a previous study of the same patient has already been through the tool, the finding and the report sentence bring the comparison of number and volume (it is not lesion-by-lesion pairing). The lesions stay in the series **FLAIR lesions · FLAMeS**, colored by region. A research model made for multiple sclerosis and for 3D FLAIR: it marks any white matter hyperintensity, without distinguishing the cause, and misses small lesions on thick 2D FLAIR (the program warns). The download is 2.4 GB; on CPU the analysis takes several minutes.
- **Spinal cord and canal (TotalSpineSeg).** **Cord** button on spine MRI (preferably the sagittal T2; any contrast and orientation work): TotalSpineSeg segments the cord, the canal, the discs and the vertebrae, already with each level's name. Ipê traces the cord's centerline and measures at each disc, in the **plane perpendicular to the cord**: the **area**, the **anteroposterior** and the **transverse** diameter, the **compression ratio** (AP ÷ transverse), the **canal's** AP, the canal occupancy by the cord and the **MSCC** and **MCC** indices (Fehlings 1999: 1 − diameter at the disc ÷ mean of the diameters at the middle of the bodies above and below). Each disc is a finding to check; the summary says the level of greatest MSCC. The cord and canal stay in the series **Cord and canal · TotalSpineSeg**. On a 2D sagittal of 3–4 mm, the area and the transverse are approximate (the program warns); the AP, MSCC and MCC are valid. Always check the level names. TotalSpineSeg is installed in an **environment of its own** (about 1 GB) and downloads the model (2 GB) on first use; it needs about **8 GB of free memory** and takes several minutes on CPU.

## CAD, AI and annotations from other systems

The **CAD/AI** button gathers what another program wrote about the study: SEG (segmentations), GSPS (graphic annotations from the device or workstation), SR (CAD/AI findings) and RTSTRUCT (radiotherapy contours). The number on the button says how many objects the study has; the menu lists them one by one, with *Go to the image* for each finding.

**In any plane.** Segmentations (SEG, including TotalSegmentator's: organs, cephalometry), contours (RTSTRUCT), spine levels, segmented lesions and automatic measurement lines also appear when the frame is reformatted (sagittal, coronal, oblique MPR) or on another series of the same study in another plane: the mask saved slice by slice is stacked into a volume in millimeters and cut by the frame's plane. **Exception (0.99.65):** the abdominal organs and the lymph node levels appear only on the series in which they were calculated (and on its reconstructions): on another series the patient has already moved, and the same position in millimeters does not land in the same place. What is 2D only (mammography, mammography CAD, graphic annotations attached to an image) stays only on the source image.

**How long opening takes, and where.** Each study opened leaves a line in the log (`Logs\dicomviewer.log`, in the data folder), for example *Opening (MG DIGITAL MAMMOGRAPHY): first image in 0.84 s — database 0.02 · bar 0.21 · strip 0.05 · protocol 0.30 · window 0.03 · state 0.04 · image 0.19*, and a second one when the AI overlays finish loading. It is what you can send when opening seems slow. **Since 0.100.60**, Ipê Web also leaves its own in the server log: *Web opening (MR, 14 series): first image in 1.92 s — series 0.21 · study 0.05 · screen 0.10 · protocol 0.20 · image 1.36 | Firefox 160 1628x1064 | 0.100.60* and, with all the images in the browser, *…: everything available in 12.40 s — 1830 images · 85.2 MB at 9.1 MB/s · decoding 6.2 ms* (only modality, counts and times). In **client mode** (0.100.61), the desktop Ipê lines also go to the server's log, as *Client opening (…) | user@computer | version* — the *server* step is the wait for the first images. Tomosynthesis (0.100.60) has the header and the slice positions read once per file and is decoded without holding up the screen. Images in JPEG-LS (Ipê's lossless compression, which keeps all mammography) are read by the CharLS decoder, about twice as fast as the previous one on a mammogram, and the decoders and modules for opening are loaded a few seconds after the program opens, so the first study does not pay for them.

**Large SEGs open in the background.** A TotalSegmentator organ SEG has thousands of frames. The study opens first, with the image on screen, and the SEG is read separately; the status bar shows *Reading the study's AI segmentations…* and the colors come in within a second or two. Reopening the same study in the same Ipê session is immediate: the SEG already read is kept in memory (up to ~800 MB of masks) while the file does not change.

**Read first, see the CAD later.** In Settings ▸ CAD/AI, *Read first, see the CAD later* makes the CAD marks (mammography CAD and other CAD SRs) start **hidden** in each study. Read the study and use **CAD/AI ▸ Reveal the CAD** (or the *Reveal the CAD* shortcut key): the marks appear and the status bar says how long the reading took beforehand. The other overlays (SEG, Ipê's AIs) do not change.

Clicking the button shows or hides all of them. The choice is saved by type: if you turned off an AI's segmentations, they are born hidden in the next studies — and the annotations the technologist left on the device still appear. When something is born hidden, the status bar says how many are hidden.

## Structures: editing masks (SEG / RTSTRUCT)

In the small arrow ▾ of the **3D** button ▸ *Structures: edit masks* (or in the **CAD/AI** button's) — or simply start painting with the **Brush** tool (*Left button tool ▸ Draw ▸ Brush*): the panel opens by itself, with a new structure. It opens a window, beside the viewer, to **correct and organize** the study's masks — the lesion that the 3D segmentation or the dynamic capture took with a vessel attached, the organ that the AI outlined badly — and save them in the study.

![The Structures panel: the list, the brush, the editing limits and the corrections (grow, shrink, holes, interpolate).](estruturas_painel.png){60}

- **Reference series**: the active frame's when the window opens. The structures are kept on its grid, but appear on **all series and planes** of the study, and the brush paints on any frame of the study, in the plane that is on screen (including MPR).
- **List**: for each structure, *View* (show/hide; double-click changes the color), name (editable), type (lesion, organ, other), volume in mL, *Locked* and where it came from. Underneath, the numbers of the chosen one: volume, voxels, slices, the three axes, mean ± deviation, minimum, maximum, **median, 10th and 90th percentiles, skewness, kurtosis, entropy and uniformity** (the pyradiomics/IBSI definitions), **largest diameter (Feret), sphericity, elongation and flatness**, and how many separate islands it has. **Copy the numbers** puts one row per structure, tab-separated, on the clipboard — it pastes straight into the spreadsheet. Sphericity is calculated from the surface mesh; in a small structure (radius of less than about 10 voxels) it is approximate.
- **New** creates an empty structure; **Import from the study** brings a saved lesion, a SEG segment (including the AI's: organs, cephalometry, implant), an RTSTRUCT contour — or all of them. While the copy is edited, the original leaves the screen; it returns on closing.
- **Brush / Eraser** (left button; the right still does zoom/pan): the circle around the mouse is the brush size (*Radius*, in mm). By default it is a disc in the screen plane (only the slice you see); **3D sphere** also paints the neighboring slices. **Only in the click's range ±** paints only the voxels of intensity similar to the point where the stroke starts (the range is in % of the series' intensity range): the brush does not leave the lesion for the fat. The brush never paints over a **locked** structure — lock the organ and paint the lesion next to it.
- **Editing limits** (apply to the brush, grow, fill holes and interpolate — what *enters* the structure; erasing is not limited): **Area** everywhere, *only inside* a structure (paint the lesion without leaving the organ) or *only outside the other* visible ones; **Only intensities between** min and max (nothing enters outside the range, in any tool); **Overwrite the others**: what the structure gains comes out of the other unlocked ones (each keeps its own undo) — without it, the structures can overlap.
- **Correct the chosen structure**: **Grow / Shrink** (margin in mm, in a ball with the real spacing; *only in the slices* does not go to the slice above and below); **Only the largest island** and **Remove islands smaller than** N mL; **Fill holes** (slice by slice); **Interpolate slices** — draw every 3 or 4 slices and the empty slices between two drawn ones come out by the intermediate shape; **Trim outside** (removes the voxels with intensity outside the range); **Merge with / Subtract / Intersect with** another structure creates a new one (for example, *lesion minus necrosis*). **Undo** and **Redo** (Ctrl+Z / Ctrl+Y), per structure.
- **“More tools” tab** (0.100.67). The **Undo / Redo** buttons stay under the tabs and apply to both. The mouse tools here use the left button, like the brush (turning one on turns the brush off). They are the eight tools below.
- **Scissors**: draw a shape over the image (*freehand*, *rectangle* or *ellipse*) and the chosen structure is cut by it — **Erase inside**, **Erase outside** or **Fill inside** —, **only in this slice** or in **all slices** (the shape goes through the volume in the direction you are looking; on a coronal MPR, it cuts front to back). It is the quick way to remove a vessel or a rib that came along.
- **Contour by level**: click on the lesion and drag. The slice's region enters, connected to the point, limited by the line of the same intensity that passes through it (the lighter or the darker side, whichever is smaller — it works for bright and dark lesions). Near the edge it takes the whole lesion; further inside, only the core. The contour follows the mouse; release when it is good. *Erase instead of add* takes the region out of the structure. On a very noisy image the contour comes out jagged: prefer the brush with *Only in the click's range*.
- **By the largest diameter**: trace the lesion's largest diameter, edge to edge. Ipê compares the intensity along the line with that of a shell around it, finds the threshold in the middle and returns the **3D contour** in a new structure, with the **largest diameter**, the **short axis** (both on the slice where the lesion is largest, as in RECIST) and the **volume**. Came out small or large? Change the **Adjust** (− tighter, + looser): the contour is redone at once, without redrawing. When the contrast with the surroundings is low, a warning appears to check. It is a threshold contour, not an AI: a lesion stuck to a structure of the same intensity leaks — correct it with the scissors.
- **Hollow (shell)**: replaces the structure with its shell, with the chosen thickness, *inward from the edge*, *outward* (the ring around the lesion, to measure perilesional enhancement) or *half on each side*.
- **Smooth**: **median** (removes spikes and closes small holes), **opening** (removes spikes and thin bridges) or **closing** (closes holes and indentations), with the radius in mm.
- **Automatic threshold (Otsu)**: finds by itself the cut that best separates light from dark — on the series or, with the *Only inside* limit, only inside that structure — and puts it in the range beside (*above* or *below* the threshold). **Fill by range** makes the chosen structure everything that is in the range (it respects the limits' *Area*: use *Only inside* so it does not take the whole study).
- **Split islands into structures**: each loose piece becomes a structure (the chosen one keeps the largest) — one lesion per row, each with its volume. Pieces smaller than the value beside are erased.
- **Grow from seeds**: paint a few strokes inside the lesion in one structure and, in another (call it *Background*), a few strokes in what surrounds it — on two or three slices. Each voxel of the region around the seeds (up to the *Margin*) goes to the seed it connects to through the path of least intensity change. It uses all visible structures as seeds; locked ones serve as seeds and do not change. If it leaked, paint one more *Background* stroke where it leaked and run again. To undo, use *Undo* on each structure. Afterwards delete the *Background*.
- **Save SEG**: all the structures in a series *Structures (Ipe)* of the study, as DICOM SEG (voxel-by-voxel mask, with each one's type: lesion or organ). It goes to the PACS with the study and opens in 3D Slicer and other viewers — and appears here again, through the CAD/AI button.
- **Save RTSTRUCT**: the radiotherapy contours, slice by slice, which the planning system reads directly. The contour follows the pixel edge (filled by the centers, as planners do, it gives the same mask); a hole becomes a second contour inside the first. A lesion comes out as GTV, an organ as ORGAN.
- **Update the saved lesion**: for the structure that came from a segmented lesion, the measurement gets the corrected mask, volume and axes — and it is that volume that lesion follow-up uses.
- **Send to the report**: one row per structure, with the volume and axes.

On closing with altered and unsaved structures, the window asks whether to save them as a SEG.

> **A drawing burned into the pixels is not an overlay.** When the AI saves the result as a series of new images, there is no way to turn it off: the way is to **Hide** the series with the right button in the series list.

## Fusion

**Fusion** button: overlays one series on another in the active frame (PET on the CT, for example), with opacity, color table and minimum and maximum limits, and the option to hide what is below the minimum.

![Fused PET/CT: the PET (in SUV, hot iron color) over the CT, with opacity, color and PET window on the top bar.](pet_fusao.png)

**Fuse by dragging** (0.99.64): drag a series from the strip to the frame's **lower left corner** ("Fuse on top") — it enters as a fusion, in color and with transparency, instead of replacing the series. To fuse what another frame shows — a dynamic map (SER, enhancement, kinetic…), a phase, the ADC —, right-click on it ▸ **Frame ▸ Fuse this frame over…** ▸ the destination frame (ADC over the T2, kinetic over the DWI). The fusion uses the patient's coordinates: series of different frames of reference get a warning to check the alignment.

# Guided measurements

**Indices** button (appears in brain MRI and CT; in other studies, through the **Applications** button). It opens a window, on top of the viewer, with a **script**: the list of measurements, one at a time, each with the right tool and the plane in which it should be made. When you click **Measure this step**, the step's tool goes to the left button; the next measurement of that type, in any frame, becomes the step's value, and the script moves on by itself. The measurement remains an ordinary measurement, visible in the frame and in the measurements panel.

Default scripts:

| Script | Measurements | Calculation |
|---|---|---|
| MRPI and MRPI 2.0 | areas of the pons and the midbrain (midsagittal), middle cerebellar peduncle (sagittal) and superior (oblique coronal), and, for 2.0, the 3rd ventricle (three measurements) and the frontal horns (axial AC-PC) | MRPI = (pons ÷ midbrain) × (MCP ÷ SCP); MRPI 2.0 = MRPI × (3rd ventricle ÷ frontal horns) |
| Evans index | frontal horns and inner skull diameter, on the same axial | horns ÷ skull |
| Callosal angle | angle on the coronal perpendicular to the AC-PC, at the posterior commissure | — |
| Olfactory bulbs | outline of the right and the left bulb on each coronal T2 slice (planimetry) and, optionally, the depth of the olfactory sulcus in the plane tangent to the back of the globes | volume = sum of the areas × distance between slices (Cavalieri), in mm³; outlining again on the same slice replaces the previous one |

The plane and the slice thickness are checked and become an **observation** beside the number, not a refusal: a measurement in a plane different from the one asked, or on a slice above 3 mm, appears with ⚠. In studies with a 3D series, use the MPR to reach the right plane. The reference values appear as text beside the number, with the source — the program does not classify. **Copy the text** and **Send to the report** take the result in list format, with the references in parentheses.

## Automatic skull indices (SynthSeg)

In the **Indices** button (brain MRI and CT): **Automatic indices (AI, SynthSeg) of this series…**. The active frame's series (preferably the 3D T1; any sequence works, including post-contrast and 2D, and CT) goes to SynthSeg, which separates the ventricles, hippocampi, amygdalae and the rest of the brain. The calculations are done by Ipê:

| Measurement | How it comes out |
|---|---|
| Evans index | greatest width of the frontal horns (lateral ventricles in front of the 3rd ventricle, both sides on the same slice) ÷ greatest intracranial diameter on the same axial |
| 3rd ventricle | transverse width at 25%, 50% and 75% of its length; the mean counts |
| Callosal angle | on the coronal of the posterior end of the 3rd ventricle (posterior commissure): lines through the superomedial walls of the lateral ventricles |
| Volumes | hippocampi (with the asymmetry), amygdalae, ventricles and estimated intracranial volume |

The check window is the same as the cephalometry one: value, reference, whose number it is, **See in the frame**, **Measure by hand** and the text for the report. Changing the horns or the diameter redoes the Evans. The measurements are made on the 1 mm segmentation that SynthSeg produces from any series (even a 5 mm 2D one), on the **device's axes**, not reoriented to the AC-PC: with the head tilted, check in the right plane. When opening the **MRPI and MRPI 2.0**, **Evans index** and **Callosal angle** scripts, the steps the AI measures already come filled in ("measured automatically (SynthSeg)"); **Redo** measures by hand. Pons, midbrain and peduncles stay by hand: SynthSeg does not separate the pons from the midbrain.

The study keeps the SEG **Brain · SynthSeg** and the image **Skull indices: check · SynthSeg** (axial of the horns, coronal of the posterior commissure and the list). Automatic on arrival: **Settings ▸ CAD/AI ▸ Skull indices (SynthSeg)…**. It needs instalar_segmentacao to be run once more, which adds DIPY and the SynthSeg weights.

## Synthetic 1 mm T1 (SynthSR)

For brain studies **without a 3D T1** (Parkinson protocols usually have only a 4–5 mm 2D), where the MPR comes out in steps. In the **Indices** button: **Create 1 mm synthetic T1 of this series (AI, SynthSR)…**. The active frame's series (any contrast, orientation and thickness; preferably a T1 or a FLAIR) goes to SynthSR, which returns an isotropic 1 mm volume with T1 contrast. In a few minutes the study gains the series **Synthetic T1 1 mm · SynthSR**, and the program asks whether to show it in the active frame.

The new series is in the same patient position as the original: it opens in the **MPR**, syncs with the other series, and accepts the guided measurements (**MRPI and MRPI 2.0**, Evans, callosal angle) and the **automatic indices**. It stays only on this computer (it is not sent to the PACS) and carries the AI stamp on the thumbnail.

**It is a synthetic image.** The network only knows normal anatomy: lesions may not appear or may change appearance, and the contrast is calculated, not acquired. Use it to **measure anatomy** (distances, areas, volumes); **never to look for or characterize lesions**, and check the measurements against the original images. With fewer than 20 slices in the source series, or from CT, the result is worse, and the program warns.

In the browser, the tool appears in the **AI** tab as **Synthetic 1 mm T1 (AI, SynthSR)**. Automatic on arrival: **Settings ▸ CAD/AI ▸ Synthetic T1 (SynthSR)…**; in that mode it only runs on brain studies that have no thin series at all (up to 1.5 mm). The model (53 MB) is downloaded once, by instalar_segmentacao or on first use.

## Cervical lymph node levels

**Lymph nodes** button (neck CT; in other studies, through the **Applications** button): **Lymph node level map (AI)**. The active frame's CT series goes to TotalSegmentator, which finds the landmarks; Ipê assembles the map of levels I to VII, right and left, by the staging's imaging rules:

| Level | Rule used |
|---|---|
| IA / IB | above the lower border of the hyoid and in front of the posterior border of the submandibular gland; IA between the anterior bellies of the digastrics |
| IIA / IIB | from the hyoid to the skull base, in front of the posterior border of the sternocleidomastoid and lateral to the carotid; IIB behind the posterior border of the jugular |
| III | from the hyoid to the lower border of the cricoid |
| IV | from the cricoid to the clavicle |
| VA / VB | behind the posterior border of the sternocleidomastoid; VB below the cricoid |
| VI | between the carotids, from the hyoid to the top of the manubrium |
| VII | below the top of the manubrium, between the carotids |
| retropharyngeal | above the hyoid, medial to the carotid |

Each level's label ("IIA R") appears in any plane, in the middle of the piece the slice crosses — on the axial, the reformatted coronal, the sagittal. With the map made, a lesion segmented with the **Segment** tool gets its level by itself (name "Lymph node IIA L" and the rule that decided). The landmarks stay in the SEG **Lymph node levels · TotalSegmentator** (hyoid, cricoid, carotids, jugulars, sternocleidomastoids, submandibular glands), for checking. A landmark that did not appear becomes a warning, and its boundary is not used. Automatic on arrival: **Settings ▸ CAD/AI ▸ Lymph node levels…**.

## Cavum cephalometry

**Cephalometry** button (appears in face, cavum or neck CT; in other studies, through the **Applications** button). Two paths:

> **Result status** (also applies to the skull indices): the window says whether the result is *automatic — not yet checked*, *edited (\*)* or *accepted by so-and-so on date*. Each changed value carries "edited \*" in the Whose column. **Accept the result** records who and when, with what was edited; on reopening the study, the window returns as you left it.

- **Automatic (AI)**: the active frame's CT series (preferably thin axial) goes to TotalSegmentator, which separates the soft and hard palate, naso-, oro- and hypopharynx, hyoid, mandible, tongue and the cervical vertebrae. The calculations are done by Ipê over those structures. It takes a few minutes on CPU, and you can keep working. It uses the same installation as the abdominal segmentation; the first time, it downloads the head and neck models (or run instalar_segmentacao again).
- **By hand (script)**: the same window, empty; choose the row, click **Measure by hand** and make the measurement on a frame (ruler; outline for the area).

| Measurement | How it comes out |
|---|---|
| Minimum cross-sectional area | the airway lumen (below −400 HU) inside the pharynx; area in the plane **perpendicular to the axis** of the airway, where it is smallest, with the location (soft palate third or retrolingual) and the range (> 100 mm² normal; 50–100 moderately reduced; < 50 markedly reduced). A graph shows the area along the axis |
| 1. Soft palate length | midsagittal, from the posterior nasal spine to the tip of the uvula |
| 2. Soft palate thickness | the greatest, perpendicular to the length |
| 3. Posterior airway space | smallest anteroposterior distance of the lumen on the midsagittal: retropalatal (at the level of the soft palate) and retrolingual (below the uvula) |
| 4. Hyoid to mandibular plane | gonion–menton line (Go–Me) drawn on the mandible projected on the sagittal; perpendicular distance to the upper border of the hyoid |
| 5 and 6. Tongue | greatest laterolateral width and anteroposterior length on the midsagittal |
| 7. Hyoid level on the spine | horizontal line through the hyoid body against the bodies of C1–C7 (e.g.: lower plateau of C3) |

The window shows each number with its reference and **whose it is** (automatic or edited). To correct, type in the cell or use **Measure by hand**; **Back to automatic** undoes it. **References…** changes the values in parentheses (they are kept). The text comes out in the report format: the minimum area with the location and the range, and the numbered list with the references.

**Checking in the frame:** each measurement's lines stay in the study as a 3D overlay and appear in any plane that contains them — on the reformatted midsagittal (palate, airway space, Go–Me and hyoid, AP tongue, hyoid level), on the axial at that height (tongue width), on the oblique perpendicular to the axis (minimum area). In the window, **See in the frame** (or a double-click on the row) reformats the active frame in the right plane and goes to the measurement's slice. A measurement changed by hand loses the automatic line. The lines are turned on and off in the CAD/AI button, like the other overlays.

**Automatic on arrival:** in **Settings ▸ CAD/AI ▸ Cavum cephalometry…** (or on the CAD/AI page of Preferences) check *Do automatically when the study arrives*. It applies to CT that arrives over the network or is imported, when the study description contains one of the chosen pieces (by default: CAVUM, RINOFARINGE, NASOFARINGE, ADENOIDE, APNEIA, RONCO, CEFALOMETRIA, VIA AÉREA). The series is chosen by the preference list (by default, the soft-tissue axial), with thickness up to 1.5 mm and at least 40 slices. One study at a time, in the background; what ran appears in Automatic tasks. A study that already has the cephalometry is not redone. When opening the study, the **Cephalometry** button opens the saved numbers directly for checking — without running again. To redo, use Cephalometry ▸ Automatic cephalometry (AI) of this series.

The study keeps two series, only on this computer: **Cephalometry · TotalSegmentator** (the structures, which can be turned on and off like the other segmentations) and **Cephalometry: check · TotalSegmentator**, an image with the midsagittal, each measurement's lines, the list of numbers and the area profile. Look at that image before using the numbers: if a line landed out of place, that number does not count. The distances are measured in the position the patient is on the table; a head that is very flexed or extended changes the "horizontal" of the hyoid level.

# Settings, users and export

All the settings windows **shrink and maximize** (maximize and minimize buttons on the window bar); what does not fit scrolls.

## Spine levels and transitional vertebra

**Identify vertebrae and discs of this series** (in the arrow of the **Genant** button on the bar — or the **Applications** button —, or in the right-click of the series in the database, on a spine CT or MRI) names each vertebra and disc. The names appear in any series and plane of the study.

![Lumbar MRI with the spine levels marked by the segmentation, including the transitional vertebra (lumbarized S1).](rm_coluna_niveis.png)

**Where the numbering comes from** — the final window and the object's list say which one was used:

| Anchor | When |
|---|---|
| counting from C2 | the series includes C2 and no vertebra is missing down to the sacrum |
| by the last rib (T12) | CT without C2: the vertebra of the lowest rib is T12 (assumes 12 pairs) |
| C2 in another series of the study | the series does not include C2, but another one in the study (whole spine, same Frame of Reference) covers from C2 down to it |
| by the AI's names | none of the above: check it |

With C2 and ribs together, the rib checks the count: the last rib at L1 becomes "L1 with rib", and at T11, "T12 without rib" (thoracolumbar transition). If the series covers from C7 to the last rib, the number of pairs appears when it is not 12.

**Lumbosacral transition** — the names follow lumbarized / sacralized:

| On screen | Means |
|---|---|
| **Lumbarized S1**, sacrum as **Sacrum (S2)** | six lumbar-type vertebrae; the disc below is S1-S2 |
| **Sacralized L5** | L5 still separate from the sacrum, with a transition (marked by you) |
| **Sacrum (sacralized L5)** | only four free lumbar vertebrae: L5 is fused to the sacrum; the last disc is L4-L5 |
| **L5 transition?** | five lumbar vertebrae, but with a sign: rudimentary L5-S1 disc (less than half of those above) or Castellvi suggested |

**Castellvi** is suggested by the shape of the last free vertebra: a transverse process 19 mm or more in height (I) or touching the sacral ala (II; if it is bony fusion, change to III). It needs the series to cover ±45 mm from the midline — the MRI sagittal almost never does, and then the window says "not assessable".

**Right-click ▸ Spine numbering**:
- **Adjust the numbering and the transitional vertebra…** — the window opens with the vertebra that was under the click. *This vertebra is…* renumbers everything from it; *Lumbosacral transition* (none, sacralized L5, L5 fused to the sacrum, lumbarized S1) renumbers to stay coherent; *Castellvi* comes with the suggestion and the reason. The **sentence for the report** is redone at each choice (Copy / Send to the report). **Apply** saves it in the study and records who checked.
- **One level down / up** — all the names move one level. If any would fall off the spine (before C1 or after S2), the program refuses and says so.

**The patient's later studies**: the numbering you applied is kept. If the next study of the same patient comes out different (for example, L5 here and lumbarized S1 in the previous one), a warning appears with the date of the previous study.

## The Settings menu

Everything that can be configured lives in the **Settings** menu (and in the Settings button on the home screen), with a submenu per subject: **Viewer** (bar and applications, extra buttons, mouse, shortcuts, window presets, annotations, text over the image, synchronization), **Study protocols** (display protocols, mammography, breast dynamic, dynamics, body regions), **CAD/AI**, **Monitors** (role, layout, order and GSDF calibration), **Network** (DICOM nodes, automation, central server, ipe:// link), **Printing** (DICOM printers and print settings), **Database** (import, database folder), **Users** and **System** (when opening the program, performance, modules, language). Each item opens its own window, with only that subject. The View, Network, Printing and User menus have only actions.

![Settings ▸ Viewer ▸ Bar and applications: in which studies each application appears on the bar.](config_barra.png){75}

**Clicking the group's name** (Viewer, Study protocols, CAD/AI, Reports…) opens a window for that group only, with its steps in a list on the left: the preference pages appear right there and are saved together on OK; those with their own window (Toolbar, DICOM nodes…) show an **Open…** button. Clicking an item in the submenu still opens only that item.

The complete window, with all the tabs, remains at **Settings ▸ All preferences** (Ctrl+,):

| Tab | What it has |
|---|---|
| Mouse | what each button, click and the wheel do |
| Keyboard shortcuts | the more than 80 actions, with search and a header that sorts by group, action or key; by default only Q, ←, →, F1 and F2. And which keys (Shift / Ctrl / Alt) borrow the left button |
| Window presets | named windows by modality |
| Monitors | role, order, identification and the series strip |
| Performance | image cache, MPR volume ceiling, 3D detail and magnifier size |
| Display protocols | the protocols with steps for non-mammography studies (layout, series, planes, MIP, window, color) |
| Dynamics | the rules for joining and splitting series |
| Mammography | the protocols with steps (chapter 5) |
| General | when opening the program, text and marks over the image, buttons on the viewer bar, import and language |
| Modules | turn Nuclear medicine, Mammography, 3D, Advanced MRI/CT and Received printing on and off |

**Modules**: turn off what you do not use and the buttons and services of that module disappear. **No study is deleted**: the study stays in the database and opens as an ordinary image; turning it back on returns everything. Nuclear medicine takes the NM buttons and the PET/CT fusion; Mammography, the protocols on opening (the study opens without hanging) and the density; 3D, the 3D button (the MPR stays); Advanced MRI/CT, the dynamic button; Received printing, the print servers (the ports stop receiving), the list and the print settings, the ultrasound automatic film and the cleanup — the composer and the film panel stay. Only those with the permission to configure change the modules.

In Settings ▸ Viewer ▸ *Extra buttons on the bar*: four buttons (Invert, Rotate and mirror, Cine, Hide patient data) leave the bar by default and live in the **More** menu; unchecking and checking there moves them between the two places. The function never disappears: it only changes place.

## Mode of use

The first time the program opens, it asks how it will be used. You can change it later in **Settings ▸ Users ▸ Mode of use**.

| Mode | How it works |
|---|---|
| **Only I use this computer** | opens directly, without asking for username and password. With users already registered, it enters as the chosen one ("Sign in as") or, if there is only one, as that one |
| **Several people use this computer** | each one signs in with their own user. The first time, you create the administrator right there |
| **This computer is the group's server** | keeps the studies, users and settings and serves the other computers (port chosen there; certificate in Network ▸ Central server) |
| **Connect to a group server** | uses the server's database and users; **Test** checks the address. Entering or leaving this mode asks to reopen the program |

**Signing in with the system account.** In the several-people and server modes, the box *Sign in with the system account without typing a password* lets whoever opened the program with the Windows/Linux account linked to a user sign in directly as that user. Each person's account is in the user's record (**System account**, with the button *Use this computer's*); an empty account always asks for the password, and a deactivated user does not sign in. Each sign-in like this stays in the access log.

### Visible to: the service's, personal or shared

With several people (or a server), the registers of **DICOM nodes**, **identities**, **print servers**, **print rules** and **automatic film rules** have the **Visible to** field:

| Choice | Who sees it |
|---|---|
| **Everyone (the service's)** | everybody. Only those with the permission to configure create or change |
| **Only me** | only you |
| **Me and chosen users…** | you and whoever you check |

- A new item from the administrator is born **the service's**; the others' is born **personal**.
- In everyday choices (which node to search, where to send) each person sees the service's, their own and what was shared with them.
- The **administrator** also sees and edits, on the settings screen, what is personal to others (*Visible to* column: "so-and-so's") — but that does not enter their choices.
- Those who do **not** have the permission to configure open **Settings ▸ Network ▸ DICOM nodes** as **My DICOM nodes**: only nodes and identities, and only their own can be edited.
- What works for the computer — the receiving DICOM node, automation, print rules — uses all the items, whoever they belong to.
- In **Only I** mode the field does not appear.

### Personal and shared database

With several people (or a server), the **Locations** panel gains the **Database** group: *Everything I see*, *My database*, *Shared* and *Shared with me*. The administrator also sees **So-and-so's database (n)** for each person who has personal studies.

- The study exists **only once** in the computer's database: "personal" is a mark. Moving between databases does not copy images. Reports, measurements and annotations go with the study.
- **Right-click on the study ▸ Organize ▸ Database**: *Move to my database (personal)*, *Move to shared*, *Share with…* (choose users) and, for the administrator, *Pass to the database of…*. Taking a study out of the shared database hides it from the others, so only those who configure the computer do it — to gather cases, use the lists.
- **Where new studies go**: what arrives over the network at the AE of a **personal identity** ("Dr. So-and-so's AE", with *Visible to: Only me*) goes to the owner's database; what arrives at the service's AE goes to the shared one. What **you** import or download from the PACS follows your choice in **Locations ▸ right-click on a database ▸ Studies I import or download go to** (by default, the shared one).
- **The administrator** opens anyone's personal database; opening that database and each study in it stays in the **access log**. When someone leaves the service: right-click on *So-and-so's database ▸ Pass so-and-so's database to* another user or the shared one.
- **Attention**: on the same computer, "personal" hides the study **inside the program**, but the files remain in the database folder — whoever opens the folder through the system sees the images. Real confidentiality only in server mode.
- The **Database** column of the list (Columns ▾) shows which database each study belongs to.

### Personal database on the server or on this computer

In **client mode** the **Locations** panel shows the **Central server** (where the window opens) and the **Database of this computer**. One click switches: this computer's database opens **without the server** — with no internet, intranet or VPN — and works as a case database.

- **Right-click on the study ▸ Database**, looking at the server: *Copy to this computer* (stays in both) and *Move to this computer* (leaves the server — only the owner or the administrator; a locked study stays copied). Looking at this computer: *Send to the central server…*, to your personal database or the shared one.
- **Reports, measurements, annotations, key images, comments, tags and the diagnosis go along**, without deleting what already exists on the other side. Left out are the followed lesions (they belong to the patient) and the films. **The case lists go along** (since 0.99.36): the study enters, on the other side, the same list and the same folder (created if they do not exist, with the same *Visible to* when the person carrying it can), with friendly name, history, answer and notes; bringing it again duplicates nothing. Smart lists do not travel: the filter runs by itself on the other side.
- **Studies I import or download go to** gains, in client mode, *my database on this computer*: what you import goes straight here and **does not go up** to the server. *My database on the server* goes up already marked as yours. Since 0.99.36 it also applies to what **you download from the PACS**: the new study stays in this computer's database and does not go up; if it is open in a tab, it changes place when the tab closes.
- **Taking a whole database to the server** (the computer that became a client): right-click on the location (this computer, an external HD…) **▸ Send this database to the central server…**. The administrator can send *as they are*: each study in the owner's database. Nothing is deleted from here.
- **The server checks everything**: a study in someone else's personal database does not appear in the search (nor through DICOMweb) and is not delivered to whoever asks; taking it out of the shared one asks for the permission to configure; putting it in someone else's database, only the administrator.
- **Changing the mode of use** neither deletes nor copies studies: the program warns what changes (for example, from "several people" to "only I", the personal studies start to appear for whoever uses the computer — and become personal again if you go back).

### Personal, shared and service settings

With several people, the **configuration lists** also have three levels — **the service's** (everyone), **shared with chosen users** and **personal**: display protocols, mammography protocols, breast dynamic layouts, print sheet templates, report templates and the **case lists** (including smart ones).

- In the usual windows nothing changes: each person sees the service's, their own and those shared with them. A **new** item is born the service's when the administrator creates it and personal for the others.
- **Changing a service item** without the permission to configure creates a **personal copy** with the same name, which takes the place of the service's **only for you** — the others keep the original. With the permission, it changes the service's. Deleting the service's also asks for the permission.
- **Settings ▸ Users ▸ Personal and shared settings…** shows, in a tab per subject, who sees each item, with the buttons *Everyone (the service's)*, *Only me*, *Me and chosen users…*, *Copy to me* and, for the administrator, *Pass to*. The administrator sees everyone's.
- **Case lists**: right-click on the list ▸ **Visible to**. On a folder, it applies to everything inside. The personal list appears in italics.
- The **Preferences** tab deals with what was already each person's (shortcuts, mouse, window presets, columns): *Back to this computer's default* or, for those who configure, *Make mine the default of this computer*.
- Those who already had their own protocols in the preferences: on the first sign-in they become your personal items.
- In client mode all of this lives on the server, which checks the rules; in "only I" nothing changes.
- **Automation rules** (0.99.36): scheduled searches, priors, routing, ready dynamic and automatic management also have **Visible to** in each rule's editor, and the column in the list. Each person sees the service's, their own and those shared with them; the administrator sees all. **All of them run** — automation works for the computer, whoever the rule belongs to. What a scheduled search downloads goes to the **shared** database; in a personal search, the box *New studies downloaded by this search go to the owner's personal database* sends them to the database of whoever owns the rule. The **prior** downloaded because of a study (pre-search or through the priors strip) goes to the **same database** as the current study. In the window *Personal and shared settings*, the **Automation rules** tab changes who sees it and does *Copy to me* (the copy is born paused, so it does not run twice). Automation is per computer: in client mode the rules stay on the computer, not on the server.
- **References** of the cephalometry and the skull indices (the text in parentheses in the report): in the **References…** button, *Applies to*: **Only me** (yours, on top of the computer's) or **Everyone on this computer** (asks for the permission to configure). The *Preferences* tab of the personal settings window also returns them to the default.
- **External call** (RIS, `ipe://` link, API): opens only what the signed-in person could open through the list. A study from another user's personal database does not open and is not even searched again in the PACS (the status bar says why); the administrator opens it, and it stays in the access log.
- What does not have three levels, on purpose: the export options are already each user's (with the computer's default underneath); smart lists are case lists and already have *Visible to*.

## Users and permissions

**Users** button. Four default profiles — Administrator, Physician, Resident and Technologist — and each profile's permission table is editable by the administrator.

| Permission | What it allows |
|---|---|
| Open and view studies | the basics |
| Import files | import |
| Search the PACS / Download from the PACS | query and download (and DICOM Management) |
| Send to DICOM nodes | send studies out |
| Export | CD, USB drive, images |
| Export with patient data | without it, every export comes out anonymized |
| Delete studies | deletion |
| Case lists and meeting mode | the case database |
| Films and printing | composer, DICOM printer and the film panel |
| Write reports / Sign reports | draft and release, separate |
| Configure network, automation and preferences | the settings windows |
| Manage users and see the access log | administration |

**I forgot the username or password (0.100.113).** In the login window, click *I forgot the username or password…*:

- In a **single-use** Ipê ("Only I use this computer"), the list of users appears: choose yours and save a new password. Whoever opened Ipê is already in the Windows account that owns the database, so the password protects nothing beyond that. The change stays in the access log.
- With **several people** or on the **server**, an administrator resets it in **Users**. If nobody remembers the administrator password, open a command window in the Ipê folder and run `ipe-cli redefinir-senha` (lists the users) and `ipe-cli redefinir-senha <user>` (asks for the new password twice).
- On the **client**, the password belongs to the central server: its administrator resets it.

To start from scratch on a computer without studies, close Ipê and delete the folder `%LOCALAPPDATA%\DicomViewer` (settings, database and studies). The next time it opens, Ipê asks for the mode of use again.

## Export

**File ▸ Export…** (or the **Export** button) exports the open study or those selected in the database:

![Export: DICOM (with DICOMDIR and browser viewer) or images, with anonymization of the copies.](exportar.png){65}

- **DICOM** — folder, CD or USB drive, with DICOMDIR and, if you want, a viewer that opens in the browser (complete, with measurements, values, ROIs and MPR; or light). It can come out compressed as .zip.
- **Images** — JPG or PNG, with format, quality, window (the file's or the current frame's), range and maximum size.

**Choosing the series**: check the box below *What to export* and the list of each study with its series appears; uncheck those that should not go out (for example the scout, dose series or segmentations). It applies to DICOM, images and the anonymized copy; a study with no series checked is left out.

**AI findings go along (0.100.86)**: in DICOM export (folder, .zip or anonymized copy in the database) the studies' AI findings — the emphysema %LAA, the L3 composition, the nodules, with the state of each (suggested, confirmed, corrected, discarded) — come out in an `IPE_ACHADOS.json` file at the root. When that folder is imported into another Ipê, they return to the database, tied to the study and the series (by the new UIDs, when the export generates new UIDs). Anonymized, the reviewer's name and the free note do not go out. Only the findings of the series that went out are included.

Anonymization is an option in the window — and mandatory for those who do not have the permission to export with patient data.

**Different patients in a single package**: exporting identified, on a CD/USB drive with viewer or in a .zip, studies of different patients asks first, showing where name and ID do not match — it is the package delivered to a patient with another patient's study inside. A loose folder, JPG/PNG images and anonymized copies do not ask (gathering cases for teaching or research is normal use).

**Derived series say where they came from**: every series that Ipê writes from another (reconstruction, MIP, dynamic map, capture) carries in *Derivation Description* the program version and the parameters (plane, thickness and mode, step, pixel, orientation and source series; in the map, the phases and thresholds) and in *Source Image Sequence* the source images (up to 300 per image, evenly spaced when there are more — the description says how many out of how many).

### Anonymize

Right-click on a study — or on several — and **Tools ▸ Anonymize a copy of this study…**. The window opens already checked to anonymize, and there are three destinations: DICOM, Images, or **Anonymized copy in my database** — it becomes another study in the list, and nothing leaves the machine.

| Choice | What happens |
|---|---|
| Name and ID | free text; `{n}` becomes the number (ANON001, ANON002…). In the copy in the database the numbering continues from where it stopped, so two copies do not become the same patient |
| Keep sex / age | the birth date always goes; age and sex are optional |
| Keep study dates | without it, the dates come out blank |
| Keep descriptions | study and series description (in some services they contain names) |
| Keep institution | name and department |
| Remove private tags | everything the manufacturer added outside the standard |
| Generate new UIDs | mandatory (and locked) in the copy in the database: with the same UIDs it would land inside the original |
| Text burned into the image | black bar: automatic (ultrasound and marked images), top strip, or do not touch the pixels |

> **Anonymizing is copying.** The original's files are not touched. The copy in the database appears with the source *Anonymized* and the automatic cleanup does not delete it — it exists only here. It is worth checking the images: in ultrasound the name sometimes stays inside the image area.

## The tables

In every table of the program the divider between columns can be dragged, and clicking the header sorts where that makes sense.

## Known limitations

- Exported JPG/PNG does not erase text burned into the image nor apply rotation.
- Registration between studies is rigid (rotation and translation), not deformable.
- The 3D runs on the CPU.
- A database location in a network folder (Windows share, NAS) is not recommended: PostgreSQL wants the data on a disk of this computer. To split the database, use the central server.
- In mammography, the priors come only from the local database.
- Streaming is not on demand: the rest of the study comes in the order the PACS sends it.
- DICOM Management is by button (it is not scheduled) and does not check DICOMweb nodes.
- The background enhancement of breast MRI does not yet separate fibroglandular tissue from fat.
- The lesion capture uses the 2nd phase as the anatomical image (not the subtraction nor the color map).
- The installer is Windows only and is not yet digitally signed; there is no automatic update.
- The density has been validated in 17 breasts from a single service.

# Recipes

Complete paths, from start to finish.

## Getting mammography ready on two monitors

1. Settings ▸ Monitors ▸ Role, layout and order: check two screens as **Viewer** and set **Order** 1 and 2. Check with **Identify monitors**.
2. Settings ▸ Study protocols ▸ Mammography ▸ **+ New**. Name "Screening", Study description contains: empty, **Active** checked.
3. **+ Step** "CC": layout 1 × 2, *As text:* `CCD x CCE`.
4. **+ Step** "MLO": layout 1 × 2, `MLOD x MLOE`.
5. **+ Step** "Current × prior": layout 2 × 2, `CCD, CCD ant x CCE, CCE ant`.
6. Open a mammogram and move with **→** and **←**; **Q** goes through the quadrants.

## Checking at the end of the day that the studies reached the PACS

1. Once: register the modalities as nodes and, if needed, the identity with the AE they accept (chapter 10).
2. **Management** ▸ check the modalities ▸ choose the PACS ▸ **Test the selected node** the first time.
3. Period **Today** ▸ **Check**. Show: **Only those with a problem**.
4. Select the incomplete and missing ones ▸ **Send what is missing to the PACS**. The program checks again after sending.
5. **Export CSV…** if you want to keep the day's record.

## Sending only some series as another device

1. In the database, select the study and, in the series panel, the series (Ctrl+click).
2. Right-click ▸ **Send N series to** ▸ the node ▸ *as* the identity (OsiriX, for example).
3. Follow it in the transfer queue. For a study that is still only in the PACS, the same menu exists in the search results: it downloads and sends by itself.

## Making the RIS open the study in the viewer only

1. On the workstation, run `ipe-cli register-url` once (or Network ▸ Register the ipe:// link).
2. In Network, check the port and copy the token if you will use the API.
3. Register the PACS as a node, check *use in search* and choose C-GET.
4. In the RIS, build the link: `ipe://open?accession={ACC}&janela=viewer`.
5. Test with an accession that is not in the database: the study should open while downloading.

## Connecting to an Orthanc by DICOMweb

1. Ask for the DICOMweb base (something like `http://server:8042/dicom-web`) and a read-only user.
2. Settings ▸ Network ▸ DICOM nodes ▸ **+ New**. In **Connection type**, choose DICOMweb (HTTP).
3. Fill in Name, DICOMweb address, User and Password. HTTPS with a self-signed certificate: check *Accept unverified certificate*.
4. Check in *Use in* what makes sense and press **Test network**.
5. Open the PACS and search. The download returns over the same connection: nothing needs to be registered on the server side.

## Measuring a lesion on breast MRI and saving the capture

1. Open the study and the **Dynamic** button; check the pre, the peak and the late phase.
2. Look at the **Kinetic** map; draw an ROI on the lesion to see the curve.
3. **Segment 3D** and click on the lesion. Adjust the **Threshold** bar until the region covers the lesion.
4. **Mark the nipple** and click on the nipple: the distance comes out at once, and applies to the other lesions of the same breast.
5. Give it a name and **Save as measurement**; then **Save capture (SC)…**.
6. In the report, **Insert ▾** brings the measurements and curves into the text.

## Assembling, printing and keeping a film

1. In the study, **F1** on each image you want in the film, or **F2** for a series (whole or a range).
2. Choose the sheet grid. To swap two images, drag by the ⠿ handle.
3. Adjust each image with the left button (Mouse: Window, Move or Zoom, in the cell's right-click menu).
4. Annotate with an arrow or text; the mouse goes back by itself to the previous function.
5. Check **also in the study** and **Save**; then **DICOM Print…** or **Print…**.
6. The **Film and print panel** shows what was printed and in how long.

## Setting up a case session

1. **+ List**, session name, type **Meeting**.
2. Drag studies from the database into the list (or right-click → add to list).
3. Double-click on the list opens the organizer: give each case a friendly name, the history, the answer, notes and tags.
4. **▶ Meeting mode**. Present with Alt+→; Alt+H shows the history and Alt+R reveals the answer.

## Splitting the triphasic CT that comes in a single series

1. Open the study, right-click on the series → **split**.
2. The phases appear as their own thumbnails in the strip. Nothing was written to the database.
3. In Settings ▸ Study protocols ▸ Dynamics, the rule was born as pending: confirm it for it to apply to all identical studies, or leave it on Ignore.

# Appendix: the shortcuts

The shortcut list comes almost empty. Only five keys are default; all the other actions are born without a key, for you to choose yours in Settings ▸ Viewer ▸ Keyboard shortcuts. Nothing stops working without a key: every action is in a menu or on the bar. A repeated shortcut is refused with a warning.

## Default

| Key | What it does |
|---|---|
| Q | Mammography: breast quadrant zoom — each Q goes to the next, in a cycle |
| → | Mammography: next protocol step |
| ← | Mammography: previous step |
| F1 | in the study: the frame's image goes to the film |
| F2 | in the study: the frame's series goes to the film (whole or a range) |

## Fixed (not configurable)

### Program

| Key | What it does |
|---|---|
| Ctrl+I | Import folder |
| Ctrl+P | Film / printing |
| Ctrl+Shift+P | Prints |
| Ctrl+Shift+F | PACS query |
| Ctrl+B | Back to the database |
| Ctrl+, | All preferences (full window) |
| F1 | User guide (outside the study; in the study it belongs to the film) |
| Ctrl+Q | Quit |

### Meeting mode

| Key | What it does |
|---|---|
| Alt+→ / Alt+← | next / previous case |
| Alt+H | History |
| Alt+R | Reveal answer |
| F11 | Full screen |

### On the frame, always

| Key | What it does |
|---|---|
| ↑ ↓ | scroll the slices |
| PgUp PgDn | scroll 10 slices |
| Home / End | first / last image |
| 1–9 | window presets |
| 0 | the file's window |
| Del | deletes the selected measurement |
| Esc | cancels what is being drawn |
| Alt + wheel or Alt + ↑↓ | fine adjustment of a linked frame |

### In the film

| Key | What it does |
|---|---|
| Ctrl+C / Ctrl+X / Ctrl+V | copy, cut, paste cells |
| Ctrl+A | select all on the sheet |
| Ctrl+Z | undo the last annotation |
| Del | delete the selected cells |
| ↑ ↓ ← → | move the cell's slice |

## Suggestions, by group

It was the default until version 0.64 — it is here for those who want to repeat the same map, or part of it. The action names are those that appear in the preferences window.

### Tools and measurements

| Suggested key | What it does |
|---|---|
| W / Z / P / S | Window / Zoom / Pan / Scroll slices |
| M | Ruler |
| X | 3D cursor |
| A / Shift+C | Angle / Cobb |
| E / Shift+E / G | Elliptical / rectangular / polygonal ROI |
| Shift+G | Polyline |
| Shift+A / T / B | Arrow / Text / Pencil |
| V | Intensity (pixel value) |
| Shift+V | Segment 3D |
| , and . | previous / next image with a measurement |

### Image

| Suggested key | What it does |
|---|---|
| I | Invert tones |
| F | Fit to window |
| R | Restore view |
| C | Cine |
| H | Image histogram (or the ROI's) |
| Alt+R / Alt+Shift+R | Rotate 90° right / left |
| Alt+H / Alt+V | Mirror left ↔ right / top ↕ bottom |
| U | Magnifier |
| Shift+Q | Zoom by quadrant: previous |
| Shift+H | Hide patient data |
| Shift+I | Show/hide CAD/AI |

### Series, MPR and dynamic

| Suggested key | What it does |
|---|---|
| [ and ] | previous / next series in the frame |
| K / Shift+K | mark key image / show the marked ones |
| Shift+P | Add prior study |
| Shift+M | MPR on/off |
| O | Oblique MPR (draw a line) |
| Alt+1 / Alt+2 / Alt+3 | reconstruct the active frame: axial / coronal / sagittal |
| Shift+D | Dynamic assessment |

### Synchronization

| Suggested key | What it does |
|---|---|
| Shift+S | Automatic synchronization (same study) |
| L / Shift+L / Ctrl+L | link frames / switch mode / change group |
| Shift+W / Shift+Z | sync window / zoom and pan |
| Shift+R | Reference lines |
| Shift+Y | Series strip |

### Mammography, report and film

| Suggested key | What it does |
|---|---|
| Shift+T | Jump between 2D and tomosynthesis |
| Shift+B | Contrast-enhanced: low energy ⇄ recombined |
| Shift+J | Tomosynthesis: next thickness (slab) |
| Alt+I | Implant (correct the prosthesis) |
| Alt+Q | Frame the breast in the frame |
| Ctrl+R | Study report |
| Ctrl+Alt+F | Send all frames to the film |
| Ctrl+Shift+L | Lesion follow-up |

## External call responses

| Response | Means |
|---|---|
| aberto | the study was in the database and was opened |
| buscando | it was not; the search on the nodes was triggered |
| ja_no_banco | retrieve request for a study that is already here |
| nao_encontrado | neither in the database nor on the nodes (or there is no node configured) |
| importando | the call brought file paths |
| erro | it failed; the reason is in the log |
| recusado | ipe:// link without the token, refused (or you answered "no" to the question) |

## Network security

- **`ipe://` link**: any page open in the browser can build a link like this. With the API token in the link (`…&token=<token>`), it opens directly; without the token, **Network ▸ External call ▸ ipe:// link without the token** applies: *Ask before opening* (default), *Accept* or *Refuse*. Put the token in the RIS link so it does not ask.
- **DICOM node**: the AE Title is just a name that the device claims to have — any computer on the network can imitate it. In **Accept connections from**, *Only registered nodes, checking the node's IP* accepts only the connection that comes from the address registered on the node with that AE.
- **DICOM printer**: a new printer accepts *any AE on the local network* (10.x, 172.16–31.x, 192.168.x and VPN 100.64.x) — no modality comes from outside the internal network. The printers you already had stay as they were; change in Settings ▸ Printing ▸ Servers.
- **Central server**: without a certificate it uses HTTP, and username and password travel over the network unencrypted — use it only on a trusted internal network, or provide a certificate (.pem). Five wrong passwords in 10 minutes block that computer for 10 minutes.

> **One last word.** Every new function of this program has a manual fallback mode, warns when it could not do it and shows the state on the screen. When a number does not come out, the answer is "it did not work" — never a big number. The program returns a number; the interpretation is the physician's.

# About Ipê

## Why Ipê

In Brasília, in the middle of the dry season, when the city turns brown and the air turns dry, the ipê trees bloom. Yellow, purple, white — and suddenly the landscape changes. I like the idea of a program with that name: something that is born in the middle of the arid work of everyday life and makes the routine lighter.

And there is a coincidence I only noticed later: *ipê* is in my name. Fil**ipe**.

## How it was born

I am a radiologist, dedicated to breast imaging, and a technology enthusiast. Like many radiologists, I moved to macOS because of OsiriX and Horos, which for years were the best workstation within reach of those who report. But I always wanted a complete and robust program that also ran on Windows and Linux, the systems of most of the services where we work.

For a long time, this wish stayed in ideas: I knew what I wanted on the screen, but I had no way to turn it into a program on my own. Artificial intelligence changed that. Today I describe a need from practice — "in breast MRI, I want the kinetic map"; "in an empty frame, let me choose the series" — and **Claude**, from Anthropic, works like a senior programmer: it writes the code, tests it and explains what it did. The clinical decisions, what goes in and how it should work remain mine, as does the checking on real studies.

## On the shoulders of giants

Ipê only exists because many people shared their work as open source: the interface libraries (Qt/PySide6), DICOM (pydicom, pynetdicom, GDCM, pylibjpeg), computation (NumPy) and artificial intelligence, such as **TotalSegmentator**, besides many others listed in *Credits and licenses*. That is why Ipê is also open (GPL-3.0): so that others can use, study, improve and give back.

## What it is not

Ipê is a research and teaching tool. It **is not a registered medical device** and is not intended for diagnostic use.

— Filipe Ramos Barra

## Credits and licenses

The complete list of what Ipê uses — libraries, AI models and tools —, with the license and link of each one, is in **Help ▸ About Ipê ▸ Credits and licenses** and in the CREDITOS.md file of the repository. The authors of TotalSegmentator and nnU-Net ask that works using these tools cite their papers; the citations are in the same list.

