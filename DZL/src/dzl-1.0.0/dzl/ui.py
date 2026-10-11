import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QIcon, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QListWidget, QListWidgetItem, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QProgressDialog, QDialog, QDialogButtonBox, QFormLayout,
    QInputDialog, QFileDialog, QStatusBar, QGroupBox, QCheckBox,
    QApplication, QProgressBar, QTextEdit, QMenu,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)

from PySide6.QtGui import QPalette, QFont
from PySide6.QtWidgets import QColorDialog, QScrollArea

from dzl import api, steam, mods, favorites

COLOR_ITEMS = [
    ("text", "Text", None),
    ("background", "Background", None),
    ("accent", "Accent", None),
    ("selected_row", "Selected Row", "#3a3a3a"),
    ("selected_text", "Selected Row Text", None),
    ("hover", "Row Hover", "#2b2b2b"),
    ("header_bg", "Column Header", None),
    ("button_bg", "Button", None),
    ("button_hover", "Button Hover", None),
    ("tab_bar", "Tab", None),
    ("tab_selected", "Selected Tab", None),
    ("star_on", "Star On", "#f5c518"),
    ("star_off", "Star Off", "#808080"),
]

COLOR_GROUPS = [
    ("General", ["text", "background", "accent"]),
    ("Tables and Lists", [
        "selected_row", "selected_text", "hover", "header_bg",
    ]),
    ("Buttons", ["button_bg", "button_hover"]),
    ("Tabs", ["tab_bar", "tab_selected"]),
    ("Favorites", ["star_on", "star_off"]),
]
PING_COL = 5
STAR_COL = 6


def _mod_stats(paths):
    import datetime
    out = []
    for p in paths:
        size = mods.human_size(mods.dir_size(p))
        newest = mods.newest_mtime(p)
        date = (
            datetime.datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M")
            if newest else "?"
        )
        out.append((size, date))
    return out


class StarDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
        brush = index.data(Qt.ForegroundRole)
        painter.save()
        if brush is not None:
            painter.setPen(brush.color())
        painter.setFont(opt.font)
        painter.drawText(option.rect, Qt.AlignCenter, "★")
        painter.restore()


class Worker(QThread):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DZL - DayZ Mod Launcher")
        self.resize(1100, 720)
        self.setMinimumSize(800, 500)

        self.steamapps = None
        self.game_dir = None
        self.mods_dir = None
        self.downloads_dir = None
        self.config_dir = Path.home() / ".config" / "dzl"
        self.cache_dir = Path.home() / ".cache" / "dzl"
        self.favs = favorites.Favorites(self.config_dir / "favorites.json")

        self._pending_server = None
        self._pending_mod_ids = None
        self._server_index = {}
        self._last_query = ""
        self._pings = {}
        self._ping_gen = 0
        self._worker = None
        self._workers = []

        self._setup_paths()
        self._load_colors()
        self._build_ui()
        self._load_username()
        QTimer.singleShot(0, self._check_steam_binary)
        QTimer.singleShot(0, lambda: self._refresh_all(True))

    def _setup_paths(self):
        try:
            self.steamapps = steam.find_steamapps()
            self.game_dir = self.steamapps / "common" / "DayZ"
            self.mods_dir = self.steamapps / "workshop" / "content" / steam.DAYZ_APPID
            self.downloads_dir = self.steamapps / "workshop" / "downloads"
            self.game_dir.mkdir(parents=True, exist_ok=True)
            self.mods_dir.mkdir(parents=True, exist_ok=True)
        except RuntimeError as e:
            QMessageBox.critical(self, "DZL", str(e))
            raise SystemExit(1)

    def _check_steam_binary(self):
        import shutil
        if not shutil.which("steam"):
            QMessageBox.warning(
                self, "DZL", "steam binary not found in PATH."
            )

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.tabs.addTab(self._tab_servers(), "Servers")
        self.tabs.addTab(self._tab_favorites(), "Favorites")
        self.tabs.addTab(self._tab_mods(), "Mods")
        self.tabs.addTab(self._tab_settings(), "Settings")

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")



    def _set_refresh_enabled(self, on):
        self.refresh_servers_btn.setEnabled(on)
        self.refresh_favs_btn.setEnabled(on)

    def _refresh_all(self, silent=False):
        self.status.showMessage("Downloading server list ...")
        self._set_refresh_enabled(False)
        cache = self.cache_dir / "servers_cache.json"
        self._run_worker(
            api.fetch_server_list, cache, 0,
            on_done=self._on_refreshed,
            on_error=lambda e: self._on_refresh_error(e, silent),
        )

    def _on_refreshed(self, servers):
        self._set_refresh_enabled(True)
        if self._last_query:
            self._on_servers(servers, self._last_query)
        else:
            self._on_index_servers(servers)
            self.status.showMessage("Server list updated.")

    def _on_refresh_error(self, msg, silent):
        self._set_refresh_enabled(True)
        self.status.showMessage("Server list download failed.")
        if not silent:
            QMessageBox.warning(self, "DZL", msg)

    def _on_index_servers(self, servers):
        self._build_server_index(servers)
        self._refresh_favorites()
        self._start_ping()

    def _ping_text(self, ip, qp):
        key = (ip, str(qp))
        if key not in self._pings:
            return "..."
        ms = self._pings[key]
        return f"{ms} ms" if ms is not None else "-"

    def _start_ping(self):
        targets = set()
        for s in self._server_results:
            targets.add((s["ip"], str(s["query_port"])))
        for f in self.favs.all():
            ip = f["ip_port"].partition(":")[0]
            targets.add((ip, str(f["query_port"])))
        self._pings = {}
        self._ping_gen += 1
        gen = self._ping_gen
        self._update_ping_cells()
        if not targets:
            return
        self._run_worker(
            api.ping_servers, sorted(targets),
            on_done=lambda r: self._on_pinged(gen, r),
            on_error=lambda e: None,
        )

    def _on_pinged(self, gen, res):
        if gen != self._ping_gen:
            return
        self._pings = dict(res)
        self._update_ping_cells()

    def _update_ping_cells(self):
        for t in (self.results_table, self.fav_table):
            for r in range(t.rowCount()):
                ipp = t.item(r, 3)
                qp = t.item(r, 4)
                if not ipp or not qp:
                    continue
                ip = ipp.text().partition(":")[0]
                t.setItem(
                    r, PING_COL,
                    QTableWidgetItem(self._ping_text(ip, qp.text())),
                )

    def _build_server_index(self, servers):
        idx = {}
        for s in servers:
            ip = (s.get("endpoint") or {}).get("ip", "")
            gp = s.get("gamePort", 2302)
            idx[f"{ip}:{gp}"] = s
        self._server_index = idx

    def _new_table(self):
        t = QTableWidget(0, 7)
        t.setHorizontalHeaderLabels(
            ["Name", "Players", "PW", "IP:GamePort", "QueryPort", "Ping",
             "Favorites"]
        )
        hh = t.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4, 5, 6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.setItemDelegateForColumn(STAR_COL, StarDelegate(t))
        t.setStyleSheet(self._table_style())
        t.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )
        t.horizontalHeader().setHighlightSections(False)
        t.verticalHeader().setHighlightSections(False)
        return t

    def _star_item(self, on):
        it = QTableWidgetItem("★")
        it.setTextAlignment(Qt.AlignCenter)
        it.setForeground(QColor(self.colors["star_on" if on else "star_off"]))
        f = it.font()
        f.setPointSize(16)
        it.setFont(f)
        return it

    def _fill_row(self, t, name, players, pw, ip_port, qport, on):
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(name))
        t.setItem(r, 1, QTableWidgetItem(players))
        t.setItem(r, 2, QTableWidgetItem(pw))
        t.setItem(r, 3, QTableWidgetItem(ip_port))
        t.setItem(r, 4, QTableWidgetItem(str(qport)))
        ip = ip_port.partition(":")[0]
        t.setItem(r, PING_COL, QTableWidgetItem(self._ping_text(ip, qport)))
        t.setItem(r, STAR_COL, self._star_item(on))

    def _tab_servers(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type server name ...")
        self.search_btn = QPushButton("Search")
        self.manual_btn = QPushButton("Manual Setup")
        self.search_btn.clicked.connect(self._do_search)
        self.manual_btn.clicked.connect(self._do_manual)
        self.search_edit.returnPressed.connect(self._do_search)
        top.addWidget(QLabel("Search:"))
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.search_btn)
        top.addWidget(self.manual_btn)
        lay.addLayout(top)

        self.results_table = self._new_table()
        self.results_table.doubleClicked.connect(self._server_double)
        self.results_table.cellClicked.connect(self._server_cell_clicked)
        self.results_table.customContextMenuRequested.connect(
            self._servers_menu
        )
        lay.addWidget(self.results_table, 1)

        btns = QHBoxLayout()
        self.join_btn = QPushButton("Join Selected Server")
        self.join_btn.clicked.connect(self._join_from_table)
        btns.addWidget(self.join_btn)
        self.mod_settings_btn = QPushButton("Mod Settings")
        self._make_mod_menu(self.mod_settings_btn, "servers")
        btns.addWidget(self.mod_settings_btn)
        btns.addStretch(1)
        self.refresh_servers_btn = QPushButton("Refresh")
        self.refresh_servers_btn.clicked.connect(
            lambda: self._refresh_all()
        )
        btns.addWidget(self.refresh_servers_btn)
        lay.addLayout(btns)

        self._server_results = []
        return w

    def _do_search(self):
        q = self.search_edit.text().strip()
        if not q:
            return
        self.status.showMessage("Downloading server list ...")
        self.search_btn.setEnabled(False)
        cache = self.cache_dir / "servers_cache.json"
        self._run_worker(
            api.fetch_server_list, cache, 0,
            on_done=lambda servers: self._on_servers(servers, q),
            on_error=self._on_search_error,
        )

    def _on_search_error(self, msg):
        self.search_btn.setEnabled(True)
        self.status.showMessage("Search failed.")
        QMessageBox.warning(self, "DZL", msg)

    def _on_servers(self, servers, q):
        self.search_btn.setEnabled(True)
        self._last_query = q
        self._build_server_index(servers)
        self._server_results = api.search_servers(servers, q)
        t = self.results_table
        t.setRowCount(0)
        for s in self._server_results:
            ip_port = f'{s["ip"]}:{s["game_port"]}'
            self._fill_row(
                t, s["name"],
                f'{s["players"]}/{s["max_players"]}',
                "P" if s["password"] else "-",
                ip_port, s["query_port"],
                self.favs.find(ip_port) >= 0,
            )
        self._refresh_favorites()
        self.status.showMessage(
            f"{len(self._server_results)} server(s) found for '{q}'"
        )
        self._start_ping()

    def _server_double(self, index):
        if index.column() == STAR_COL:
            return
        self._join_from_table()

    def _server_cell_clicked(self, row, col):
        if col == STAR_COL:
            self._toggle_fav_server(row)

    def _toggle_fav_server(self, row):
        if row < 0 or row >= len(self._server_results):
            return
        s = self._server_results[row]
        ip_port = f'{s["ip"]}:{s["game_port"]}'
        idx = self.favs.find(ip_port)
        if idx >= 0:
            self.favs.delete(idx)
            on = False
        else:
            self.favs.add(
                s["name"], [], ip_port, str(s["query_port"]),
                self._effective_username(),
            )
            on = True
        self.results_table.setItem(row, STAR_COL, self._star_item(on))
        self._refresh_favorites()

    def _servers_menu(self, pos):
        row = self.results_table.indexAt(pos).row()
        if row < 0 or row >= len(self._server_results):
            return
        self.results_table.selectRow(row)
        s = self._server_results[row]
        is_fav = self.favs.find(f'{s["ip"]}:{s["game_port"]}') >= 0
        menu = QMenu(self)
        a_join = menu.addAction("Join Server")
        a_fav = menu.addAction(
            "Remove from favorites" if is_fav else "Add to favorites"
        )
        chosen = menu.exec(
            self.results_table.viewport().mapToGlobal(pos)
        )
        if chosen == a_join:
            self._join_from_table()
        elif chosen == a_fav:
            self._toggle_fav_server(row)

    def _join_from_table(self):
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self._server_results):
            QMessageBox.information(self, "DZL", "Select a server first.")
            return
        s = self._server_results[row]
        self._begin_join(s["ip"], s["game_port"], s["query_port"], s["name"])

    def _server_mod_tool(self, mode):
        row = self.results_table.currentRow()
        if row < 0 or row >= len(self._server_results):
            QMessageBox.information(self, "DZL", "Select a server first.")
            return
        s = self._server_results[row]
        self._mod_tool_for(s["ip"], s["query_port"], mode)

    def _mod_tool_for(self, ip, query_port, mode):
        self.status.showMessage("Fetching mod list ...")
        self._run_worker(
            api.fetch_server_mods, ip, int(query_port),
            on_done=lambda r: self._apply_mod_tool(mode, r[0]),
        )

    def _apply_mod_tool(self, mode, mod_ids):
        if not mod_ids:
            QMessageBox.information(self, "DZL", "Vanilla server, no mods.")
            return
        label = "Verify" if mode == "verify" else "Remove"
        r = QMessageBox.question(
            self, label + " Mods",
            f"{label}: delete {len(mod_ids)} mod folder(s) used by this server?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        import shutil
        for mid in mod_ids:
            shutil.rmtree(self.mods_dir / mid, ignore_errors=True)
        if mode == "verify":
            steam.prepare_join(self.steamapps, self.game_dir)
        self._refresh_mods()
        self.status.showMessage(f"{len(mod_ids)} mod folder(s) deleted.")

    def _make_mod_menu(self, button, page):
        menu = QMenu(button)
        a_info = menu.addAction("Server Info")
        a_verify = menu.addAction("Verify Mods")
        a_remove = menu.addAction("Remove Mods Used By This Server")
        a_info.triggered.connect(
            lambda: self._mod_settings_action(page, "info")
        )
        a_verify.triggered.connect(
            lambda: self._mod_settings_action(page, "verify")
        )
        a_remove.triggered.connect(
            lambda: self._mod_settings_action(page, "remove")
        )
        button.setMenu(menu)

    def _mod_settings_target(self, page):
        if page == "servers":
            row = self.results_table.currentRow()
            if row < 0 or row >= len(self._server_results):
                QMessageBox.information(self, "DZL", "Select a server first.")
                return None
            s = self._server_results[row]
            return s["name"], s["ip"], str(s["game_port"]), str(s["query_port"])
        entry = self.favs.get(self._fav_selected())
        if entry is None:
            QMessageBox.information(self, "DZL", "Select a favorite first.")
            return None
        ip, _, gp = entry["ip_port"].partition(":")
        return entry["name"], ip, gp, str(entry["query_port"])

    def _mod_settings_action(self, page, action):
        target = self._mod_settings_target(page)
        if not target:
            return
        name, ip, gp, qp = target
        if action == "info":
            self.status.showMessage("Fetching server info ...")
            self._run_worker(
                api.fetch_server_mods_detailed, ip, int(qp),
                on_done=lambda ml: self._show_server_info(
                    name, ip, gp, qp, ml
                ),
            )
        else:
            self._mod_tool_for(ip, qp, action)

    def _show_server_info(self, name, ip, gp, qp, mod_list):
        info = self._server_index.get(f"{ip}:{gp}")
        if info:
            players = f'{info.get("players", 0)}/{info.get("maxPlayers", 0)}'
            pw = "Yes" if info.get("password") else "No"
        else:
            players = "?"
            pw = "?"
        head = (
            f"Server Name: {name or 'unknown'}\n"
            f"Game IP:Port: {ip}:{gp}\n"
            f"Query Port: {qp}\n"
            f"Players: {players}\n"
            f"Password: {pw}\n"
            f"Mods: {len(mod_list)}"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Server Info")
        dlg.resize(560, 520)
        lay = QVBoxLayout(dlg)
        label = QLabel(head)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(label)
        lst = QListWidget()
        lst.setStyleSheet(self._list_style())
        if not mod_list:
            lst.addItem("Vanilla server, no mods.")
        for m in mod_list:
            local = self.mods_dir / m["id"]
            installed = local.is_dir()
            title = m["name"] or (
                mods.read_mod_name(local) if installed else "Unknown name"
            )
            state = "installed" if installed else "not installed"
            lst.addItem(f'{title}  [{m["id"]}]  ({state})')
        lay.addWidget(lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    def _do_manual(self):
        dlg = ManualSetupDialog(self)
        if dlg.exec() == QDialog.Accepted:
            ip, gp, qp, name = dlg.values()
            self._begin_join(ip, gp, qp, name or "")

    def _begin_join(self, ip, game_port, query_port, server_name):
        self._pending_server = {
            "ip": ip,
            "game_port": str(game_port),
            "query_port": str(query_port),
            "server_name": server_name,
            "ip_port": f"{ip}:{game_port}",
        }
        username = self._effective_username()
        if not username:
            QMessageBox.information(
                self, "DZL", "Set a username in Settings first."
            )
            return
        self.status.showMessage(
            f"Fetching mod list from {ip}:{query_port} ..."
        )
        self._run_worker(
            api.fetch_server_mods, ip, int(query_port),
            on_done=self._on_server_mods,
        )

    def _on_server_mods(self, result):
        mod_ids, vanilla = result
        if vanilla:
            self._pending_mod_ids = []
            self.status.showMessage("This is a Vanilla Server.")
            self._do_join()
            return
        self._pending_mod_ids = mod_ids
        self.status.showMessage(
            f"{len(mod_ids)} server mod(s) identified. Preparing join ..."
        )
        self._do_join()

    def _do_join(self):
        try:
            steam.prepare_join(self.steamapps, self.game_dir)
        except Exception as e:
            QMessageBox.warning(self, "DZL", f"Cleanup failed: {e}")

        mod_ids = self._pending_mod_ids or []
        installed = [
            mid for mid in mod_ids if (self.mods_dir / mid).is_dir()
        ]
        if installed:
            self.status.showMessage("Checking for mod updates ...")
            self._run_worker(
                api.check_updates, installed, self.mods_dir,
                on_done=lambda out: self._after_update_check(out),
                on_error=lambda e: (
                    QMessageBox.warning(self, "DZL", "Update check failed"),
                    self._after_update_check(None),
                ),
            )
        else:
            self._after_update_check(None)

    def _after_update_check(self, outdated):
        if outdated:
            names = []
            for mid in outdated:
                m = self.mods_dir / mid
                names.append(mods.read_mod_name(m) if m.is_dir() else mid)
            text = (
                "Mod updates available:\n\n" +
                "\n".join(f"  • {n}" for n in names) +
                "\n\nUpdate now? (The mods will be re-downloaded.)"
            )
            r = QMessageBox.question(
                self, "DZL", text,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if r == QMessageBox.Yes:
                for mid in outdated:
                    import shutil
                    shutil.rmtree(self.mods_dir / mid, ignore_errors=True)
                acf = steam.acf_path(self.steamapps)
                acf.unlink(missing_ok=True)

        mod_ids = self._pending_mod_ids or []
        missing = [mid for mid in mod_ids if not (self.mods_dir / mid).is_dir()]
        if not missing:
            self._finalize_join()
            return

        self._download_queue = list(missing)
        self._download_next()

    def _download_next(self):
        if not self._download_queue:
            self._wait_for_downloads()
            return
        mid = self._download_queue.pop(0)
        self.status.showMessage(f"Downloading mod {mid} ...")
        self._run_worker(
            steam.download_mod, mid, self.steamapps,
            on_done=lambda _: self._download_next(),
            on_error=lambda e: self._download_next(),
        )

    def _wait_for_downloads(self):
        self._wait_for_acf(self._finalize_join)

    def _wait_for_acf(self, on_finish):
        acf = steam.acf_path(self.steamapps)
        old = getattr(self, "_poll_timer", None)
        if old is not None:
            old.stop()
        self._wait_ticks = 0
        dlg = QProgressDialog(
            "Waiting for Steam downloads to finish ...", "Cancel", 0, 0, self
        )
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        timer = QTimer(self)
        timer.setInterval(2000)
        self._poll_timer = timer

        def tick():
            self._wait_ticks += 1
            if dlg.wasCanceled():
                timer.stop()
                self.status.showMessage("Download wait cancelled.")
                return
            if self._wait_ticks > 900:
                timer.stop()
                dlg.close()
                QMessageBox.warning(self, "DZL", "Download timed out.")
                return
            if steam.acf_needs_download(acf):
                return
            timer.stop()
            dlg.close()
            on_finish()

        timer.timeout.connect(tick)
        timer.start()
        dlg.show()
        self.status.showMessage("Waiting for Steam downloads to finish ...")

    def _finalize_join(self):
        mod_ids = self._pending_mod_ids or []
        for mid in mod_ids:
            steam.link_mod(self.game_dir, self.mods_dir, mid)

        s = self._pending_server
        username = self._effective_username()
        folder_names = [steam.mod_link_name(m) for m in mod_ids]
        info = self._server_index.get(s["ip_port"])
        players = (
            f'{info.get("players", 0)}/{info.get("maxPlayers", 0)}'
            if info else "?"
        )

        info = self._server_index.get(s["ip_port"])
        players = (
            f'{info.get("players", 0)}/{info.get("maxPlayers", 0)}'
            if info else "?"
        )

        text = (
            f"Server Name: {s['server_name'] or 'unknown'}\n"
            f"Username: {username}\n"
            f"Game IP:Port: {s['ip_port']}\n"
            f"Query Port: {s['query_port']}\n"
            f"Players: {players}\n"
            f"Mods: {len(folder_names)}"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("")
        lay = QVBoxLayout(dlg)
        row = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.SP_DialogApplyButton).pixmap(48, 48)
        )
        row.addWidget(icon, 0, Qt.AlignTop)
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(label, 1)
        lay.addLayout(row)
        btns = QHBoxLayout()
        btns.addStretch(1)
        join_btn = QPushButton("Join Server")
        cancel_btn = QPushButton("Cancel")
        join_btn.setDefault(True)
        join_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(join_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)
        if dlg.exec() != QDialog.Accepted:
            self.status.showMessage("Join cancelled.")
            return

        try:
            steam.launch_dayz(
                self.steamapps, folder_names,
                s["ip_port"], s["query_port"], username,
            )
            self.status.showMessage("DayZ launched.")
        except Exception as e:
            QMessageBox.critical(self, "DZL", f"Launch failed: {e}")

    def _tab_favorites(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        self.fav_table = self._new_table()
        self.fav_table.doubleClicked.connect(self._fav_double)
        self.fav_table.cellClicked.connect(self._fav_cell_clicked)
        self.fav_table.customContextMenuRequested.connect(self._fav_menu)
        lay.addWidget(self.fav_table, 1)

        btns = QHBoxLayout()
        self.fav_join = QPushButton("Join")
        self.fav_verify = QPushButton("Mod Settings")
        self._make_mod_menu(self.fav_verify, "favorites")
        self.fav_edit = QPushButton("Edit")
        self.fav_rename = QPushButton("Rename")
        self.fav_delete = QPushButton("Delete")
        self.fav_join.clicked.connect(lambda: self._fav_action(None))
        self.fav_edit.clicked.connect(self._fav_edit)
        self.fav_rename.clicked.connect(self._fav_rename)
        self.fav_delete.clicked.connect(self._fav_delete)
        for b in (self.fav_join, self.fav_verify, self.fav_edit,
                  self.fav_rename, self.fav_delete):
            btns.addWidget(b)
        btns.addStretch(1)
        self.refresh_favs_btn = QPushButton("Refresh")
        self.refresh_favs_btn.clicked.connect(lambda: self._refresh_all())
        btns.addWidget(self.refresh_favs_btn)
        lay.addLayout(btns)

        self._refresh_favorites()
        return w

    def _refresh_favorites(self):
        t = self.fav_table
        t.setRowCount(0)
        for f in self.favs.all():
            s = self._server_index.get(f["ip_port"])
            if s:
                players = f'{s.get("players", 0)}/{s.get("maxPlayers", 0)}'
                pw = "P" if s.get("password") else "-"
            else:
                players = "?"
                pw = "?"
            self._fill_row(
                t, f["name"], players, pw,
                f["ip_port"], f["query_port"], True,
            )

    def _fav_selected(self):
        return self.fav_table.currentRow()

    def _fav_double(self, index):
        if index.column() == STAR_COL:
            return
        self._fav_action(None)

    def _fav_cell_clicked(self, row, col):
        if col == STAR_COL:
            self._fav_remove(row)

    def _fav_remove(self, row):
        if self.favs.get(row) is None:
            return
        self.favs.delete(row)
        self._refresh_favorites()
        self._sync_server_stars()

    def _sync_server_stars(self):
        t = self.results_table
        for r, s in enumerate(self._server_results):
            on = self.favs.find(f'{s["ip"]}:{s["game_port"]}') >= 0
            t.setItem(r, STAR_COL, self._star_item(on))

    def _fav_menu(self, pos):
        row = self.fav_table.indexAt(pos).row()
        if self.favs.get(row) is None:
            return
        self.fav_table.selectRow(row)
        menu = QMenu(self)
        a_join = menu.addAction("Join Server")
        a_rem = menu.addAction("Remove from favorites")
        chosen = menu.exec(self.fav_table.viewport().mapToGlobal(pos))
        if chosen == a_join:
            self._fav_action(None)
        elif chosen == a_rem:
            self._fav_remove(row)

    def _fav_action(self, _):
        idx = self._fav_selected()
        if idx < 0:
            return
        entry = self.favs.get(idx)
        if not entry:
            return
        ip_port = entry["ip_port"]
        ip, _, gp = ip_port.partition(":")
        self._begin_join(ip, gp, entry["query_port"], entry["name"])

    def _fav_verify(self):
        idx = self._fav_selected()
        if idx < 0:
            QMessageBox.information(self, "DZL", "Select a favorite first.")
            return
        entry = self.favs.get(idx)
        if not entry:
            return
        ip, _, gp = entry["ip_port"].partition(":")
        self._mod_tool_for(ip, entry["query_port"], "verify")

    def _fav_edit(self):
        idx = self._fav_selected()
        if idx < 0:
            return
        entry = self.favs.get(idx)
        ip_port, ok = QInputDialog.getText(
            self, "Edit Favorite", "IP:GamePort:", text=entry["ip_port"]
        )
        ip_port = ip_port.strip()
        if not ok or not ip_port:
            return
        if ":" not in ip_port:
            ip_port += ":2302"
        qp, ok = QInputDialog.getText(
            self, "Edit Favorite", "Query Port:", text=entry["query_port"]
        )
        qp = qp.strip()
        if not ok or not qp.isdigit():
            return
        self.favs.update(idx, ip_port, qp)
        self._refresh_favorites()
        self._sync_server_stars()

    def _fav_rename(self):
        idx = self._fav_selected()
        if idx < 0:
            return
        entry = self.favs.get(idx)
        new, ok = QInputDialog.getText(
            self, "Rename Favorite", "New name:", text=entry["name"]
        )
        if ok and new.strip():
            self.favs.rename(idx, new.strip())
            self._refresh_favorites()

    def _fav_delete(self):
        idx = self._fav_selected()
        if idx < 0:
            return
        entry = self.favs.get(idx)
        r = QMessageBox.question(
            self, "Delete Favorite",
            f"Delete '{entry['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            self.favs.delete(idx)
            self._refresh_favorites()
            self._sync_server_stars()

    def _tab_mods(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(
            ["Name", "Mod Size", "Last Updated", "Workshop ID"]
        )
        hh = t.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setStyleSheet(self._table_style())
        t.doubleClicked.connect(lambda _: self._mod_info())
        t.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )
        t.horizontalHeader().setHighlightSections(False)
        t.verticalHeader().setHighlightSections(False)
        self.mod_table = t
        lay.addWidget(t, 1)

        btns = QHBoxLayout()
        self.mod_update = QPushButton("Update")
        self.mod_delete = QPushButton("Delete")
        self.mod_info_btn = QPushButton("Info")
        self.mod_check_all = QPushButton("Check All For Updates")
        self.mod_delete_all = QPushButton("Delete All Mods")
        self.mod_update.clicked.connect(self._mod_update)
        self.mod_delete.clicked.connect(self._mod_delete)
        self.mod_info_btn.clicked.connect(self._mod_info)
        self.mod_check_all.clicked.connect(self._mod_check_all)
        self.mod_delete_all.clicked.connect(self._mod_delete_all)
        for b in (self.mod_update, self.mod_delete, self.mod_info_btn,
                  self.mod_check_all, self.mod_delete_all):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        self._refresh_mods()
        return w

    def _refresh_mods(self):
        self._mod_data = mods.list_mods(self.mods_dir)
        t = self.mod_table
        t.setRowCount(0)
        for m in self._mod_data:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(m["name"]))
            t.setItem(r, 1, QTableWidgetItem("..."))
            t.setItem(r, 2, QTableWidgetItem("..."))
            t.setItem(r, 3, QTableWidgetItem(m["id"]))
        self._mod_gen = getattr(self, "_mod_gen", 0) + 1
        gen = self._mod_gen
        paths = [m["path"] for m in self._mod_data]
        self._run_worker(
            _mod_stats, paths,
            on_done=lambda res: self._fill_mod_stats(gen, res),
            on_error=lambda e: None,
        )

    def _fill_mod_stats(self, gen, res):
        if gen != self._mod_gen:
            return
        t = self.mod_table
        for r, (size, date) in enumerate(res):
            if r < t.rowCount():
                t.setItem(r, 1, QTableWidgetItem(size))
                t.setItem(r, 2, QTableWidgetItem(date))

    def _mod_selected(self):
        idx = self.mod_table.currentRow()
        if 0 <= idx < len(self._mod_data):
            return self._mod_data[idx]
        return None

    def _mod_update(self):
        m = self._mod_selected()
        if not m:
            return
        self.status.showMessage(f"Updating {m['name']} ...")
        self._run_worker(
            api.check_updates, [m["id"]], self.mods_dir,
            on_done=lambda out: self._mod_update_result(m, out),
        )

    def _mod_update_result(self, m, outdated):
        if not outdated:
            QMessageBox.information(
                self, "DZL", f"{m['name']} is already up to date."
            )
            return
        import shutil
        shutil.rmtree(m["path"], ignore_errors=True)
        steam.acf_path(self.steamapps).unlink(missing_ok=True)
        self.status.showMessage(f"Downloading {m['name']} ...")
        self._run_worker(
            steam.download_mod, m["id"], self.steamapps,
            on_done=lambda _: self._wait_for_single_download(),
        )

    def _wait_for_single_download(self):
        self._wait_for_acf(self._single_done)

    def _single_done(self):
        self._refresh_mods()
        self.status.showMessage("Mod updated.")

    def _mod_delete(self):
        m = self._mod_selected()
        if not m:
            return
        r = QMessageBox.question(
            self, "Delete Mod", f"Delete '{m['name']}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r == QMessageBox.Yes:
            import shutil
            shutil.rmtree(m["path"], ignore_errors=True)
            self._refresh_mods()

    def _mod_info(self):
        m = self._mod_selected()
        if not m:
            return
        self.status.showMessage("Fetching workshop info ...")
        self._run_worker(
            api.fetch_workshop_info, m["id"],
            on_done=lambda info: self._show_mod_info(m, info),
        )

    def _show_mod_info(self, m, info):
        import datetime
        path = m["path"]
        size = mods.human_size(mods.dir_size(path))
        newest = mods.newest_mtime(path)
        author = mods.read_mod_author(path)
        lines = [
            f"Name:         {m['name']}",
            f"Workshop ID:  {m['id']}",
            f"URL:          https://steamcommunity.com/sharedfiles/filedetails/?id={m['id']}",
        ]
        if author:
            lines.append(f"Author:       {author}")
        lines.append(f"Size on disk: {size}")
        if newest:
            lines.append(
                "Local files:  " +
                datetime.datetime.fromtimestamp(newest).strftime(
                    "%Y-%m-%d %H:%M"
                )
            )
        if info:
            lines.append(
                "Steam updated: " +
                datetime.datetime.fromtimestamp(
                    info["time_updated"]
                ).strftime("%Y-%m-%d %H:%M")
            )
            lines.append(
                "Steam created: " +
                datetime.datetime.fromtimestamp(
                    info["time_created"]
                ).strftime("%Y-%m-%d %H:%M")
            )
            lines.append(f"Subscribers:  {info['subscriptions']}")
            status = (
                "Up to date"
                if newest > info["time_updated"]
                else "Update available"
            )
            lines.append(f"Status:       {status}")
        else:
            lines.append("Steam info unavailable.")
        QMessageBox.information(self, f"Mod Info — {m['name']}", "\n".join(lines))

    def _mod_check_all(self):
        if not self._mod_data:
            QMessageBox.information(self, "DZL", "No mods installed.")
            return
        ids = [m["id"] for m in self._mod_data]
        self.status.showMessage("Checking all mods for updates ...")
        self._run_worker(
            api.check_updates, ids, self.mods_dir,
            on_done=self._check_all_result,
            on_error=lambda e: QMessageBox.warning(
                self, "DZL", f"Update check failed: {e}"
            ),
        )

    def _check_all_result(self, outdated):
        if not outdated:
            QMessageBox.information(
                self, "DZL", "All mods are up to date."
            )
            return
        names = []
        for mid in outdated:
            m = self.mods_dir / mid
            names.append(mods.read_mod_name(m) if m.is_dir() else mid)
        text = (
            f"{len(outdated)} mod(s) have updates:\n\n" +
            "\n".join(f"  • {n}" for n in names) +
            "\n\nDelete them now? They will re-download on next join."
        )
        r = QMessageBox.question(
            self, "DZL", text, QMessageBox.Yes | QMessageBox.No
        )
        if r == QMessageBox.Yes:
            import shutil
            for mid in outdated:
                shutil.rmtree(self.mods_dir / mid, ignore_errors=True)
            self._refresh_mods()
            self.status.showMessage(
                f"Deleted {len(outdated)} outdated mod(s)."
            )

    def _mod_delete_all(self):
        r = QMessageBox.question(
            self, "Delete All Mods",
            "Delete ALL DayZ mods?\n\n"
            "This removes the mods directory, downloads directory, "
            "and all @* symlinks in the game folder.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        mods.delete_all_mods(
            self.mods_dir, self.downloads_dir, self.game_dir
        )
        self._refresh_mods()
        self.status.showMessage("All mods deleted.")
    def _tab_settings(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        sub = QTabWidget()
        outer.addWidget(sub)
        sub.addTab(self._settings_general(), "Username")
        sub.addTab(self._settings_appearance(), "Appearance")
        sub.addTab(self._settings_storage(), "Storage")
        return w

    def _settings_general(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Username")
        form = QFormLayout(g)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "Leave empty to clear (spaces become underscores)"
        )
        self.save_btn = QPushButton("Save Username")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_username)
        self.username_edit.textEdited.connect(
            lambda _: self.save_btn.setEnabled(True)
        )
        form.addRow("Username:", self.username_edit)
        form.addRow("", self.save_btn)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _settings_storage(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox("Storage")
        v = QVBoxLayout(g)
        info = QLabel(
            "Steam apps directory:\n" +
            (str(self.steamapps) if self.steamapps else "not found") +
            "\n\nConfig:\n" + str(self.config_dir) +
            "\n\nCache:\n" + str(self.cache_dir)
        )
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(info)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _settings_appearance(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(self._appearance_page())
        return scroll

    def _appearance_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        names = {k: label for k, label, _ in COLOR_ITEMS}
        self._color_btns = {}
        for title, keys in COLOR_GROUPS:
            g = QGroupBox(title)
            form = QFormLayout(g)
            for key in keys:
                btn = QPushButton()
                btn.clicked.connect(
                    lambda _=False, k=key: self._pick_color(k)
                )
                reset = QPushButton("Reset")
                reset.clicked.connect(
                    lambda _=False, k=key: self._reset_color(k)
                )
                row = QHBoxLayout()
                row.addWidget(btn, 1)
                row.addWidget(reset)
                form.addRow(names[key] + ":", row)
                self._color_btns[key] = btn
                self._paint_color_btn(key)
            lay.addWidget(g)
        self.bold_check = QCheckBox("Bold text")
        self.bold_check.setChecked(self.bold)
        self.bold_check.toggled.connect(self._toggle_bold)
        lay.addWidget(self.bold_check)
        lay.addStretch(1)
        return w

    def _toggle_bold(self, on):
        self.bold = on
        self._save_colors()
        self._apply_colors()

    def _paint_color_btn(self, key):
        val = self.colors[key]
        btn = self._color_btns[key]
        if val:
            fg = "#000000" if QColor(val).lightness() > 128 else "#ffffff"
            btn.setText(val)
            btn.setStyleSheet(f"background-color: {val}; color: {fg};")
        else:
            btn.setText("Theme default")
            btn.setStyleSheet("")

    def _pick_color(self, key):
        start = QColor(self.colors[key] or "#ffffff")
        c = QColorDialog.getColor(start, self, "Choose color")
        if not c.isValid():
            return
        self.colors[key] = c.name()
        self._color_changed(key)

    def _reset_color(self, key):
        default = next(d for k, _, d in COLOR_ITEMS if k == key)
        self.colors[key] = default
        self._color_changed(key)

    def _color_changed(self, key):
        self._save_colors()
        self._paint_color_btn(key)
        self._apply_colors()

    def _load_colors(self):
        import json
        self._default_palette = QApplication.palette()
        self._default_font = QFont(QApplication.font())
        self.bold = False
        self._colors_path = self.config_dir / "colors.json"
        self.colors = {k: d for k, _, d in COLOR_ITEMS}
        try:
            saved = json.loads(self._colors_path.read_text())
            self.bold = bool(saved.get("bold_text", False))
            for k, v in saved.items():
                if k in self.colors and v and QColor(v).isValid():
                    self.colors[k] = v
        except Exception:
            pass
        self._apply_palette()

    def _save_colors(self):
        import json
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = dict(self.colors)
        data["bold_text"] = self.bold
        self._colors_path.write_text(json.dumps(data, indent=2))

    def _apply_palette(self):
        pal = QPalette(self._default_palette)
        c = self.colors
        if c["text"]:
            for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
                pal.setColor(role, QColor(c["text"]))
        if c["background"]:
            for role in (QPalette.Window, QPalette.Base):
                pal.setColor(role, QColor(c["background"]))

        if c["accent"]:
            pal.setColor(QPalette.Highlight, QColor(c["accent"]))
            if hasattr(QPalette, "Accent"):
                pal.setColor(QPalette.Accent, QColor(c["accent"]))
        QApplication.setPalette(pal)
        f = QFont(self._default_font)
        f.setBold(self.bold)
        QApplication.setFont(f)
        QApplication.instance().setStyleSheet(self._global_style())

    def _global_style(self):
        c = self.colors
        parts = []
        if self.bold:
            parts.append("* { font-weight: bold; }")
        if c["button_bg"] or c["button_hover"]:
            bg = c["button_bg"] or "palette(button)"
            parts.append(
                f"QPushButton {{ background-color: {bg};"
                " border: 1px solid palette(mid); border-radius: 3px;"
                " padding: 5px 12px; }"
            )
            if c["button_hover"]:
                parts.append(
                    "QPushButton:hover { background-color: "
                    f"{c['button_hover']}; }}"
                )
            parts.append(
                "QPushButton:pressed { background-color: palette(mid); }"
            )
            parts.append("QPushButton:disabled { color: palette(mid); }")
            if c["accent"]:
                parts.append(
                    f"QPushButton:focus {{ border: 1px solid {c['accent']}; }}"
                )
        if c["tab_bar"] or c["tab_selected"] or c["accent"]:
            bar = c["tab_bar"] or "palette(window)"
            sel = c["tab_selected"] or "palette(base)"
            parts.append(
                f"QTabBar::tab {{ background-color: {bar};"
                " border: 1px solid palette(mid); border-bottom: none;"
                " padding: 6px 14px; }"
            )
            acc = (
                f" border-top: 2px solid {c['accent']};"
                if c["accent"] else ""
            )
            parts.append(
                f"QTabBar::tab:selected {{ background-color: {sel};{acc} }}"
            )
        if c["header_bg"]:
            parts.append(
                f"QHeaderView::section {{ background-color: {c['header_bg']};"
                " border: 1px solid palette(mid); padding: 4px; }"
            )
            parts.append(
                f"QTableCornerButton::section {{ background-color: {c['header_bg']}; }}"
            )
        return "".join(parts)

    def _table_style(self):
        sel = self.colors["selected_row"]
        txt = self.colors["selected_text"]
        color = f" color: {txt};" if txt else ""
        rule = f"background-color: {sel};{color}"
        hov = self.colors["hover"] or "transparent"
        bor = self.colors["accent"] or "palette(mid)"
        hdr = self.colors["header_bg"] or "palette(window)"
        return (
            f"QTableWidget {{ border: 1px solid {bor}; outline: 0; }}"
            f"QHeaderView::section {{ background-color: {hdr};"
            " border: 1px solid palette(mid); padding: 4px; }"
            f"QHeaderView::section:hover {{ background-color: {hdr}; }}"
            f"QHeaderView::section:pressed {{ background-color: {hdr}; }}"
            f"QTableWidget::item:hover:!selected {{ background-color: {hov}; }}"
            f"QTableWidget::item:selected {{ {rule} }}"
            f"QTableWidget::item:selected:hover {{ {rule} }}"
            f"QTableWidget::item:selected:!active {{ {rule} }}"
        )

    def _list_style(self):
        sel = self.colors["selected_row"]
        hov = self.colors["hover"]
        txt = self.colors["selected_text"]
        color = f" color: {txt};" if txt else ""
        bor = self.colors["accent"] or "palette(mid)"
        parts = [f"QListWidget {{ border: 1px solid {bor}; outline: 0; }}"]
        if hov:
            parts.append(
                f"QListWidget::item:hover:!selected {{ background-color: {hov}; }}"
            )
        if sel:
            rule = f"background-color: {sel};{color}"
            parts.append(f"QListWidget::item:selected {{ {rule} }}")
            parts.append(f"QListWidget::item:selected:hover {{ {rule} }}")
            parts.append(f"QListWidget::item:selected:!active {{ {rule} }}")
        return "".join(parts)

    def _apply_colors(self):
        self._apply_palette()
        style = self._table_style()
        self.results_table.setStyleSheet(style)
        self.fav_table.setStyleSheet(style)
        self.mod_table.setStyleSheet(style)
        self._refresh_favorites()
        self._sync_server_stars()

    def _load_username(self):
        f = self.config_dir / "username.conf"
        if f.is_file():
            self.username_edit.setText(f.read_text().strip())

    def _save_username(self):
        raw = self.username_edit.text().strip()
        name = raw.replace(" ", "_")
        f = self.config_dir / "username.conf"
        if name:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            f.write_text(name + "\n")
        else:
            f.unlink(missing_ok=True)
        self.status.showMessage(
            f"Username saved: {name}" if name else "Username cleared."
        )
        self.save_btn.setEnabled(False)

    def _effective_username(self):
        f = self.config_dir / "username.conf"
        if f.is_file():
            return f.read_text().strip()
        return ""

    def _run_worker(self, fn, *args, on_done=None, on_error=None):
        w = Worker(fn, *args)
        self._workers.append(w)
        self._worker = w
        w.done.connect(
            lambda r: (on_done(r) if on_done else None),
            Qt.QueuedConnection,
        )
        w.error.connect(
            lambda e: (
                on_error(e) if on_error
                else QMessageBox.warning(self, "DZL", e)
            ),
            Qt.QueuedConnection,
        )
        def _cleanup():
            try:
                self._workers.remove(w)
            except ValueError:
                pass
        w.finished.connect(_cleanup)
        w.start()

    def closeEvent(self, event):
        for w in list(self._workers):
            w.quit()
            w.wait(2000)
        event.accept()


class ManualSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Server Setup")
        form = QFormLayout(self)

        self.ip = QLineEdit()
        self.ip.setPlaceholderText("1.2.3.4:2302")
        self.qport = QLineEdit()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Optional server label")

        hint = QLabel(
            '<a href="https://www.battlemetrics.com/servers/dayz/">'
            'Find server info at BattleMetrics</a>'
        )
        hint.setOpenExternalLinks(True)
        hint.setAlignment(Qt.AlignCenter)

        form.addRow("IP:GamePort", self.ip)
        form.addRow("Query Port", self.qport)
        form.addRow("Server Label", self.name)
        form.addRow(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _validate(self):
        addr = self.ip.text().strip()
        if not addr:
            QMessageBox.warning(self, "DZL", "IP:GamePort is required.")
            return
        if ":" not in addr:
            addr += ":2302"
        try:
            qp = int(self.qport.text().strip())
        except ValueError:
            QMessageBox.warning(self, "DZL", "Query port must be a number.")
            return
        self.accept()

    def values(self):
        addr = self.ip.text().strip()
        if ":" not in addr:
            addr += ":2302"
        ip, _, gp = addr.partition(":")
        qp = int(self.qport.text().strip())
        return ip, gp, qp, self.name.text().strip()
