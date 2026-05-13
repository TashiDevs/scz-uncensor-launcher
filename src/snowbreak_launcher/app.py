from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
    QAbstractButton,
    QWidget,
)

from .config import append_log, install_to_state, load_env_file, load_state, log_path, save_state, state_to_install
from .constants import APP_NAME, GITHUB_RELEASE_PAGE
from .detection import auto_detect_install, resolve_manual_install, validate_ix_folder
from .github_client import fetch_latest_release
from .installer import setup_or_update, static_asset_status, uncensor_file_status, uninstall_all_managed_files
from .launcher import launch_game
from .localization import is_localization_enabled
from .models import GitHubRelease, InstallInfo, LauncherState
from .progress import OperationCancelled, ProgressEvent
from .static_assets import import_static_zip
from .update_logic import UpdateDecision, decide_next_state


WINDOW_SIZE = (900, 560)


class GlassButton(QAbstractButton):
    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
        *,
        large: bool = False,
        width: int = 120,
        height: int = 32,
    ) -> None:
        super().__init__(parent)
        self._large = large
        self.setText(text)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        radius = 27 if self._large else 14

        if self.isDown():
            fill = QColor(38, 88, 122, 205)
        elif self.underMouse() and self.isEnabled():
            fill = QColor(29, 71, 101, 190)
        elif self.isEnabled():
            fill = QColor(11, 38, 61, 178)
        else:
            fill = QColor(11, 38, 61, 95)

        shadow = QColor(0, 10, 18, 95 if self._large else 50)
        shadow_rect = rect.translated(0, 5 if self._large else 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(shadow_rect, radius, radius)

        painter.setBrush(fill)
        painter.setPen(QPen(QColor(175, 238, 255, 220), 1.2))
        painter.drawRoundedRect(rect, radius, radius)

        font = QFont("Segoe UI", 23 if self._large else 9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(238, 251, 255, 245 if self.isEnabled() else 140))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


class StatusChip(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._kind = "idle"
        self.setFixedSize(126, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_status(self, text: str, kind: str) -> None:
        self._text = text
        self._kind = kind
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self._kind == "ok":
            border = QColor(154, 230, 245, 190)
            text = QColor(237, 252, 255)
        elif self._kind == "pending":
            border = QColor(210, 224, 232, 135)
            text = QColor(226, 241, 247)
        elif self._kind == "warn":
            border = QColor(235, 210, 142, 170)
            text = QColor(255, 241, 201)
        elif self._kind == "error":
            border = QColor(244, 145, 145, 170)
            text = QColor(255, 225, 225)
        else:
            border = QColor(116, 165, 188, 130)
            text = QColor(188, 219, 232)

        painter.setPen(QPen(border, 1.1))
        painter.setBrush(QColor(7, 30, 48, 150))
        painter.drawRoundedRect(rect, 10, 10)
        text_rect = rect.adjusted(8, 0, -8, 0)
        font = _fitted_font(self._text, "Segoe UI", 9, QFont.Weight.DemiBold, int(text_rect.width()), min_size=7)
        painter.setFont(font)
        painter.setPen(text)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, _elided_text(font, self._text, int(text_rect.width())))


class GlassLabel(QWidget):
    def __init__(self, parent: QWidget | None = None, width: int = 230, height: int = 30, max_width: int = 440) -> None:
        super().__init__(parent)
        self._text = ""
        self._min_width = width
        self._max_width = max_width
        self._center_x: int | None = None
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_center_x(self, center_x: int) -> None:
        self._center_x = center_x
        self._center_on_anchor()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt-style compatibility
        self._text = text
        self._resize_to_text()
        self.update()

    def _resize_to_text(self) -> None:
        font = QFont("Segoe UI", 9)
        desired = QFontMetrics(font).horizontalAdvance(self._text) + 40
        width = max(self._min_width, min(self._max_width, desired))
        if width != self.width():
            self.setFixedWidth(width)
            self._center_on_anchor()

    def _center_on_anchor(self) -> None:
        if self._center_x is not None:
            self.move(self._center_x - self.width() // 2, self.y())

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 12, 22, 168))
        painter.drawRoundedRect(rect, 13, 13)
        text_rect = rect.adjusted(14, 0, -14, 0)
        font = _fitted_font(self._text, "Segoe UI", 9, QFont.Weight.Normal, int(text_rect.width()), min_size=8)
        painter.setFont(font)
        painter.setPen(QColor(235, 251, 255))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, _elided_text(font, self._text, int(text_rect.width())))


class AutoUpdatePill(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(268, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt-style compatibility
        self._checked = checked
        self.update()

    def isChecked(self) -> bool:  # noqa: N802 - Qt-style compatibility
        return self._checked

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 12, 22, 168))
        painter.drawRoundedRect(rect, 13, 13)

        box = QRectF(13, 8, 18, 18)
        painter.setPen(QPen(QColor(177, 238, 255), 2))
        painter.setBrush(QColor(177, 238, 255, 220) if self._checked else QColor(0, 0, 0, 0))
        painter.drawRoundedRect(box, 5, 5)
        if self._checked:
            painter.setPen(QPen(QColor(4, 27, 40), 2.2))
            painter.drawLine(QPointF(17, 17), QPointF(21, 21))
            painter.drawLine(QPointF(21, 21), QPointF(28, 12))

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(235, 251, 255))
        painter.drawText(QRectF(40, 0, self.width() - 48, self.height()), Qt.AlignmentFlag.AlignVCenter, "Automatically update next time")


class WorkerSignals(QObject):
    progress = Signal(object)
    checks_done = Signal(object, object)
    setup_done = Signal(str)
    cancelled = Signal(str)
    error = Signal(str)


class SnowbreakLauncherApp(QWidget):
    def __init__(self) -> None:
        super().__init__()
        load_env_file(Path.cwd())

        self.setWindowTitle(APP_NAME)
        self.setFixedSize(*WINDOW_SIZE)
        self.setWindowIcon(QIcon(str(_asset_path("images", "app-icon.ico"))))
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.state_data: LauncherState = load_state()
        self.install: InstallInfo | None = state_to_install(self.state_data)
        self.latest_release: GitHubRelease | None = None
        self.decision: UpdateDecision | None = None
        self.ui_state = "disclaimer" if not self._notice_accepted() else "checking"
        self.busy = False
        self.cancel_requested = False
        self.top_title = "Ready"
        self.top_detail = "Done."
        self.top_progress_value = 0.0
        self.core_files_installed = False
        self.static_assets_installed = False
        self.present_static_assets: list[str] = []
        self.local_install_complete = False
        self._background = _load_background_pixmap()
        self._signals = WorkerSignals()
        self._signals.progress.connect(self._apply_progress)
        self._signals.checks_done.connect(self._finish_checks)
        self._signals.setup_done.connect(self._setup_done)
        self._signals.cancelled.connect(self._cancelled)
        self._signals.error.connect(self._show_error)

        self._build_controls()
        self._render()
        if self.ui_state == "checking":
            QTimer.singleShot(250, self._start_checks)

    def _build_controls(self) -> None:
        self.chips: dict[str, StatusChip] = {}
        for index, key in enumerate(("Game", "Switch", "Core", "Assets")):
            chip = StatusChip(self)
            chip.move(368 + index * 130, 45)
            self.chips[key] = chip

        self.main_button = GlassButton("Install", self, large=True, width=504, height=76)
        self.main_button.move(198, 252)
        self.main_button.clicked.connect(self._main_action)

        self.status_label = GlassLabel(self, width=268, height=30, max_width=440)
        self.status_label.move(316, 356)
        self.status_label.set_center_x(450)

        self.auto_update_pill = AutoUpdatePill(self)
        self.auto_update_pill.move(316, 398)
        self.auto_update_pill.setChecked(bool(self.state_data.auto_update_enabled))
        self.auto_update_pill.toggled.connect(self._auto_update_changed)

        self.cancel_button = GlassButton("Cancel", self, width=112, height=30)
        self.cancel_button.move(394, 438)
        self.cancel_button.clicked.connect(self._cancel_action)

        self.uninstall_button = GlassButton("Uninstall", self, width=92, height=30)
        self.uninstall_button.move(14, 544 - 30)
        self.uninstall_button.clicked.connect(self._uninstall)

        self.log_button = GlassButton("Open log", self, width=88, height=30)
        self.log_button.move(116, 544 - 30)
        self.log_button.clicked.connect(self._view_log)

        self.import_button = GlassButton("Import ZIP", self, width=96, height=30)
        self.import_button.move(214, 544 - 30)
        self.import_button.clicked.connect(self._import_static_zip)

    def _render(self) -> None:
        for name, (kind, text) in self._current_checklist().items():
            self.chips[name].set_status(text, kind)

        show_installed_controls = self.local_install_complete and self.ui_state not in {"checking", "installing", "updating", "disclaimer"}
        self._set_footer_visibility(installed=show_installed_controls, show_error_tools=self.ui_state == "error")
        self.auto_update_pill.setVisible(show_installed_controls and self.ui_state == "ready_to_update")
        self.cancel_button.setVisible(self.ui_state in {"installing", "updating"})

        if self.ui_state == "disclaimer":
            self._set_top_state("Before we start", "This tool only changes localization.txt and the ~ix mod folder. Use it at your own risk.", 0.0)
            self.status_label.setText("Ready when you are.")
            self.main_button.setText("I Understand")
            self.main_button.setEnabled(True)
        elif self.ui_state == "checking":
            self._set_top_state("Checking", "Checking Snowbreak and the latest uncensor release.", 0.18)
            self.status_label.setText("Checking...")
            self.main_button.setText("Checking...")
            self.main_button.setEnabled(False)
        elif self.ui_state == "ready_to_install":
            reason = self.decision.reason if self.decision else "Ready to install."
            title = "Game needed" if self.install is None else "Setup needed"
            self._set_top_state(title, reason, 0.0)
            self.status_label.setText(_short_status_text(reason))
            self.main_button.setText("Install")
            self.main_button.setEnabled(True)
        elif self.ui_state == "ready_to_update":
            reason = self.decision.reason if self.decision else "Ready to update."
            self._set_top_state("Update ready", reason, 0.0)
            self.status_label.setText(_short_status_text(reason))
            self.main_button.setText("Update")
            self.main_button.setEnabled(True)
        elif self.ui_state in {"installing", "updating"}:
            title = "Updating" if self.ui_state == "updating" else "Installing"
            self._set_top_state(title, "Working carefully. Please keep the launcher open.", self.top_progress_value)
            self.main_button.setText("Working...")
            self.main_button.setEnabled(False)
        elif self.ui_state == "ready_to_launch":
            self._set_top_state("Launch ready", "Done.", 1.0)
            self.status_label.setText("Installed and up to date.")
            self.main_button.setText("Launch")
            self.main_button.setEnabled(True)
        elif self.ui_state == "error":
            self._set_top_state("Needs attention", "Something needs attention, but your setup was kept safe.", 0.0)
            self.main_button.setText("Try Again")
            self.main_button.setEnabled(True)
        self.update()

    def _current_checklist(self) -> dict[str, tuple[str, str]]:
        if self.ui_state in {"checking", "error"}:
            return {
            "Game": ("idle", "Checking game"),
                "Switch": ("idle", "Checking loc"),
                "Core": ("idle", "Checking files"),
                "Assets": ("idle", "Checking assets"),
            }
        if self.ui_state == "disclaimer":
            return {
                "Game": ("idle", "Game check"),
                "Switch": ("idle", "loc check"),
                "Core": ("idle", "Uncensor check"),
                "Assets": ("idle", "Assets check"),
            }

        install = self.install
        if install:
            game = ("ok", f"{install.install_type} found")
            localization_enabled = is_localization_enabled(install.localization_path)
            localization = (
                "ok" if localization_enabled else "pending",
                "loc=1" if localization_enabled else "loc=0",
            )
            static_ok, present_static = static_asset_status(install.ix_folder)
            self.static_assets_installed = static_ok
            self.present_static_assets = present_static
            static_kind = "ok" if static_ok else "warn"
            static_text = "Assets installed" if static_ok else "Assets missing"
            if present_static and not static_ok:
                static_text = f"Assets {len(present_static)}/2"
        else:
            game = ("warn", "Choose game")
            localization = ("pending", "loc=0")
            static_ok = False
            static_kind = "pending"
            static_text = "Assets pending"

        core_ok, _ = uncensor_file_status(install.ix_folder, self.state_data) if install else (False, [])
        self.core_files_installed = core_ok
        if self.ui_state == "ready_to_update" and self.local_install_complete:
            core = ("warn", "Update available")
        elif core_ok and self.local_install_complete:
            core = ("ok", "Uncensor current")
        elif install:
            core = ("warn", "Uncensor missing")
        elif self.latest_release:
            core = ("pending", "Uncensor ready")
        else:
            core = ("pending", "Uncensor pending")

        return {
            "Game": game,
            "Switch": localization,
            "Core": core,
            "Assets": (static_kind, static_text),
        }

    def _set_top_state(self, title: str, detail: str, progress: float) -> None:
        self.top_title = title
        self.top_detail = detail
        self.top_progress_value = max(0.0, min(1.0, progress))
        self.update()

    def _set_footer_visibility(self, installed: bool, show_error_tools: bool) -> None:
        self.uninstall_button.setVisible(installed)
        self.log_button.setVisible(show_error_tools)
        self.import_button.setVisible(show_error_tools)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        source = QRectF(0, 0, self._background.width(), self._background.height())
        if self._background.width() > self.width():
            extra = self._background.width() - self.width()
            source.setLeft(extra / 2)
            source.setWidth(self.width())
        if self._background.height() > self.height():
            extra = self._background.height() - self.height()
            source.setTop(extra / 2)
            source.setHeight(self.height())
        painter.drawPixmap(QRectF(self.rect()), self._background, source)
        self._paint_top_bar(painter)
        self._paint_watermark(painter)

    def _paint_top_bar(self, painter: QPainter) -> None:
        bar = QRectF(0, 0, self.width(), 104)
        painter.setPen(QPen(QColor(124, 210, 235, 95), 1))
        painter.setBrush(QColor(1, 18, 31, 214))
        painter.drawRect(bar)

        painter.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        painter.setPen(QColor(242, 252, 255))
        painter.drawText(QRectF(22, 18, 330, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.top_title)

        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor(188, 225, 240))
        detail_rect = QRectF(22, 50, 330, 22)
        detail = QFontMetrics(painter.font()).elidedText(self.top_detail, Qt.TextElideMode.ElideRight, int(detail_rect.width()))
        painter.drawText(detail_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)

        track = QRectF(22, 84, 328, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(19, 54, 73, 210))
        painter.drawRoundedRect(track, 2, 2)
        fill_width = max(0.0, track.width() * self.top_progress_value)
        painter.setBrush(QColor(181, 239, 255, 235))
        painter.drawRoundedRect(QRectF(track.left(), track.top(), fill_width, track.height()), 2, 2)

    def _paint_watermark(self, painter: QPainter) -> None:
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor(222, 244, 252, 215))
        painter.drawText(QRectF(760, 530, 120, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "by Tashi")

    def _main_action(self) -> None:
        if self.ui_state == "disclaimer":
            self.state_data.accepted_notice = True
            self.state_data.disclaimer_accepted_at = datetime.now().isoformat(timespec="seconds")
            save_state(self.state_data)
            self.ui_state = "checking"
            self._render()
            self._start_checks()
        elif self.ui_state in {"ready_to_install", "ready_to_update"}:
            self._start_setup_or_update()
        elif self.ui_state == "ready_to_launch":
            self._launch_game()
        elif self.ui_state == "error":
            self.ui_state = "checking"
            self._render()
            self._start_checks()

    def _cancel_action(self) -> None:
        if self.busy:
            self.cancel_requested = True
            self.status_label.setText("Cancelling after the current safe step...")
            return
        self.close()

    def _start_checks(self) -> None:
        if self.busy:
            return
        self.ui_state = "checking"
        self._render()

        def work() -> None:
            try:
                install = self.install or auto_detect_install()
                release = None
                if install:
                    install_to_state(install, self.state_data)
                    release = fetch_latest_release()
                    self.state_data.last_checked_release = release.tag_name
                    self.state_data.last_check_time = datetime.now().isoformat(timespec="seconds")
                    save_state(self.state_data)
                self._signals.checks_done.emit(install, release)
            except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
                append_log(f"Update check failed: {exc}")
                self._signals.error.emit(f"Could not check for updates: {exc}")

        self._run_worker(work)

    def _finish_checks(self, install: InstallInfo | None, release: GitHubRelease | None) -> None:
        self.install = install
        self.latest_release = release
        static_ok = False
        core_ok = False
        if install:
            static_ok, _ = static_asset_status(install.ix_folder)
            core_ok, _ = uncensor_file_status(install.ix_folder, self.state_data)
        self.core_files_installed = core_ok
        self.static_assets_installed = static_ok
        self.decision = decide_next_state(self.state_data, install, release, core_ok, static_ok)
        self.local_install_complete = self.decision.local_install_complete
        self.ui_state = self.decision.ui_state
        self.busy = False
        self._render()
        if self.decision.should_auto_update:
            QTimer.singleShot(250, self._start_setup_or_update)

    def _start_setup_or_update(self) -> None:
        if self.busy:
            return
        if not self.install and not self._choose_folder():
            return
        if self.install is None:
            return
        self.cancel_requested = False
        self.ui_state = "updating" if self.local_install_complete and self.decision and self.decision.action_label == "Update" else "installing"
        self.top_progress_value = 0.0
        self.status_label.setText("Starting...")
        self._render()

        def work() -> None:
            try:
                setup_or_update(
                    self.install,  # type: ignore[arg-type]
                    self.state_data,
                    progress=lambda event: self._signals.progress.emit(event),
                    cancel_check=lambda: self.cancel_requested,
                    install_static_pack=True,
                )
                self._signals.setup_done.emit("Install/update complete.")
            except OperationCancelled as exc:
                append_log(str(exc))
                self._signals.cancelled.emit(str(exc))
            except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
                append_log(f"Setup failed: {exc}")
                self._signals.error.emit(str(exc))

        self._run_worker(work)

    def _choose_folder(self) -> bool:
        selected = QFileDialog.getExistingDirectory(self, "Choose your Snowbreak folder")
        if not selected:
            return False
        install = resolve_manual_install(selected)
        if not install:
            self._show_error("I could not find Game\\Content\\Paks in that folder. Please choose the Snowbreak install folder.")
            return False
        self.install = install
        install_to_state(install, self.state_data)
        save_state(self.state_data)
        append_log(f"Selected install: {install.game_root}")
        return True

    def _launch_game(self) -> None:
        if not self.install and not self._choose_folder():
            return
        install = self.install
        if install is None:
            return
        chosen_exe = None
        if install.install_type != "Steam" and not install.launcher_exe:
            selected, _ = QFileDialog.getOpenFileName(self, "Choose Snowbreak launcher EXE", "", "EXE files (*.exe);;All files (*.*)")
            if not selected:
                return
            chosen_exe = Path(selected)
            self.state_data.launcher_exe = str(chosen_exe)
            save_state(self.state_data)
        try:
            launch_game(install, chosen_exe=chosen_exe)
            self.status_label.setText("Launch command sent.")
            self.close()
        except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
            self._show_error(f"Could not launch Snowbreak: {exc}")

    def _uninstall(self) -> None:
        if not self.install:
            return
        confirmed = QMessageBox.question(
            self,
            "Uninstall uncensor files",
            "This removes all files inside Game\\Content\\Paks\\~ix and clears the installed status.\n\n"
            "Nothing outside ~ix will be touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            validate_ix_folder(self.install.paks_root, self.install.ix_folder)
            removed = uninstall_all_managed_files(self.install, self.state_data)
            self.state_data.installed_release = None
            self.state_data.installed_files = {}
            save_state(self.state_data)
            self.core_files_installed = False
            self.static_assets_installed = False
            self.local_install_complete = False
            self.status_label.setText(f"Uninstalled {removed} file(s)/folder(s).")
            self.ui_state = "ready_to_install"
            self._render()
        except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
            self._show_error(f"Uninstall failed: {exc}")

    def _import_static_zip(self) -> None:
        if not self.install and not self._choose_folder():
            return
        if self.install is None:
            return
        selected, _ = QFileDialog.getOpenFileName(self, "Choose static asset ZIP", "", "ZIP files (*.zip);;All files (*.*)")
        if not selected:
            return
        try:
            installed = import_static_zip(Path(selected), self.install.ix_folder)
            self.status_label.setText("Imported static assets: " + ", ".join(installed))
            self.ui_state = "checking"
            self._render()
            self._start_checks()
        except Exception as exc:  # noqa: BLE001 - user-facing GUI boundary
            self._show_error(f"Static ZIP import failed: {exc}")

    def _auto_update_changed(self, checked: bool) -> None:
        self.state_data.auto_update_enabled = checked
        save_state(self.state_data)

    def _view_log(self) -> None:
        path = log_path()
        path.touch(exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def _run_worker(self, target: callable) -> None:
        self.busy = True
        threading.Thread(target=target, daemon=True).start()

    def _apply_progress(self, event: ProgressEvent) -> None:
        title = "Updating" if self.ui_state == "updating" else "Installing"
        self._set_top_state(title, event.message, event.fraction)
        self.status_label.setText(_progress_status_text(event))

    def _setup_done(self, message: str) -> None:
        self.busy = False
        self.core_files_installed = True
        self.static_assets_installed = True
        self.local_install_complete = True
        self.decision = UpdateDecision("ready_to_launch", "Launch", "Done.", local_install_complete=True)
        self.ui_state = "ready_to_launch"
        self.status_label.setText(message)
        self._render()

    def _cancelled(self, message: str) -> None:
        self.busy = False
        self.ui_state = "ready_to_update" if self.local_install_complete else "ready_to_install"
        self.status_label.setText("Cancelled. No partial download was installed.")
        self._render()

    def _show_error(self, message: str) -> None:
        self.busy = False
        self.ui_state = "error"
        self.status_label.setText(message)
        self._render()

    def _notice_accepted(self) -> bool:
        return bool(self.state_data.accepted_notice or self.state_data.disclaimer_accepted_at)


def create_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or [])
    return app


def _asset_path(*parts: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        root = Path(bundle_root)
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "assets" / Path(*parts)


def _load_background_pixmap() -> QPixmap:
    path = _asset_path("images", "background.png")
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        fallback = QPixmap(*WINDOW_SIZE)
        fallback.fill(QColor(7, 17, 29))
        return fallback
    return pixmap.scaled(*WINDOW_SIZE, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.0f} KB"
    return f"{value} B"


def _short_status_text(text: str) -> str:
    lowered = text.lower()
    if "choose" in lowered or "not detected" in lowered:
        return "Choose Snowbreak folder."
    if "update available" in lowered:
        return "Update available."
    if "assets" in lowered and "uncensor" in lowered:
        return "Files and assets missing."
    if "assets" in lowered:
        return "Assets missing."
    if "uncensor" in lowered:
        return "Uncensor missing."
    if "install" in lowered:
        return "Ready to install."
    return text if len(text) <= 32 else text[:29].rstrip() + "..."


def _progress_status_text(event: ProgressEvent) -> str:
    if event.bytes_total:
        label = "Static assets" if "static asset" in event.message.lower() else event.phase
        return f"{label}: {_format_bytes(event.bytes_downloaded)} / {_format_bytes(event.bytes_total)}"
    return f"{event.phase}: {_short_status_text(event.message)}"


def _fitted_font(
    text: str,
    family: str,
    start_size: int,
    weight: QFont.Weight,
    max_width: int,
    *,
    min_size: int,
) -> QFont:
    for size in range(start_size, min_size - 1, -1):
        font = QFont(family, size, weight)
        if QFontMetrics(font).horizontalAdvance(text) <= max_width:
            return font
    return QFont(family, min_size, weight)


def _elided_text(font: QFont, text: str, max_width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, max_width)


def open_release_page() -> str:
    return GITHUB_RELEASE_PAGE
