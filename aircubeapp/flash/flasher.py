"""esptool worker: flashes AirCube firmware (ESP32-H2) on a background thread.

Release firmware is a single merged image flashed at 0x0 (matches
FIRMWARE_UPDATE.md / ESP Launchpad). Custom .bin files use a caller-chosen
offset (0x0 for merged images, 0x10000 for app-only builds).
"""
from __future__ import annotations

import io
import sys

from PyQt6.QtCore import QThread, pyqtSignal

FLASH_BAUD = 460800
CHIP = "esp32h2"


class _EmittingStream(io.TextIOBase):
    """Line-buffered stdout shim that forwards esptool output to a signal."""

    def __init__(self, emit):
        super().__init__()
        self._emit = emit
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        # esptool uses \r for progress updates; treat both as line breaks
        while True:
            idx_n = self._buf.find("\n")
            idx_r = self._buf.find("\r")
            candidates = [i for i in (idx_n, idx_r) if i >= 0]
            if not candidates:
                break
            idx = min(candidates)
            line = self._buf[:idx].strip()
            self._buf = self._buf[idx + 1:]
            if line:
                self._emit(line)
        return len(s)

    def flush(self):
        pass


class FlashWorker(QThread):
    """Runs esptool write-flash in-process on a worker thread."""
    log_line = pyqtSignal(str)
    progress_percent = pyqtSignal(int)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, port: str, firmware_path: str, offset: int = 0x0):
        super().__init__()
        self.port = port
        self.firmware_path = firmware_path
        self.offset = offset

    def run(self):
        args = [
            "--chip", CHIP,
            "--port", self.port,
            "--baud", str(FLASH_BAUD),
            "--before", "default-reset",
            "--after", "hard-reset",
            "write-flash",
            f"0x{self.offset:X}", self.firmware_path,
        ]
        self.log_line.emit("esptool " + " ".join(args))

        stream = _EmittingStream(self._on_line)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stream, stream
        try:
            import esptool
            esptool.main(args)
        except SystemExit as e:
            if e.code in (0, None):
                self.finished_ok.emit()
            else:
                self.failed.emit(f"esptool exited with code {e.code}")
            return
        except Exception as e:
            self.failed.emit(str(e))
            return
        finally:
            sys.stdout, sys.stderr = old_out, old_err
        self.finished_ok.emit()

    def _on_line(self, line: str):
        self.log_line.emit(line)
        # esptool progress lines look like "Writing at 0x00010000... (12 %)"
        if "%" in line:
            digits = "".join(ch for ch in line.split("(")[-1] if ch.isdigit())
            if digits:
                try:
                    self.progress_percent.emit(min(100, int(digits)))
                except ValueError:
                    pass
