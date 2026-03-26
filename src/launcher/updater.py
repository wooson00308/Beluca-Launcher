"""BPE 업데이트 순수 로직. PySide6 import 금지."""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("launcher.updater")

_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def _make_ssl_context():
    """certifi 인증서가 있으면 사용, 없으면 기본 context."""
    import ssl

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def download_asset(
    url: str,
    dest: Path,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> Path:
    """URL에서 파일을 다운로드한다.

    progress_cb는 0.0~1.0 범위로 호출된다.
    """
    if not url.startswith("https://github.com/"):
        raise ValueError(f"Untrusted download URL: {url}")

    ctx = _make_ssl_context()
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "BPELauncher/1.0")

    tmp_dest = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0

            with open(tmp_dest, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(min(downloaded / total, 1.0))

        tmp_dest.rename(dest)
    except Exception:
        if tmp_dest.exists():
            tmp_dest.unlink()
        raise

    if progress_cb:
        progress_cb(1.0)

    logger.info("다운로드 완료: %s", dest)
    return dest


def wait_for_process_exit(app_path: str, timeout: float = 30.0) -> bool:
    """Windows에서 BPE.exe가 완전히 종료될 때까지 대기한다.

    macOS에서는 파일 락이 없으므로 바로 True 반환.
    """
    if platform.system() != "Windows":
        return True

    exe_path = Path(app_path)
    if not exe_path.is_file():
        return True

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(exe_path, "r+b"):
                pass
            logger.info("프로세스 종료 확인: %s", app_path)
            return True
        except (PermissionError, OSError):
            time.sleep(1.0)

    logger.warning("프로세스 종료 대기 타임아웃: %s", app_path)
    return False


def extract_and_replace_macos(dmg_path: Path, app_path: Path) -> None:
    """macOS: dmg를 마운트하여 .app을 교체한다."""
    mountpoint = Path(tempfile.mkdtemp(prefix="bpe_mount_"))

    try:
        subprocess.run(
            [
                "hdiutil",
                "attach",
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(mountpoint),
                str(dmg_path),
            ],
            check=True,
            capture_output=True,
        )

        # 마운트된 볼륨에서 .app 찾기
        app_candidates = list(mountpoint.glob("*.app"))
        if not app_candidates:
            raise FileNotFoundError(f"dmg 안에 .app 번들을 찾을 수 없습니다: {mountpoint}")

        source_app = app_candidates[0]
        logger.info("소스 앱 발견: %s", source_app)

        # 기존 .app 삭제 후 복사
        if app_path.exists():
            shutil.rmtree(app_path)
        shutil.copytree(source_app, app_path, symlinks=True)
        logger.info("앱 교체 완료: %s", app_path)

    finally:
        subprocess.run(
            ["hdiutil", "detach", str(mountpoint), "-force"],
            capture_output=True,
        )
        if mountpoint.exists():
            shutil.rmtree(mountpoint, ignore_errors=True)

    # quarantine 속성 제거
    subprocess.run(
        ["xattr", "-cr", str(app_path)],
        capture_output=True,
    )

    # 임시 dmg 삭제
    dmg_path.unlink(missing_ok=True)


def extract_and_replace_windows(zip_path: Path, exe_path: Path) -> None:
    """Windows: zip을 해제하여 exe를 교체한다."""
    extract_dir = zip_path.parent / "_bpe_extract"

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                target = (extract_dir / info.filename).resolve()
                try:
                    target.relative_to(extract_dir.resolve())
                except ValueError:
                    raise RuntimeError(f"Unsafe path in zip: {info.filename}")
            zf.extractall(extract_dir)

        # zip 안에서 exe 찾기
        exe_candidates = list(extract_dir.rglob("*.exe"))
        if not exe_candidates:
            raise FileNotFoundError(f"zip 안에 exe를 찾을 수 없습니다: {zip_path}")

        source_exe = exe_candidates[0]
        shutil.copy2(source_exe, exe_path)
        logger.info("exe 교체 완료: %s", exe_path)

    finally:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)

    # 임시 zip 삭제
    zip_path.unlink(missing_ok=True)


def launch_app(app_path: str) -> None:
    """업데이트된 BPE를 실행한다."""
    if platform.system() == "Darwin":
        subprocess.Popen(["open", app_path])
    else:
        # Windows
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [app_path],
            creationflags=DETACHED_PROCESS if sys.platform == "win32" else 0,
        )
    logger.info("앱 실행: %s", app_path)
