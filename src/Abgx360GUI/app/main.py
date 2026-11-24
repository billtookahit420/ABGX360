"""abgx360 GUI -- a batch front-end for abgx360 (Seacrest), using
the v1.0.7 [Hadzz Fork] CLI.

A GUI wrapper for people who hate the command line: add ISOs (or a
whole folder, or a burned DVD), pick from the same options the
original abgx360 GUI v1.0.2 offered -- all of them, organised the
same way -- and run the queue. Each item gets a parsed per-check
results view plus the full raw log, a live command-line preview
shows exactly what will run, and a status bar narrates every phase.

First run downloads and builds the abgx360 engine into a per-user
folder (Recomp Tools style); later runs reuse it.

abgx360 -- https://github.com/hadzz/abgx360 / http://abgx360.hadzz.com
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import abgx_engine as engine  # noqa: E402
import archive_input  # noqa: E402
import netshare  # noqa: E402

from PySide6.QtCore import Qt, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence  # noqa: E402
from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton,
    QRadioButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)


class Worker(QThread):
    """Runs one engine callable in the background. Workers are held
    in a set on the window until they finish (letting a reference be
    overwritten mid-run is designed out, as in the sibling apps)."""
    log = Signal(str)
    done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn(lambda s: self.log.emit(str(s)))
        except Exception as e:  # noqa: BLE001
            self.done.emit({"error": "%s: %s" % (type(e).__name__, e)})
            return
        self.done.emit(result)


QUICKSTART = {
    "Welcome!":
        "Welcome to abgx360 GUI, the ultimate tool for Xbox 360 ISOs "
        "and Stealth files!\n\nPick an item from the dropdown list "
        "above to get detailed information or instructions displayed "
        "here.",
    "How to change the default settings or create preset settings":
        "Every option in this app is saved into named presets from "
        "the File menu: Save Settings (Ctrl+S), Load Settings "
        "(Ctrl+L), Delete Settings (Ctrl+D). Saving a preset named "
        "\"Default\" makes it load automatically every time the app "
        "starts, so set the options the way you like them, save them "
        "as Default, and they become your defaults.",
    "How to check/fix an Xbox 360 ISO or create a .dvd file":
        "Add an ISO with Add Single ISO (or a whole folder with Add "
        "Folder), leave the options at their defaults for a standard "
        "check, and press Run Queue. abgx360 checks the .dvd file, "
        "stealth data (Video, PFI, DMI, SS), region, and -- when "
        "stealth passes -- verifies the game data against the online "
        "database, AutoFixing problems at the threshold you chose on "
        "the AutoFix tab. A missing or wrong .dvd file is created/"
        "fixed automatically when Check/Create .dvd file is on.",
    "How to check ISOs on a network share":
        "If your ISOs live on a home server, use the Network "
        "Share... button above the queue: enter the server (e.g. "
        "192.168.0.102) and the share name, then pick ISO files "
        "or a whole folder from it. If the share asks for a "
        "login, fill in the User / Password / Domain fields -- "
        "the username is remembered, the password is not. "
        "Recent shares are remembered. "
        "On Linux the share is mounted through GVFS (the "
        "gvfs-backends package) so abgx360 reads it like a local "
        "folder; the other file dialogs then open on the share "
        "too. On Windows you can also type a UNC path "
        "(\\\\SERVER\\share) directly into any file dialog.",
    "How to check an ISO inside a zip or 7z file":
        "Add Single ISO also accepts .zip and .7z archives. "
        "The disc image inside is extracted to local scratch "
        "(the extracted folder in the app's data folder) and "
        "checked from there; the queue row keeps showing the "
        "archive you picked, and the archive itself is never "
        "modified -- extraction never happens on a network "
        "share. If an archive holds several disc images, the "
        "largest is extracted. Extracted ISOs are reused when "
        "you re-add the same archive; delete the extracted "
        "folder's contents to reclaim the space.",
    "Angle Deviation and You":
        "SS replay angles are measured against their CCRT targets. "
        "Deviation is always checked whether or not fixing is "
        "enabled: a warning appears if any angle deviates more than "
        "3 degrees (yellow -- stealth is uncertain) or 9 degrees "
        "(red -- stealth failed). The AutoFix tab option adjusts "
        "angles that deviate more than X degrees (default 3) back to "
        "their targets. It applies to SS v1 only; SS v2 is "
        "unaffected.",
    "To SplitVid or not to SplitVid":
        "SplitVid puts a copy of the L1 video data on L1, which is "
        "how original discs are laid out and what newer firmwares "
        "expect. Adding SplitVid makes an ISO bigger (a full "
        "DVD+R DL) but is the layout originals use. The Misc tab "
        "lets you Add it, Remove it, or Leave it the way it is "
        "(the default).",
    "What is AnyDVD style corruption?":
        "AnyDVD and similar tools remove DVD copy protection on the "
        "fly, and in doing so they insert video files into the game "
        "data area of rips made through them. That data is not part "
        "of the game and makes the game CRC wrong. The Options tab "
        "check searches game data sectors for those inserted files. "
        "The check runs automatically whenever the game CRC is "
        "checked; the option exists to force a game CRC check.",
    "Is there such a thing as a \"bad kreon rip\"?":
        "No. Kreon drives read the SS at a fixed set of angles, and "
        "the so-called \"bad kreon rip\" was a misunderstanding of "
        "angle deviation: a rip is not bad merely because its SS "
        "angles deviate -- what matters is how far they deviate "
        "from the CCRT targets (see Angle Deviation and You).",
    "What is SS v2?":
        "SS v2 is a security sector with multiple challenge/response "
        "entries measured at several angles, used by newer games. "
        "\"Trust SS v2 angles\" (AutoFix tab) trusts those "
        "measurements instead of re-checking them against the "
        "database; turning it off (--notrust) is the cautious "
        "choice for discs ripped with unknown drives.",
    "Where are my StealthFiles and Images stored?":
        "abgx360 keeps its data in a hidden folder in your home "
        "directory: ~/.abgx360 -- StealthFiles in ~/.abgx360/"
        "StealthFiles and extracted Xex images in ~/.abgx360/"
        "Images. Help > Where is my StealthFiles folder... "
        "(Ctrl+F) and Help > Where is my Images folder... (Ctrl+I) "
        "open them for you.",
}

AUTOFIX_LABELS = [
    "Level 3 - AutoFix if stealth passes but fails verification",
    "Level 2 - AutoFix if stealth is uncertain and fails verification",
    "Level 1 - AutoFix if stealth fails",
    "Level 0 - Do not AutoFix",
]
REGIONS = [
    "NTSC/U", "PAL (Australia or New Zealand)", "PAL (Europe)",
    "NTSC/J (Japan)", "NTSC/J (China)", "NTSC/J (Other)",
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("abgx360 GUI")
        self.resize(1060, 860)
        self._workers = set()
        self.items = []            # queue item dicts
        self._running = False
        self._stop = False
        self._handle = None
        self._setup_done = False
        self._last_net_root = ""
        self._net_error = None
        self._setup_error = None
        self._setup_stopped = False
        self._dep_offer_rounds = 0
        self._dep_offers = []
        self._ui_queue = []
        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._drain_ui_queue)
        self._ui_timer.start(100)
        self.history = engine.load_history()
        self._build_ui()
        self._load_initial_settings()
        self._refresh_interlocks()
        self._update_preview()
        self._start_setup()

    # ----------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- queue panel ---
        qbox = QGroupBox("Input Queue")
        qlay = QVBoxLayout(qbox)
        btns = QHBoxLayout()
        self.btn_add_file = QPushButton("Add Single ISO...")
        self.btn_add_folder = QPushButton("Add Folder...")
        self.btn_add_net = QPushButton("Network Share...")
        self.btn_add_dvd = QPushButton("Add Burned DVD...")
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_clear = QPushButton("Clear Queue")
        for b in (self.btn_add_file, self.btn_add_folder,
                  self.btn_add_net, self.btn_add_dvd,
                  self.btn_remove, self.btn_clear):
            btns.addWidget(b)
        btns.addStretch(1)
        self.btn_run = QPushButton("Run Queue")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        btns.addWidget(self.btn_run)
        btns.addWidget(self.btn_stop)
        qlay.addLayout(btns)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Item", "Type", "Status", "Result", "Path / Device"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        qlay.addWidget(self.table)
        root.addWidget(qbox)

        # --- program output / run panel ---
        obox = QGroupBox("Program Output")
        olay = QHBoxLayout(obox)
        self.w_output_mode = QComboBox()
        self.w_output_mode.addItems(
            ["CLI Window", "HTML File", "Text File"])
        olay.addWidget(QLabel("Output:"))
        olay.addWidget(self.w_output_mode)
        self.w_output_file = QLineEdit()
        self.w_output_file.setPlaceholderText(
            "Output file (HTML/Text modes)")
        self.btn_output_file = QPushButton("Save to...")
        olay.addWidget(self.w_output_file, 1)
        olay.addWidget(self.btn_output_file)
        self.w_open_done = QCheckBox("Open file when done")
        self.w_maximize = QCheckBox("Maximize it")
        self.w_terminal = QCheckBox("Use Terminal font characters")
        self.w_write_disable = QCheckBox("Disable Writes")
        for w in (self.w_open_done, self.w_maximize, self.w_terminal,
                  self.w_write_disable):
            olay.addWidget(w)
        root.addWidget(obox)

        # --- option tabs + results ---
        split = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_options(), "Options")
        self.tabs.addTab(self._tab_patch(), "Manually Patch or Extract")
        self.tabs.addTab(self._tab_autofix(), "AutoFix")
        self.tabs.addTab(self._tab_rebuild(), "Rebuilding")
        self.tabs.addTab(self._tab_misc(), "Misc")
        self.tabs.addTab(self._tab_quickstart(), "Quickstart")
        split.addWidget(self.tabs)

        rbox = QWidget()
        rlay = QVBoxLayout(rbox)
        rlay.setContentsMargins(0, 4, 0, 0)
        self.results = QTableWidget(0, 3)
        self.results.setHorizontalHeaderLabels(
            ["Check", "Result", "Detail"])
        self.results.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.results.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        rlay.addWidget(self.results)
        self.raw_log = QPlainTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setPlaceholderText(
            "Raw abgx360 output for the selected item appears here.")
        rlay.addWidget(self.raw_log)
        split.addWidget(rbox)
        split.setSizes([430, 300])
        root.addWidget(split, 1)

        # --- live command preview (the original's status field) ---
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Command:"))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        prow.addWidget(self.preview, 1)
        root.addLayout(prow)

        # --- status bar: stage line + progress ---
        self.stage_label = QLabel("Starting...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(220)
        status_bar = self.statusBar()
        status_bar.addWidget(self.stage_label, 1)
        status_bar.addPermanentWidget(self.progress_bar)

        self._build_menus()
        self._wire()

    def _chk(self, label, parent_layout, checked=False, tip=None):
        c = QCheckBox(label)
        c.setChecked(checked)
        if tip:
            c.setToolTip(tip)
        parent_layout.addWidget(c)
        return c

    def _tab_options(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.w_dvd_file = self._chk(
            "Check/Create .dvd file", lay, True)
        self.w_stealth = self._chk("Check Stealth", lay, True)
        self.w_verify = self._chk(
            "Verify if Stealth passes", lay, True)
        self.w_padding = self._chk(
            "Check/Fix Video padding", lay, False,
            "Also fixes XGD2 L0 zero padding when --pL0 is added "
            "under Misc > Extra options.")
        self.w_avatar = self._chk("Show Avatar Awards", lay, False)
        self.w_colors = self._chk("Use colors", lay, True)
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("Verbosity Level:"))
        self.w_verbosity = QComboBox()
        self.w_verbosity.addItems(["Low", "Medium", "High"])
        self.w_verbosity.setCurrentIndex(1)
        vrow.addWidget(self.w_verbosity)
        vrow.addStretch(1)
        lay.addLayout(vrow)
        self.w_corruption = self._chk(
            "Check for AnyDVD style game data corruption", lay, False)
        self.w_showfiles = self._chk(
            "Display ISO Filesystem", lay, False)
        self.w_updates = self._chk("Check for updates", lay, True)
        self.w_csv = self._chk("Include the CSV", lay, False)
        self.w_offline = self._chk(
            "Disable all online functions", lay, False)
        self.w_gamecrc = self._chk(
            "Check Game Partition CRC when needed", lay, True)
        self.w_recurse = self._chk(
            "Recurse subdirectories when using Directory Input",
            lay, False)
        self.w_ach = self._chk("Show Achievements", lay, False)
        self.w_ach_secret = self._chk("Hide secret ones", lay, False)
        lay.addStretch(1)
        return page

    def _file_row(self, parent_layout, chk_label):
        row = QHBoxLayout()
        chk = QCheckBox(chk_label)
        edit = QLineEdit()
        btn = QPushButton("Browse...")
        row.addWidget(chk)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        parent_layout.addLayout(row)
        return chk, edit, btn

    def _tab_patch(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.w_patch_anyway = self._chk(
            "Patch even if stealth passes", lay, False)
        self.w_patch_garbage = self._chk(
            "Patch even if these files are invalid", lay, False)
        (self.w_p_video, self.w_p_video_f,
         self.w_p_video_b) = self._file_row(lay, "Patch Video")
        (self.w_p_pfi, self.w_p_pfi_f,
         self.w_p_pfi_b) = self._file_row(lay, "Patch PFI")
        (self.w_p_dmi, self.w_p_dmi_f,
         self.w_p_dmi_b) = self._file_row(lay, "Patch DMI")
        (self.w_p_ss, self.w_p_ss_f,
         self.w_p_ss_b) = self._file_row(lay, "Patch SS")
        self.w_clobber = self._chk(
            "Overwrite these files without prompting", lay, False)
        lay.addSpacing(8)
        (self.w_e_video, self.w_e_video_f,
         self.w_e_video_b) = self._file_row(lay, "Extract Video")
        self.w_e_entire = self._chk(
            "Extract entire video partition (253 MB)", lay, False)
        (self.w_e_pfi, self.w_e_pfi_f,
         self.w_e_pfi_b) = self._file_row(lay, "Extract PFI")
        (self.w_e_dmi, self.w_e_dmi_f,
         self.w_e_dmi_b) = self._file_row(lay, "Extract DMI")
        (self.w_e_ss, self.w_e_ss_f,
         self.w_e_ss_b) = self._file_row(lay, "Extract SS")
        note = QLabel(
            "Note: extraction happens before patching when both "
            "are chosen.")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        return page

    def _tab_autofix(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("AutoFix Threshold:"))
        self.w_autofix = QComboBox()
        self.w_autofix.addItems(AUTOFIX_LABELS)
        self.w_autofix.setCurrentIndex(1)
        row.addWidget(self.w_autofix, 1)
        lay.addLayout(row)
        ssbox = QGroupBox("SS Challenge / Response Data")
        slay = QVBoxLayout(ssbox)
        self.w_trust = self._chk("Trust SS v2 angles", slay, True)
        self.w_angle359 = self._chk(
            "Adjust SS v1 angle 359 for iXtreme < v1.4", slay, False)
        self.w_fixdrt = self._chk(
            "Fix C/R Table if data is invalid", slay, True)
        drow = QHBoxLayout()
        self.w_fixdev = QCheckBox(
            "Adjust angles that deviate more than")
        self.w_fixdev.setChecked(True)
        drow.addWidget(self.w_fixdev)
        self.w_fixdev_value = QComboBox()
        self.w_fixdev_value.addItems([str(i) for i in range(14)])
        self.w_fixdev_value.setCurrentIndex(3)
        drow.addWidget(self.w_fixdev_value)
        drow.addWidget(QLabel("degrees from their CCRT targets"))
        drow.addStretch(1)
        slay.addLayout(drow)
        lay.addWidget(ssbox)
        lay.addStretch(1)
        return page

    def _tab_rebuild(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel(
            "Choose the method for rebuilding an ISO if it's "
            "missing space for a video partition."))
        self.rebuild_group = QButtonGroup()
        self.w_rb_default = QRadioButton("Default Method")
        self.w_rb_low = QRadioButton("Low Disk Space Method")
        self.w_rb_none = QRadioButton("Don't rebuild")
        self.w_rb_default.setChecked(True)
        self.w_rb_low.setToolTip(
            "Only requires 253 MB free space but will corrupt "
            "your ISO if it fails during the rebuilding process.")
        self.w_rb_default.setToolTip(
            "Requires 7 to 7.5 GB free space on the partition "
            "your ISO is located.")
        for rb in (self.w_rb_default, self.w_rb_low, self.w_rb_none):
            self.rebuild_group.addButton(rb)
            lay.addWidget(rb)
        self.w_keep = self._chk(
            "Don't delete the original ISO after rebuilding",
            lay, False)
        lay.addStretch(1)
        return page

    def _tab_misc(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Your console's region code:"))
        self.w_region = QLineEdit()
        self.w_region.setMaxLength(8)
        rrow.addWidget(self.w_region)
        self.btn_region = QPushButton("Select...")
        rrow.addWidget(self.btn_region)
        rrow.addStretch(1)
        lay.addLayout(rrow)
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Preferred Language:"))
        self.w_lang = QComboBox()
        self.w_lang.addItems(engine.LANGUAGES)
        lrow.addWidget(self.w_lang)
        lrow.addStretch(1)
        lay.addLayout(lrow)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("SplitVid:"))
        self.w_splitvid = QComboBox()
        self.w_splitvid.addItems([
            "Add it if it doesn't exist or isn't valid",
            "Remove it if it exists",
            "Leave it the way it is"])
        self.w_splitvid.setCurrentIndex(2)
        srow.addWidget(self.w_splitvid)
        srow.addStretch(1)
        lay.addLayout(srow)
        irow = QHBoxLayout()
        irow.addWidget(QLabel("Images:"))
        self.w_images = QComboBox()
        self.w_images.addItems([
            "Extract images when using HTML output",
            "Extract images always",
            "Don't extract images"])
        irow.addWidget(self.w_images)
        self.w_embed = QCheckBox("Embed them in HTML")
        irow.addWidget(self.w_embed)
        irow.addStretch(1)
        lay.addLayout(irow)
        mrow = QHBoxLayout()
        self.w_match = QCheckBox("Match Only (Directory input):")
        mrow.addWidget(self.w_match)
        self.w_match_mask = QLineEdit()
        mrow.addWidget(self.w_match_mask, 1)
        self.btn_match = QPushButton("Select...")
        mrow.addWidget(self.btn_match)
        lay.addLayout(mrow)
        lay.addWidget(QLabel(
            "Add extra command line options here (for advanced "
            "users only):"))
        self.w_extra = QLineEdit()
        lay.addWidget(self.w_extra)
        lay.addStretch(1)
        return page

    def _tab_quickstart(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        self.w_qs = QComboBox()
        self.w_qs.addItems(list(QUICKSTART.keys()))
        lay.addWidget(self.w_qs)
        self.qs_text = QPlainTextEdit()
        self.qs_text.setReadOnly(True)
        self.qs_text.setPlainText(QUICKSTART["Welcome!"])
        lay.addWidget(self.qs_text, 1)
        return page

    # ----------------------------------------------------------
    # Menus
    # ----------------------------------------------------------
    def _build_menus(self):
        mb = self.menuBar()
        file_menu = mb.addMenu("File")
        act = file_menu.addAction("Save Settings...")
        act.setShortcut(QKeySequence("Ctrl+S"))
        act.triggered.connect(self._preset_save)
        act = file_menu.addAction("Load Settings...")
        act.setShortcut(QKeySequence("Ctrl+L"))
        act.triggered.connect(self._preset_load)
        act = file_menu.addAction("Delete Settings...")
        act.setShortcut(QKeySequence("Ctrl+D"))
        act.triggered.connect(self._preset_delete)
        file_menu.addSeparator()
        self.menu_reopen_files = file_menu.addMenu("Reopen File(s)")
        self.menu_reopen_dirs = file_menu.addMenu(
            "Reopen Directory")
        act = file_menu.addAction("Clear History")
        act.triggered.connect(self._history_clear)
        file_menu.addSeparator()
        act = file_menu.addAction("Exit")
        act.triggered.connect(self.close)
        self._refresh_history_menus()

        help_menu = mb.addMenu("Help")
        act = help_menu.addAction("Official site")
        act.triggered.connect(lambda: QDesktopServices.openUrl(
            QUrl(engine.SITE_URL)))
        act = help_menu.addAction("Re-run first-run setup")
        act.triggered.connect(lambda _checked=False:
                              self._start_setup())
        help_menu.addSeparator()
        act = help_menu.addAction(
            "Where is my StealthFiles folder...")
        act.setShortcut(QKeySequence("Ctrl+F"))
        act.triggered.connect(
            lambda: self._open_folder(engine.stealthfiles_dir(),
                                      "StealthFiles"))
        act = help_menu.addAction("Where is my Images folder...")
        act.setShortcut(QKeySequence("Ctrl+I"))
        act.triggered.connect(
            lambda: self._open_folder(engine.images_dir(), "Images"))
        help_menu.addSeparator()
        act = help_menu.addAction("About")
        act.triggered.connect(self._about)

    def _open_folder(self, path, label):
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self, label + " folder",
                "The %s folder does not exist yet. It will be at:\n%s"
                "\nabgx360 creates it the first time it runs."
                % (label, path))

    def _about(self):
        QMessageBox.about(
            self, "About abgx360 GUI",
            "abgx360 GUI -- a batch front-end for abgx360 v1.0.7 "
            "[Hadzz Fork].\n\nabgx360 and the original GUI are by "
            "Seacrest; the v1.0.7 fork is maintained by Hadzz / "
            "Bakasura. This app reproduces the original GUI's "
            "options and command construction, and adds a queue, "
            "parsed results and a status bar.")

    def _refresh_history_menus(self):
        for menu, key, kind in (
                (self.menu_reopen_files, "files", "file"),
                (self.menu_reopen_dirs, "dirs", "dir")):
            menu.clear()
            for entry in self.history.get(key, []):
                act = menu.addAction(entry)
                act.triggered.connect(
                    lambda _c=False, p=entry, k=kind:
                    self._add_item(k, p))

    def _history_clear(self):
        self.history = {"files": [], "dirs": []}
        engine.save_history(self.history)
        self._refresh_history_menus()

    # ----------------------------------------------------------
    # Wiring + interlocks
    # ----------------------------------------------------------
    def _wire(self):
        self.btn_add_file.clicked.connect(self._add_file_dialog)
        self.btn_add_folder.clicked.connect(self._add_folder_dialog)
        self.btn_add_net.clicked.connect(self._net_share_dialog)
        self.btn_add_dvd.clicked.connect(self._add_dvd_dialog)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self._clear_queue)
        self.btn_run.clicked.connect(self._run_queue)
        self.btn_stop.clicked.connect(self._stop_queue)
        self.btn_output_file.clicked.connect(self._output_file_dialog)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.btn_region.clicked.connect(self._region_dialog)
        self.btn_match.clicked.connect(self._match_dialog)
        self.w_qs.currentTextChanged.connect(
            lambda t: self.qs_text.setPlainText(QUICKSTART[t]))
        pairs = [(self.w_p_video_b, self.w_p_video_f, False),
                 (self.w_p_pfi_b, self.w_p_pfi_f, False),
                 (self.w_p_dmi_b, self.w_p_dmi_f, False),
                 (self.w_p_ss_b, self.w_p_ss_f, False),
                 (self.w_e_video_b, self.w_e_video_f, True),
                 (self.w_e_pfi_b, self.w_e_pfi_f, True),
                 (self.w_e_dmi_b, self.w_e_dmi_f, True),
                 (self.w_e_ss_b, self.w_e_ss_f, True)]
        for btn, edit, save in pairs:
            btn.clicked.connect(
                lambda _c=False, e=edit, s=save:
                self._pick_file(e, s))
        # any settings change -> interlocks + preview
        for w in self._settings_widgets():
            if isinstance(w, QCheckBox):
                w.toggled.connect(self._refresh_interlocks)
            elif isinstance(w, QRadioButton):
                w.toggled.connect(self._refresh_interlocks)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(
                    self._refresh_interlocks)
            elif isinstance(w, QLineEdit):
                w.textChanged.connect(self._refresh_interlocks)

    def _settings_widgets(self):
        return [
            self.w_write_disable, self.w_output_mode,
            self.w_output_file, self.w_maximize, self.w_open_done,
            self.w_terminal, self.w_dvd_file, self.w_stealth,
            self.w_verify, self.w_padding, self.w_avatar,
            self.w_colors, self.w_verbosity, self.w_corruption,
            self.w_showfiles, self.w_updates, self.w_csv,
            self.w_offline, self.w_gamecrc, self.w_recurse,
            self.w_ach, self.w_ach_secret, self.w_patch_anyway,
            self.w_patch_garbage, self.w_p_video, self.w_p_video_f,
            self.w_p_pfi, self.w_p_pfi_f, self.w_p_dmi,
            self.w_p_dmi_f, self.w_p_ss, self.w_p_ss_f,
            self.w_clobber, self.w_e_video, self.w_e_video_f,
            self.w_e_entire, self.w_e_pfi, self.w_e_pfi_f,
            self.w_e_dmi, self.w_e_dmi_f, self.w_e_ss,
            self.w_e_ss_f, self.w_autofix, self.w_trust,
            self.w_angle359, self.w_fixdrt, self.w_fixdev,
            self.w_fixdev_value, self.w_rb_default, self.w_rb_low,
            self.w_rb_none, self.w_keep, self.w_region, self.w_lang,
            self.w_splitvid, self.w_images, self.w_embed,
            self.w_match, self.w_match_mask, self.w_extra,
        ]

    def _refresh_interlocks(self):
        s = self.collect_settings()
        # offline => updates off; updates off => csv off
        self.w_updates.setEnabled(not s["StayOffline"])
        if s["StayOffline"]:
            self.w_updates.setChecked(False)
        csv_ok = s["OnlineUpdate"] and not s["StayOffline"]
        self.w_csv.setEnabled(csv_ok)
        if not csv_ok:
            self.w_csv.setChecked(False)
        # stealth off => verify off
        self.w_verify.setEnabled(s["CheckStealth"])
        if not s["CheckStealth"]:
            self.w_verify.setChecked(False)
        # game crc never => corruption off
        self.w_corruption.setEnabled(s["CheckGameCRCWhenNeeded"])
        if not s["CheckGameCRCWhenNeeded"]:
            self.w_corruption.setChecked(False)
        # rebuild method != default => keep-original off
        keep_ok = s["RebuildMethod"] == 0
        self.w_keep.setEnabled(keep_ok)
        if not keep_ok:
            self.w_keep.setChecked(False)
        # images never => embed off
        self.w_embed.setEnabled(s["XexImages"] != 2)
        if s["XexImages"] == 2:
            self.w_embed.setChecked(False)
        # file fields follow their checkboxes
        for chk, edit, btn in (
                (self.w_p_video, self.w_p_video_f, self.w_p_video_b),
                (self.w_p_pfi, self.w_p_pfi_f, self.w_p_pfi_b),
                (self.w_p_dmi, self.w_p_dmi_f, self.w_p_dmi_b),
                (self.w_p_ss, self.w_p_ss_f, self.w_p_ss_b),
                (self.w_e_video, self.w_e_video_f, self.w_e_video_b),
                (self.w_e_pfi, self.w_e_pfi_f, self.w_e_pfi_b),
                (self.w_e_dmi, self.w_e_dmi_f, self.w_e_dmi_b),
                (self.w_e_ss, self.w_e_ss_f, self.w_e_ss_b)):
            edit.setEnabled(chk.isChecked())
            btn.setEnabled(chk.isChecked())
        self.w_e_entire.setEnabled(self.w_e_video.isChecked())
        if not self.w_e_video.isChecked():
            self.w_e_entire.setChecked(False)
        self.w_match_mask.setEnabled(self.w_match.isChecked())
        self.btn_match.setEnabled(self.w_match.isChecked())
        self.w_output_file.setEnabled(s["ProgramOutput"] != 0)
        self.btn_output_file.setEnabled(s["ProgramOutput"] != 0)
        self._update_preview()

    # ----------------------------------------------------------
    # Settings <-> widgets
    # ----------------------------------------------------------
    def collect_settings(self):
        s = {}
        s["WriteDisable"] = self.w_write_disable.isChecked()
        s["ProgramOutput"] = self.w_output_mode.currentIndex()
        s["OutputFile"] = self.w_output_file.text()
        s["Maximize"] = self.w_maximize.isChecked()
        s["OpenFileWhenDone"] = self.w_open_done.isChecked()
        s["TerminalFont"] = self.w_terminal.isChecked()
        s["CheckDVDFile"] = self.w_dvd_file.isChecked()
        s["CheckStealth"] = self.w_stealth.isChecked()
        s["Verify"] = self.w_verify.isChecked()
        s["CheckVideoPadding"] = self.w_padding.isChecked()
        s["ShowAvatarAwards"] = self.w_avatar.isChecked()
        s["UseColors"] = self.w_colors.isChecked()
        s["Verbosity"] = self.w_verbosity.currentIndex()
        s["CheckCorruption"] = self.w_corruption.isChecked()
        s["DisplayFilesystem"] = self.w_showfiles.isChecked()
        s["OnlineUpdate"] = self.w_updates.isChecked()
        s["CSVUpdate"] = self.w_csv.isChecked()
        s["StayOffline"] = self.w_offline.isChecked()
        s["CheckGameCRCWhenNeeded"] = self.w_gamecrc.isChecked()
        s["RecurseSubdirs"] = self.w_recurse.isChecked()
        s["ShowAchievements"] = self.w_ach.isChecked()
        s["HideSecretAchievements"] = self.w_ach_secret.isChecked()
        s["PatchIfStealthPasses"] = self.w_patch_anyway.isChecked()
        s["PatchIfInvalid"] = self.w_patch_garbage.isChecked()
        s["PatchVideo"] = self.w_p_video.isChecked()
        s["PatchVideoFile"] = self.w_p_video_f.text()
        s["PatchPFI"] = self.w_p_pfi.isChecked()
        s["PatchPFIFile"] = self.w_p_pfi_f.text()
        s["PatchDMI"] = self.w_p_dmi.isChecked()
        s["PatchDMIFile"] = self.w_p_dmi_f.text()
        s["PatchSS"] = self.w_p_ss.isChecked()
        s["PatchSSFile"] = self.w_p_ss_f.text()
        s["Clobber"] = self.w_clobber.isChecked()
        s["ExtractVideo"] = self.w_e_video.isChecked()
        s["ExtractVideoFile"] = self.w_e_video_f.text()
        s["ExtractEntireVideoPartition"] = \
            self.w_e_entire.isChecked()
        s["ExtractPFI"] = self.w_e_pfi.isChecked()
        s["ExtractPFIFile"] = self.w_e_pfi_f.text()
        s["ExtractDMI"] = self.w_e_dmi.isChecked()
        s["ExtractDMIFile"] = self.w_e_dmi_f.text()
        s["ExtractSS"] = self.w_e_ss.isChecked()
        s["ExtractSSFile"] = self.w_e_ss_f.text()
        s["AutoFix"] = self.w_autofix.currentIndex()
        s["TrustSSv2"] = self.w_trust.isChecked()
        s["FixAngle359"] = self.w_angle359.isChecked()
        s["FixDRT"] = self.w_fixdrt.isChecked()
        s["FixBadAngles"] = self.w_fixdev.isChecked()
        s["FixBadAnglesValue"] = self.w_fixdev_value.currentIndex()
        if self.w_rb_low.isChecked():
            s["RebuildMethod"] = 1
        elif self.w_rb_none.isChecked():
            s["RebuildMethod"] = 2
        else:
            s["RebuildMethod"] = 0
        s["KeepOriginalISO"] = self.w_keep.isChecked()
        s["MyRegion"] = self.w_region.text().strip()
        s["PreferredLang"] = self.w_lang.currentIndex()
        s["SplitVid"] = self.w_splitvid.currentIndex()
        s["XexImages"] = self.w_images.currentIndex()
        s["EmbedImages"] = self.w_embed.isChecked()
        s["ExtraOptions"] = self.w_extra.text()
        s["MatchOnly"] = self.w_match.isChecked()
        s["MatchMask"] = self.w_match_mask.text()
        return s

    def apply_settings(self, s):
        merged = dict(engine.DEFAULT_SETTINGS)
        merged.update({k: v for k, v in s.items()
                       if k in engine.DEFAULT_SETTINGS})
        self.w_write_disable.setChecked(merged["WriteDisable"])
        self.w_output_mode.setCurrentIndex(merged["ProgramOutput"])
        self.w_output_file.setText(merged["OutputFile"])
        self.w_maximize.setChecked(merged["Maximize"])
        self.w_open_done.setChecked(merged["OpenFileWhenDone"])
        self.w_terminal.setChecked(merged["TerminalFont"])
        self.w_dvd_file.setChecked(merged["CheckDVDFile"])
        self.w_stealth.setChecked(merged["CheckStealth"])
        self.w_verify.setChecked(merged["Verify"])
        self.w_padding.setChecked(merged["CheckVideoPadding"])
        self.w_avatar.setChecked(merged["ShowAvatarAwards"])
        self.w_colors.setChecked(merged["UseColors"])
        self.w_verbosity.setCurrentIndex(merged["Verbosity"])
        self.w_corruption.setChecked(merged["CheckCorruption"])
        self.w_showfiles.setChecked(merged["DisplayFilesystem"])
        self.w_updates.setChecked(merged["OnlineUpdate"])
        self.w_csv.setChecked(merged["CSVUpdate"])
        self.w_offline.setChecked(merged["StayOffline"])
        self.w_gamecrc.setChecked(merged["CheckGameCRCWhenNeeded"])
        self.w_recurse.setChecked(merged["RecurseSubdirs"])
        self.w_ach.setChecked(merged["ShowAchievements"])
        self.w_ach_secret.setChecked(
            merged["HideSecretAchievements"])
        self.w_patch_anyway.setChecked(
            merged["PatchIfStealthPasses"])
        self.w_patch_garbage.setChecked(merged["PatchIfInvalid"])
        self.w_p_video.setChecked(merged["PatchVideo"])
        self.w_p_video_f.setText(merged["PatchVideoFile"])
        self.w_p_pfi.setChecked(merged["PatchPFI"])
        self.w_p_pfi_f.setText(merged["PatchPFIFile"])
        self.w_p_dmi.setChecked(merged["PatchDMI"])
        self.w_p_dmi_f.setText(merged["PatchDMIFile"])
        self.w_p_ss.setChecked(merged["PatchSS"])
        self.w_p_ss_f.setText(merged["PatchSSFile"])
        self.w_clobber.setChecked(merged["Clobber"])
        self.w_e_video.setChecked(merged["ExtractVideo"])
        self.w_e_video_f.setText(merged["ExtractVideoFile"])
        self.w_e_entire.setChecked(
            merged["ExtractEntireVideoPartition"])
        self.w_e_pfi.setChecked(merged["ExtractPFI"])
        self.w_e_pfi_f.setText(merged["ExtractPFIFile"])
        self.w_e_dmi.setChecked(merged["ExtractDMI"])
        self.w_e_dmi_f.setText(merged["ExtractDMIFile"])
        self.w_e_ss.setChecked(merged["ExtractSS"])
        self.w_e_ss_f.setText(merged["ExtractSSFile"])
        self.w_autofix.setCurrentIndex(merged["AutoFix"])
        self.w_trust.setChecked(merged["TrustSSv2"])
        self.w_angle359.setChecked(merged["FixAngle359"])
        self.w_fixdrt.setChecked(merged["FixDRT"])
        self.w_fixdev.setChecked(merged["FixBadAngles"])
        self.w_fixdev_value.setCurrentIndex(
            merged["FixBadAnglesValue"])
        method = merged["RebuildMethod"]
        (self.w_rb_default if method == 0 else
         self.w_rb_low if method == 1 else
         self.w_rb_none).setChecked(True)
        self.w_keep.setChecked(merged["KeepOriginalISO"])
        self.w_region.setText(merged["MyRegion"])
        self.w_lang.setCurrentIndex(merged["PreferredLang"])
        self.w_splitvid.setCurrentIndex(merged["SplitVid"])
        self.w_images.setCurrentIndex(merged["XexImages"])
        self.w_embed.setChecked(merged["EmbedImages"])
        self.w_extra.setText(merged["ExtraOptions"])
        self.w_match.setChecked(merged["MatchOnly"])
        self.w_match_mask.setText(merged["MatchMask"])
        self._refresh_interlocks()

    def _load_initial_settings(self):
        preset = engine.load_preset("Default")
        if preset is not None:
            self.apply_settings(preset)
        else:
            self.apply_settings(engine.DEFAULT_SETTINGS)
        if self.collect_settings()["Maximize"]:
            self.showMaximized()

    # ----------------------------------------------------------
    # Presets
    # ----------------------------------------------------------
    def _preset_save(self):
        name, ok = QInputDialog.getText(
            self, "Save Settings",
            "Enter a name for these settings. Saving them as "
            "\"Default\" will cause them to be loaded every time "
            "abgx360 GUI is launched.", text="Default")
        if ok and name.strip():
            engine.save_preset(name.strip(),
                               self.collect_settings())
            self._set_stage("Settings saved as \"%s\"." % name)

    def _preset_pick(self, title):
        names = engine.list_presets()
        if not names:
            QMessageBox.information(
                self, title, "No saved settings yet.")
            return None
        name, ok = QInputDialog.getItem(
            self, title, "Settings:", names, 0, False)
        return name if ok else None

    def _preset_load(self):
        name = self._preset_pick("Load Settings")
        if name:
            data = engine.load_preset(name)
            if data is not None:
                self.apply_settings(data)
                self._set_stage(
                    "Settings \"%s\" loaded." % name)

    def _preset_delete(self):
        name = self._preset_pick("Delete Settings")
        if name:
            engine.delete_preset(name)
            self._set_stage("Settings \"%s\" deleted." % name)

    # ----------------------------------------------------------
    # Queue
    # ----------------------------------------------------------
    def _add_item(self, kind, path):
        for it in self.items:
            if it["kind"] == kind and it["path"] == path:
                return
        name = Path(path).name if kind != "dvd" else path
        item = {"kind": kind, "path": path, "name": name,
                "status": "Queued", "result": "", "results": [],
                "raw": "", "run_path": None, "extracting": False,
                "extract_error": None}
        if kind == "dir":
            try:
                n = len(engine.scan_folder(
                    path, self.w_recurse.isChecked()))
            except Exception:  # noqa: BLE001
                n = 0
            item["name"] = "%s (%d files)" % (name, n)
        is_arc = kind == "file" and archive_input.is_archive(path)
        if is_arc:
            item["extracting"] = True
            item["status"] = "Extracting..."
        self.items.append(item)
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._fill_row(row, item)
        self.table.selectRow(row)
        self._update_preview()
        self._set_stage("Queued %d item(s). Ready."
                        % len(self.items))
        if is_arc:
            self._start_extraction(item)

    def _start_extraction(self, item):
        """Extract an archive item's ISO to local scratch on a
        worker; the row keeps showing the archive the user
        picked, and the engine later runs item["run_path"]."""
        self._set_stage("Extracting %s..." % item["name"])

        def job(log):
            dest = archive_input.extract_iso(item["path"], log=log)
            return {"run_path": str(dest)}

        worker = Worker(job)
        self._workers.add(worker)
        worker.log.connect(
            lambda s: self.raw_log.appendPlainText(s))
        worker.done.connect(
            lambda r: self._extract_finished(item, r, worker))
        worker.start()

    def _extract_finished(self, item, result, worker):
        self._workers.discard(worker)
        item["extracting"] = False
        try:
            idx = self.items.index(item)
        except ValueError:
            return
        if result.get("run_path"):
            item["run_path"] = result["run_path"]
            item["status"] = "Queued"
            self._set_stage(
                "Extracted %s -- queued. The archive itself is "
                "untouched." % item["name"])
        else:
            item["extract_error"] = result.get(
                "error", "extraction failed")
            item["status"] = "Error"
            item["result"] = "Extraction failed"
            item["raw"] = item["extract_error"]
            self._set_stage("Extraction failed for %s -- see "
                            "the item's log." % item["name"])
        self._refresh_row(idx)
        self._update_preview()

    def _fill_row(self, row, item):
        vals = [item["name"],
                {"file": "File", "dir": "Directory",
                 "dvd": "Burned DVD"}[item["kind"]],
                item["status"], item["result"], item["path"]]
        for col, val in enumerate(vals):
            self.table.setItem(row, col, QTableWidgetItem(val))

    def _refresh_row(self, idx):
        if 0 <= idx < self.table.rowCount():
            self._fill_row(idx, self.items[idx])

    def _start_dir(self):
        """Where file dialogs open: the last connected network
        share while it is still reachable, else the dialog's
        default. On Windows the native dialogs also accept a
        typed UNC path (\\\\SERVER\\share) at any time."""
        root = getattr(self, "_last_net_root", "")
        if root and os.path.isdir(root):
            return root
        return ""

    def _add_picked_files(self, paths):
        for p in paths:
            self._add_item("file", p)
            engine.remember(self.history, "files", p)
        if paths:
            self._refresh_history_menus()

    def _add_file_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select ISO file(s)", self._start_dir(),
            "Disc images and archives (*.iso *.000 *.360 *.img "
            "*.bin *.xex *.zip *.7z);;"
            "Disc images (*.iso *.000 *.360 *.img *.bin *.xex);;"
            "Archives (*.zip *.7z);;All files (*)")
        self._add_picked_files(paths)

    def _add_folder_dialog(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select a folder to check", self._start_dir())
        if d:
            self._add_item("dir", d)
            engine.remember(self.history, "dirs", d)
            self._refresh_history_menus()

    def _add_dvd_dialog(self):
        dev, ok = QInputDialog.getText(
            self, "Burned DVD",
            "Drive device (devices are files on Linux, "
            "e.g. /dev/cdrom):", text="/dev/cdrom")
        if ok and dev.strip():
            self._add_item("dvd", dev.strip())

    # ----------------------------------------------------------
    # Network shares
    # ----------------------------------------------------------
    def _net_connect(self, server, share, port=None, username="",
                     password="", workgroup=""):
        """Resolve a share to a browsable root and remember it.
        Returns the root path, or None with self._net_error set.
        This is the one code path the dialog and the smoke driver
        both use: Windows -> the UNC root; Linux -> the GVFS
        mount directory (mounted on demand). The username is
        remembered with the share; the password never is."""
        self._net_error = None
        try:
            root = netshare.browse_root(
                server, share, port, username=username,
                password=password, workgroup=workgroup)
        except netshare.NetShareError as e:
            self._net_error = str(e)
            return None
        except Exception as e:  # noqa: BLE001
            self._net_error = "%s: %s" % (type(e).__name__, e)
            return None
        if sys.platform.startswith("win") \
                and not os.path.isdir(root):
            self._net_error = (
                "Could not reach %s. Check the server and share "
                "names, and that the share is accessible from "
                "this PC." % root)
            return None
        self._last_net_root = root
        netshare.remember_share(server, share, port, user=username)
        return root

    def _net_share_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Network Share")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Browse ISOs on a network share (SMB). On Windows "
            "you can also type a UNC path (\\\\SERVER\\share) "
            "straight into any file dialog."))
        shares = netshare.load_shares()
        if shares:
            lay.addWidget(QLabel("Recent shares:"))
            recent = QListWidget()
            for e in shares:
                recent.addItem(netshare.share_label(e))
            recent.setMaximumHeight(90)
            lay.addWidget(recent)
        else:
            recent = None
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Server:"))
        w_server = QLineEdit()
        w_server.setPlaceholderText("e.g. 192.168.0.102")
        srow.addWidget(w_server, 1)
        lay.addLayout(srow)
        hrow = QHBoxLayout()
        hrow.addWidget(QLabel("Share:"))
        w_share = QLineEdit()
        w_share.setPlaceholderText("e.g. XBOX360 ARCHIVE")
        hrow.addWidget(w_share, 1)
        lay.addLayout(hrow)
        lay.addWidget(QLabel(
            "Credentials -- only if the share asks for them. "
            "The username is remembered; the password is not."))
        crow = QHBoxLayout()
        crow.addWidget(QLabel("User:"))
        w_user = QLineEdit()
        crow.addWidget(w_user, 1)
        crow.addWidget(QLabel("Password:"))
        w_pass = QLineEdit()
        w_pass.setEchoMode(QLineEdit.EchoMode.Password)
        crow.addWidget(w_pass, 1)
        crow.addWidget(QLabel("Domain:"))
        w_domain = QLineEdit()
        w_domain.setPlaceholderText("WORKGROUP")
        crow.addWidget(w_domain, 1)
        lay.addLayout(crow)
        if shares:
            first = shares[0]
            w_server.setText(first["server"])
            w_share.setText(first["share"])
            w_user.setText(first.get("user") or "")

            def _fill(item):
                t = netshare.parse_target(item.text())
                if t:
                    w_server.setText(t["server"])
                    w_share.setText(t["share"])
                    for e in shares:
                        if e["server"].lower() == \
                                t["server"].lower() and \
                                e["share"].lower() == \
                                t["share"].lower():
                            w_user.setText(e.get("user") or "")
                            break
            recent.itemClicked.connect(_fill)
            recent.itemDoubleClicked.connect(_fill)
        status = QLabel("")
        status.setWordWrap(True)
        lay.addWidget(status)
        btns = QHBoxLayout()
        btn_files = QPushButton("Add ISO files...")
        btn_folder = QPushButton("Add folder...")
        btn_close = QPushButton("Close")
        btns.addWidget(btn_files)
        btns.addWidget(btn_folder)
        btns.addStretch(1)
        btns.addWidget(btn_close)
        lay.addLayout(btns)

        def connect():
            t = netshare.parse_target(w_server.text(),
                                      w_share.text())
            if t is None:
                status.setText(
                    "Enter a server and a share name -- or a "
                    "full path like \\\\SERVER\\share or "
                    "smb://SERVER/share.")
                return None
            QApplication.setOverrideCursor(
                Qt.CursorShape.WaitCursor)
            try:
                root = self._net_connect(
                    t["server"], t["share"], t["port"],
                    username=w_user.text().strip(),
                    password=w_pass.text(),
                    workgroup=w_domain.text().strip())
            finally:
                QApplication.restoreOverrideCursor()
            if root is None:
                status.setText(self._net_error or
                               "Could not connect to the share.")
                return None
            if t["subpath"]:
                root = os.path.join(root, t["subpath"])
            status.setText("Connected: " + root)
            return root

        def add_files():
            root = connect()
            if root is None:
                return
            paths, _ = QFileDialog.getOpenFileNames(
                dlg, "Select ISO file(s)", root,
                "Disc images and archives (*.iso *.000 *.360 "
                "*.img *.bin *.xex *.zip *.7z);;"
                "Disc images (*.iso *.000 *.360 *.img *.bin "
                "*.xex);;Archives (*.zip *.7z);;All files (*)")
            self._add_picked_files(paths)
            if paths:
                dlg.accept()

        def add_folder():
            root = connect()
            if root is None:
                return
            d = QFileDialog.getExistingDirectory(
                dlg, "Select a folder to check", root)
            if d:
                self._add_item("dir", d)
                engine.remember(self.history, "dirs", d)
                self._refresh_history_menus()
                dlg.accept()

        btn_files.clicked.connect(add_files)
        btn_folder.clicked.connect(add_folder)
        btn_close.clicked.connect(dlg.reject)
        dlg.exec()

    def _remove_selected(self):
        rows = sorted({i.row() for i in
                       self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.items[r]
            self.table.removeRow(r)
        self._update_preview()

    def _clear_queue(self):
        if self._running:
            return
        self.items.clear()
        self.table.setRowCount(0)
        self.results.setRowCount(0)
        self.raw_log.clear()
        self._update_preview()
        self._set_stage("Queue cleared.")

    def _show_selected(self):
        rows = self.table.selectedIndexes()
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self.items):
            self._show_item(idx)
            self._update_preview()

    def _show_item(self, idx):
        item = self.items[idx]
        self.results.setRowCount(0)
        for r in item["results"]:
            row = self.results.rowCount()
            self.results.insertRow(row)
            self.results.setItem(row, 0, QTableWidgetItem(r["check"]))
            self.results.setItem(row, 1,
                                 QTableWidgetItem(r["result"]))
            self.results.setItem(row, 2,
                                 QTableWidgetItem(r["detail"]))
        self.raw_log.setPlainText(item["raw"])

    def _selected_index(self):
        rows = self.table.selectedIndexes()
        return rows[0].row() if rows else -1

    def _update_preview(self):
        idx = self._selected_index()
        if 0 <= idx < len(self.items):
            item = self.items[idx]
        else:
            item = {"kind": "file", "path": "<file>"}
        try:
            self.preview.setText(engine.preview_command(
                self.collect_settings(), item))
        except Exception:  # noqa: BLE001
            self.preview.setText("")

    # ----------------------------------------------------------
    # Dialogs: files, region, match masks
    # ----------------------------------------------------------
    def _pick_file(self, edit, save):
        if save:
            path, _ = QFileDialog.getSaveFileName(
                self, "Choose destination file", self._start_dir())
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose a file", self._start_dir())
        if path:
            edit.setText(path)

    def _output_file_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Choose the output file", self._start_dir())
        if path:
            self.w_output_file.setText(path)

    def _region_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select regions")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Check the box next to the region of any and all "
            "consoles you own"))
        boxes = [QCheckBox(r) for r in REGIONS]
        for b in boxes:
            lay.addWidget(b)
        # initialise from the current code, as the original does:
        # value = 00 <PAL> <NTSC_J> <NTSC_U> (hex bytes)
        cur = self.w_region.text().strip().upper().rjust(8, "0")
        try:
            pal = int(cur[2:4], 16)
            ntsc_j = int(cur[4:6], 16)
            ntsc_u = int(cur[6:8], 16)
        except Exception:  # noqa: BLE001
            pal = ntsc_j = ntsc_u = 0
        if ntsc_u == 0xFF:
            boxes[0].setChecked(True)
        if pal & 0x01:
            boxes[1].setChecked(True)
        if (pal & 0xFE) == 0xFE:
            boxes[2].setChecked(True)
        if ntsc_j & 0x01:
            boxes[3].setChecked(True)
        if ntsc_j & 0x02:
            boxes[4].setChecked(True)
        if (ntsc_j & 0xFC) == 0xFC:
            boxes[5].setChecked(True)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            pal = ntsc_j = ntsc_u = 0
            if boxes[0].isChecked():
                ntsc_u = 0xFF
            if boxes[1].isChecked():
                pal |= 0x01
            if boxes[2].isChecked():
                pal |= 0xFE
            if boxes[3].isChecked():
                ntsc_j |= 0x01
            if boxes[4].isChecked():
                ntsc_j |= 0x02
            if boxes[5].isChecked():
                ntsc_j |= 0xFC
            self.w_region.setText(
                "00%02X%02X%02X" % (pal, ntsc_j, ntsc_u))

    def _match_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select matches")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(
            "Check the box next to the type of files you want "
            "to match"))
        cur = self.w_match_mask.text()
        boxes = []
        for m in engine.MATCH_MASKS:
            b = QCheckBox(m)
            if (cur.startswith(m) or ("," + m) in cur
                    or (", " + m) in cur):
                b.setChecked(True)
            boxes.append(b)
            lay.addWidget(b)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            chosen = [m for m, b in zip(engine.MATCH_MASKS, boxes)
                      if b.isChecked()]
            if chosen:
                self.w_match_mask.setText(", ".join(chosen))
                self.w_match.setChecked(True)

    # ----------------------------------------------------------
    # First-run setup
    # ----------------------------------------------------------
    def _set_stage(self, text):
        self.stage_label.setText(text)

    def _offer_dep_install(self, info):
        """Ask what to do about missing build deps; returns
        "install" or "manual". Called only on the GUI thread.
        Under the smoke driver the offer is recorded and the
        choice comes from the smoke config instead of a dialog."""
        self._dep_offers.append(dict(info))
        cfg_path = os.environ.get("ABGX360_GUI_SMOKE")
        if cfg_path:
            try:
                cfg = json.loads(Path(cfg_path).read_text())
            except Exception:  # noqa: BLE001
                cfg = {}
            return cfg.get("dep_choice", "manual")
        names = "\n".join("  - " + n for n in info["missing"])
        if info["family"] != "debian":
            QMessageBox.information(
                self, "Build dependencies missing",
                "Building the abgx360 engine needs the following, "
                "which are not installed:\n" + names
                + "\n\nAutomatic install is only available on "
                "Debian/Ubuntu-family systems. On this system, "
                "install them with:\n" + info["manual_command"]
                + "\n\nThen use Help > Re-run first-run setup.")
            return "manual"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Build dependencies missing")
        box.setText(
            "Building the abgx360 engine needs the following, "
            "which are not installed:\n" + names
            + "\n\nPackages: " + ", ".join(info["packages"])
            + "\n\nInstall them automatically now? You will be "
            "asked for your password once.")
        btn_install = box.addButton(
            "Install automatically",
            QMessageBox.ButtonRole.AcceptRole)
        box.addButton("I'll install it myself",
                      QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return "install" if box.clickedButton() is btn_install \
            else "manual"

    def _stop_setup_for_deps(self, info):
        """The user chose to install the deps themselves (or this
        distro has no automatic path): stop setup cleanly -- not
        an error state -- with the exact command in the log."""
        self._setup_stopped = True
        self._set_stage(
            "Setup stopped -- install the build packages, then "
            "use Help > Re-run first-run setup.")
        self.raw_log.appendPlainText("SETUP: " + info["manual_text"])

    def _start_setup(self, install_deps=False):
        if engine.engine_ready():
            self._setup_done = True
            self._set_stage("Ready -- abgx360 engine found.")
            return
        self._setup_error = None
        self._setup_stopped = False
        if not install_deps:
            self._dep_offer_rounds = 0
            # Pre-flight: missing build deps are an offer to
            # install, never a configure dead-end later.
            missing = engine.missing_build_deps()
            if missing:
                info = engine.dep_info(missing)
                if self._offer_dep_install(info) == "install":
                    install_deps = True
                else:
                    self._stop_setup_for_deps(info)
                    return
        self._set_stage("First-run setup: starting...")
        self.btn_run.setEnabled(False)

        def job(log):
            def stage(msg):
                self._stage_queue.append(msg)
            try:
                engine.ensure_engine(log, stage,
                                     install_deps=install_deps)
                return {"ok": True}
            except engine.DepsMissingError as e:
                return {"deps_missing": e.info}
            except engine.EngineError as e:
                return {"error": str(e)}

        self._stage_queue = []
        worker = Worker(job)
        self._workers.add(worker)
        worker.log.connect(lambda s: self.raw_log.appendPlainText(s))
        worker.done.connect(lambda r: self._setup_finished(r, worker))
        worker.start()
        self._setup_timer = QTimer(self)
        self._setup_timer.timeout.connect(self._drain_stage_queue)
        self._setup_timer.start(200)

    def _drain_stage_queue(self):
        while getattr(self, "_stage_queue", None):
            self._set_stage(self._stage_queue.pop(0))

    def _setup_finished(self, result, worker):
        self._workers.discard(worker)
        if hasattr(self, "_setup_timer"):
            self._setup_timer.stop()
        self._drain_stage_queue()
        if result.get("deps_missing"):
            # Configure hit the dependency wall even though the
            # pre-flight passed (or an install attempt was not
            # enough): make the offer from the failure path --
            # once. A second arrival falls through to the plain
            # error below instead of looping the dialog.
            self._dep_offer_rounds += 1
            if self._dep_offer_rounds <= 1:
                info = result["deps_missing"]
                if self._offer_dep_install(info) == "install":
                    self._start_setup(install_deps=True)
                else:
                    self._stop_setup_for_deps(info)
                    self.btn_run.setEnabled(True)
                return
        self.btn_run.setEnabled(True)
        if result.get("ok"):
            self._setup_done = True
            self._set_stage("Ready -- abgx360 engine installed.")
        else:
            self._setup_error = result.get("error") or (
                result["deps_missing"]["manual_text"]
                if result.get("deps_missing") else "setup failed")
            self._set_stage(
                "Setup did not complete -- see the log. "
                "Run Queue is unavailable until the engine is ready.")
            self.raw_log.appendPlainText(
                "SETUP: " + self._setup_error)

    # ----------------------------------------------------------
    # Running the queue
    # ----------------------------------------------------------
    def _run_queue(self):
        if self._running:
            return
        if not self._setup_done and not engine.engine_ready():
            QMessageBox.warning(
                self, "Engine not ready",
                "The abgx360 engine is not installed yet.\n\n"
                + (self._setup_error or
                   "First-run setup has not completed."))
            return
        if not self.items:
            QMessageBox.information(
                self, "Nothing to run", "Add at least one item.")
            return
        if any(it.get("extracting") for it in self.items):
            QMessageBox.information(
                self, "Still extracting",
                "An archive is still being extracted to local "
                "scratch. Wait until its row shows Queued, then "
                "run the queue.")
            return
        settings = self.collect_settings()
        if settings["ProgramOutput"] != 0 and \
                not settings["OutputFile"]:
            path, _ = QFileDialog.getSaveFileName(
                self, "Choose the output file", self._start_dir())
            if not path:
                return
            self.w_output_file.setText(path)
            settings = self.collect_settings()
        self._running = True
        self._stop = False
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setMaximum(len(self.items))
        self.progress_bar.setValue(0)
        threading.Thread(target=self._run_all,
                         args=(settings,), daemon=True).start()

    def _stop_queue(self):
        self._stop = True
        if self._handle is not None:
            self._handle.terminate()

    def _run_all(self, settings):
        # Runs on a plain thread; all widget access goes through
        # the _ui queue drained by a QTimer on the GUI thread.
        done = 0
        for idx, item in enumerate(list(self.items)):
            if self._stop:
                break
            if item.get("extract_error"):
                self._invoke(
                    lambda i=idx, e=item["extract_error"]:
                    self._item_finished(i, e, [],
                                        "Extraction failed"))
                done += 1
                self._invoke(
                    lambda d=done: self.progress_bar.setValue(d))
                continue
            argv = engine.build_argv(settings, item)
            cmd_text = engine.preview_command(settings, item)
            self._invoke(lambda i=idx, c=cmd_text: self._item_started(i, c))
            handle = engine.start_run(argv)
            self._handle = handle
            raw_lines = []
            try:
                for line in handle.proc.stdout:
                    raw_lines.append(line)
                    plain = engine.strip_ansi(line).strip()
                    if plain.startswith("Checking") or \
                            plain.startswith("Stealth") or \
                            "AutoFix" in plain:
                        self._invoke(
                            lambda i=idx, n=item["name"], p=plain:
                            self._set_stage(
                                "Checking %d of %d: %s -- %s"
                                % (i + 1, len(self.items), n,
                                   p[:80])))
                handle.proc.wait()
                rc = handle.proc.returncode
            except Exception as e:  # noqa: BLE001
                rc = -1
                raw_lines.append("GUI error: %s" % e)
            self._handle = None
            raw = "".join(raw_lines)
            results = engine.parse_results(engine.strip_ansi(raw))
            verdict = self._verdict(results, rc)
            self._invoke(lambda i=idx, r=raw, res=results, v=verdict:
                         self._item_finished(i, r, res, v))
            done += 1
            self._invoke(lambda d=done: self.progress_bar.setValue(d))
        self._invoke(lambda: self._batch_finished(settings, done))

    def _invoke(self, fn):
        # thread-safe-ish handoff: append and let the GUI timer run it
        if threading.current_thread() is threading.main_thread():
            fn()
        else:
            self._ui_queue.append(fn)

    def _drain_ui_queue(self):
        while getattr(self, "_ui_queue", None):
            fn = self._ui_queue.pop(0)
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    def _verdict(self, results, rc):
        fails = sum(1 for r in results if r["result"] == "FAIL")
        passes = sum(1 for r in results if r["result"] == "PASS")
        if rc != 0 and not results:
            return "Error (exit %d)" % rc
        if fails:
            return "%d failed, %d passed" % (fails, passes)
        if passes:
            return "All checks passed (%d)" % passes
        return "Done (exit %d)" % rc

    def _item_started(self, idx, cmd_text):
        item = self.items[idx]
        item["status"] = "Running"
        item["raw"] = ""
        item["results"] = []
        self._refresh_row(idx)
        self.table.selectRow(idx)
        self._set_stage("Checking %d of %d: %s"
                        % (idx + 1, len(self.items), item["name"]))
        self.raw_log.setPlainText("Running: " + cmd_text + "\n")

    def _item_finished(self, idx, raw, results, verdict):
        item = self.items[idx]
        item["raw"] = raw
        item["results"] = results
        item["status"] = "Done"
        item["result"] = verdict
        self._refresh_row(idx)
        if self._selected_index() == idx:
            self._show_item(idx)

    def _batch_finished(self, settings, done):
        self._running = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        failed = sum(1 for it in self.items
                     if it["status"] == "Done"
                     and it["result"].startswith(("Error",))
                     )
        self._set_stage(
            "Batch finished: %d item(s) checked." % done)
        # HTML / Text output modes: the original redirects the
        # program output to the chosen file -- concatenate the
        # items' raw output (ANSI kept for HTML, stripped by the
        # CLI itself for Text thanks to the bundled -s).
        if settings["ProgramOutput"] != 0 and settings["OutputFile"]:
            try:
                text = "\n".join(
                    engine.strip_ansi(it["raw"])
                    if settings["ProgramOutput"] == 2 else it["raw"]
                    for it in self.items)
                Path(settings["OutputFile"]).write_text(
                    text, errors="replace")
                if settings["OpenFileWhenDone"]:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(
                        settings["OutputFile"]))
            except Exception as e:  # noqa: BLE001
                self.raw_log.appendPlainText(
                    "Writing the output file failed: %s" % e)
        _ = failed

    # ----------------------------------------------------------
    # Smoke hook (scripted acceptance driver; inert otherwise)
    # ----------------------------------------------------------
    def _maybe_smoke(self):
        cfg_path = os.environ.get("ABGX360_GUI_SMOKE")
        if not cfg_path:
            return
        try:
            self._smoke_cfg = json.loads(Path(cfg_path).read_text())
        except Exception:  # noqa: BLE001
            return
        self._smoke_state = {"events": []}
        self._smoke_phase = "setup"
        self._smoke_timer = QTimer(self)
        self._smoke_timer.timeout.connect(self._smoke_tick)
        self._smoke_timer.start(250)

    def _smoke_shot(self, path):
        if path:
            self.grab().save(path)
            self._smoke_state["events"].append("shot:" + path)

    def _smoke_tick(self):
        cfg = self._smoke_cfg
        st = self._smoke_state
        phase = self._smoke_phase
        if phase == "setup":
            if self._setup_done or self._setup_error \
                    or getattr(self, "_setup_stopped", False):
                st["stage_after_setup"] = self.stage_label.text()
                st["setup_error"] = self._setup_error
                st["setup_stopped"] = bool(
                    getattr(self, "_setup_stopped", False))
                st["dep_offers"] = list(
                    getattr(self, "_dep_offers", []))
                self._smoke_shot(cfg.get("shot_setup"))
                if cfg.get("settings"):
                    self.apply_settings(cfg["settings"])
                net_root = None
                if cfg.get("net_share"):
                    ns = cfg["net_share"]
                    net_root = self._net_connect(
                        ns["server"], ns["share"],
                        ns.get("port"),
                        username=ns.get("user", ""),
                        password=ns.get("password", ""),
                        workgroup=ns.get("workgroup", ""))
                    st["net_root"] = net_root
                    st["net_error"] = self._net_error
                for p in cfg.get("add_files", []):
                    self._add_item("file", p)
                for p in cfg.get("net_add_files", []):
                    if net_root:
                        self._add_item(
                            "file", os.path.join(net_root, p))
                if cfg.get("net_add_folder") and net_root:
                    self._add_item(
                        "dir", os.path.join(
                            net_root, cfg["net_add_folder"]))
                if cfg.get("add_folder"):
                    self._add_item("dir", cfg["add_folder"])
                if cfg.get("add_dvd"):
                    self._add_item("dvd", cfg["add_dvd"])
                st["commands"] = [
                    engine.preview_command(
                        self.collect_settings(), it)
                    for it in self.items]
                st["queue"] = [
                    {"kind": it["kind"], "path": it["path"],
                     "name": it["name"]} for it in self.items]
                self._smoke_phase = "run" if cfg.get("run_queue") \
                    else "finish"
            return
        if phase == "run":
            settling = any(it.get("extracting")
                           for it in self.items)
            if not self._running and not st.get("run_started") \
                    and not settling:
                st["run_started"] = True
                self._run_queue()
                self._smoke_phase = "mid"
            return
        if phase == "mid":
            if any(it["status"] == "Running" for it in self.items):
                st["mid_run_stage"] = self.stage_label.text()
                self._smoke_shot(cfg.get("shot_mid"))
                self._smoke_phase = "wait_done"
            elif not self._running:
                self._smoke_phase = "finish"
            return
        if phase == "wait_done":
            if not self._running:
                self._smoke_phase = "finish"
            return
        if phase == "finish":
            self._smoke_timer.stop()
            st["stage_final"] = self.stage_label.text()
            st["items"] = [
                {"name": it["name"], "status": it["status"],
                 "result": it["result"], "results": it["results"],
                 "path": it["path"],
                 "run_path": it.get("run_path"),
                 "raw_tail": it["raw"][-4000:]}
                for it in self.items]
            self._smoke_shot(cfg.get("shot_done"))
            out = cfg.get("out_state")
            if out:
                Path(out).write_text(json.dumps(st, indent=1))
            QTimer.singleShot(200, self.close)


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    win._maybe_smoke()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
