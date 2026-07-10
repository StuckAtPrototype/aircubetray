"""Fetch AirCube firmware releases from GitHub."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from .. import FIRMWARE_REPO
from ..store import data_dir

RELEASES_API = f"https://api.github.com/repos/{FIRMWARE_REPO}/releases"
FIRMWARE_ASSET_RE = re.compile(r"AirCube_firmware_v?([\d.]+)\.bin$", re.IGNORECASE)


@dataclass
class FirmwareRelease:
    version: str
    tag: str
    name: str
    asset_name: str
    download_url: str
    size: int
    published_at: str
    body: str


class ReleaseFetcher(QThread):
    """Fetch the list of firmware releases (assets matching AirCube_firmware_*.bin)."""
    releases_ready = pyqtSignal(list)   # [FirmwareRelease]
    error = pyqtSignal(str)

    def run(self):
        try:
            resp = requests.get(RELEASES_API, timeout=15,
                                headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            releases: list[FirmwareRelease] = []
            for rel in resp.json():
                for asset in rel.get("assets", []):
                    m = FIRMWARE_ASSET_RE.search(asset.get("name", ""))
                    if not m:
                        continue
                    releases.append(FirmwareRelease(
                        version=m.group(1).strip("."),
                        tag=rel.get("tag_name", ""),
                        name=rel.get("name", "") or rel.get("tag_name", ""),
                        asset_name=asset["name"],
                        download_url=asset["browser_download_url"],
                        size=asset.get("size", 0),
                        published_at=(rel.get("published_at", "") or "")[:10],
                        body=rel.get("body", "") or "",
                    ))
            self.releases_ready.emit(releases)
        except Exception as e:
            self.error.emit(str(e))


class FirmwareDownloader(QThread):
    """Download a firmware asset to the app data dir."""
    progress = pyqtSignal(int, int)   # received, total bytes
    finished_ok = pyqtSignal(str)     # local path
    error = pyqtSignal(str)

    def __init__(self, release: FirmwareRelease):
        super().__init__()
        self.release = release

    def run(self):
        try:
            fw_dir = os.path.join(data_dir(), "firmware")
            os.makedirs(fw_dir, exist_ok=True)
            path = os.path.join(fw_dir, self.release.asset_name)
            if (os.path.exists(path) and self.release.size
                    and os.path.getsize(path) == self.release.size):
                self.finished_ok.emit(path)
                return
            with requests.get(self.release.download_url, stream=True,
                              timeout=30) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0)) or self.release.size
                received = 0
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                        received += len(chunk)
                        self.progress.emit(received, total)
            os.replace(tmp, path)
            self.finished_ok.emit(path)
        except Exception as e:
            self.error.emit(str(e))
