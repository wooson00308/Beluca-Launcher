"""BPE 자동 업데이트 런처 엔트리포인트."""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("launcher")


def main() -> None:
    parser = argparse.ArgumentParser(description="BPE 자동 업데이트 런처")
    parser.add_argument("--version", required=True, help="업데이트할 버전")
    parser.add_argument("--download-url", required=True, help="다운로드 URL")
    parser.add_argument("--app-path", required=True, help="BPE 앱 경로")

    args = parser.parse_args()

    if not args.version or not args.download_url or not args.app_path:
        logger.error("필수 인자가 누락되었습니다.")
        sys.exit(1)

    from PySide6.QtWidgets import QApplication

    from launcher.gui import UpdateWindow

    app = QApplication(sys.argv)
    window = UpdateWindow()
    window.show()
    window.start_update(args.version, args.download_url, args.app_path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
