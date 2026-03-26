"""updater 모듈 테스트."""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from launcher.updater import (
    download_asset,
    extract_and_replace_windows,
    wait_for_process_exit,
)


class _FakeResponse:
    """urllib.request.urlopen 대체용 페이크 응답."""

    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class TestDownloadAsset:
    def test_download_writes_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        test_data = b"fake-binary-content" * 100
        dest = tmp_path / "test_download.dmg"

        def fake_urlopen(req: Any, context: Any = None) -> _FakeResponse:
            return _FakeResponse(test_data)

        monkeypatch.setattr("launcher.updater.urllib.request.urlopen", fake_urlopen)

        progress_values: list[float] = []
        result = download_asset(
            "https://github.com/fake.dmg",
            dest,
            progress_cb=progress_values.append,
        )

        assert result == dest
        assert dest.read_bytes() == test_data
        assert len(progress_values) > 0
        assert progress_values[-1] == 1.0

    def test_download_no_content_length(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        test_data = b"small"
        dest = tmp_path / "no_length.bin"

        def fake_urlopen(req: Any, context: Any = None) -> _FakeResponse:
            resp = _FakeResponse(test_data)
            resp.headers["Content-Length"] = "0"
            return resp

        monkeypatch.setattr("launcher.updater.urllib.request.urlopen", fake_urlopen)

        result = download_asset("https://github.com/fake.bin", dest)
        assert result == dest
        assert dest.read_bytes() == test_data


class TestExtractAndReplaceWindows:
    def test_extract_replaces_exe(self, tmp_path: Path) -> None:
        # zip 생성
        zip_path = tmp_path / "update.zip"
        exe_content = b"NEW_EXE_CONTENT"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("BPE.exe", exe_content)

        # 기존 exe
        exe_path = tmp_path / "BPE.exe"
        exe_path.write_bytes(b"OLD_EXE_CONTENT")

        extract_and_replace_windows(zip_path, exe_path)

        assert exe_path.read_bytes() == exe_content
        assert not zip_path.exists()  # 임시 zip 삭제됨

    def test_extract_zipslip_raises(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../../etc/passwd", "hacked")

        exe_path = tmp_path / "BPE.exe"

        with pytest.raises(RuntimeError, match="Unsafe path in zip"):
            extract_and_replace_windows(zip_path, exe_path)

    def test_extract_no_exe_raises(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "hello")

        exe_path = tmp_path / "BPE.exe"

        with pytest.raises(FileNotFoundError):
            extract_and_replace_windows(zip_path, exe_path)


class TestWaitForProcessExit:
    @patch("launcher.updater.platform.system", return_value="Darwin")
    def test_macos_returns_immediately(self, mock_system: MagicMock) -> None:
        assert wait_for_process_exit("/some/path") is True

    @patch("launcher.updater.platform.system", return_value="Windows")
    def test_windows_nonexistent_returns_true(self, mock_system: MagicMock, tmp_path: Path) -> None:
        assert wait_for_process_exit(str(tmp_path / "nonexistent.exe")) is True

    @patch("launcher.updater.platform.system", return_value="Windows")
    def test_windows_accessible_file_returns_true(
        self, mock_system: MagicMock, tmp_path: Path
    ) -> None:
        exe = tmp_path / "test.exe"
        exe.write_bytes(b"data")
        assert wait_for_process_exit(str(exe), timeout=2.0) is True

    @patch("launcher.updater.platform.system", return_value="Windows")
    def test_windows_timeout(self, mock_system: MagicMock, tmp_path: Path) -> None:
        exe = tmp_path / "locked.exe"
        exe.write_bytes(b"data")

        original_open = open

        def fake_open(*args: Any, **kwargs: Any) -> Any:
            if str(exe) in str(args[0]):
                raise PermissionError("File is locked")
            return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=fake_open):
            start = time.monotonic()
            result = wait_for_process_exit(str(exe), timeout=2.0)
            elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 1.5  # 최소 timeout 근처까지 대기했는지
