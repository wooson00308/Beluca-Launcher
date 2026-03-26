"""BPE 업데이트 런처 GUI."""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher import updater

logger = logging.getLogger("launcher.gui")


class _UpdateThread(QThread):
    """백그라운드에서 업데이트를 수행하는 워커 스레드."""

    progress = Signal(float)
    finished = Signal(bool, str)

    def __init__(
        self,
        version: str,
        download_url: str,
        app_path: str,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._version = version
        self._download_url = download_url
        self._app_path = app_path

    def run(self) -> None:
        try:
            # 다운로드 경로 결정
            if sys.platform == "darwin":
                suffix = ".dmg"
            else:
                suffix = ".zip"
            dest = Path(tempfile.gettempdir()) / f"BPE-{self._version}{suffix}"

            # 다운로드
            updater.download_asset(
                self._download_url,
                dest,
                progress_cb=self.progress.emit,
            )

            # 프로세스 종료 대기 (Windows)
            if not updater.wait_for_process_exit(self._app_path):
                self.finished.emit(False, "BPE 프로세스 종료 대기 시간 초과")
                return

            # 교체
            app_path = Path(self._app_path)
            if sys.platform == "darwin":
                updater.extract_and_replace_macos(dest, app_path)
            else:
                updater.extract_and_replace_windows(dest, app_path)

            # 새 BPE 실행
            updater.launch_app(self._app_path)

            self.finished.emit(True, f"v{self._version} 업데이트 완료")

        except Exception as e:
            logger.exception("업데이트 실패")
            self.finished.emit(False, str(e))


class UpdateWindow(QWidget):
    """업데이트 진행률을 표시하는 메인 윈도우."""

    update_finished = Signal(bool, str)

    WINDOW_W = 400
    WINDOW_H = 220
    BG_COLOR = "#1a1a1d"
    ACCENT_COLOR = "#f08a24"
    TEXT_COLOR = "#e0e0e0"
    SUBTEXT_COLOR = "#999999"

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._worker = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFixedSize(self.WINDOW_W, self.WINDOW_H)
        self.setWindowTitle("BPE Launcher")
        self.setStyleSheet(f"background-color: {self.BG_COLOR};")

        # 화면 가운데 정렬
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.WINDOW_W) // 2
            y = (geo.height() - self.WINDOW_H) // 2
            self.move(x, y)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(12)

        # 타이틀
        self._title = QLabel("BPE 업데이트")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._title.setStyleSheet(f"color: {self.ACCENT_COLOR};")
        layout.addWidget(self._title)

        # 상태 메시지
        self._status = QLabel("준비 중...")
        self._status.setStyleSheet(f"color: {self.TEXT_COLOR}; font-size: 13px;")
        layout.addWidget(self._status)

        layout.addSpacing(4)

        # 프로그레스바
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: #2a2a2d;
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {self.ACCENT_COLOR};
                border-radius: 4px;
            }}
            """
        )
        layout.addWidget(self._progress)

        # 퍼센트 표시
        self._percent = QLabel("0%")
        self._percent.setStyleSheet(f"color: {self.SUBTEXT_COLOR}; font-size: 12px;")
        layout.addWidget(self._percent)

        layout.addStretch()

    def start_update(self, version: str, download_url: str, app_path: str) -> None:
        """업데이트를 시작한다."""
        if self._worker and self._worker.isRunning():
            return
        self._app_path = app_path
        self._status.setText(f"v{version} 업데이트 중...")
        self._worker = _UpdateThread(version, download_url, app_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    @Slot(float)
    def _on_progress(self, value: float) -> None:
        pct = int(value * 100)
        self._progress.setValue(pct)
        self._percent.setText(f"{pct}%")

    @Slot(bool, str)
    def _on_finished(self, success: bool, message: str) -> None:
        self.update_finished.emit(success, message)

        if success:
            logger.info("업데이트 성공: %s", message)
            QApplication.quit()
        else:
            logger.error("업데이트 실패: %s", message)
            self._status.setText(f"업데이트 실패: {message}")
            self._status.setStyleSheet("color: #ff4444; font-size: 13px;")
            self._progress.setStyleSheet(
                """
                QProgressBar {
                    background-color: #2a2a2d;
                    border: none;
                    border-radius: 4px;
                }
                QProgressBar::chunk {
                    background-color: #ff4444;
                    border-radius: 4px;
                }
                """
            )
            btn = QPushButton("BPE 실행")
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {self.ACCENT_COLOR};
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: #d07a20;
                }}
                """
            )
            btn.clicked.connect(self._launch_and_quit)
            self.layout().addWidget(btn)

    def _launch_and_quit(self) -> None:
        """기존 BPE를 실행하고 런처를 종료한다."""
        updater.launch_app(self._app_path)
        QApplication.quit()
