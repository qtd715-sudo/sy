"""HTTP fetch helper.

Python urllib (OpenSSL) 가 SSL 환경 이슈로 일부 서버(Naver, Google News 등)와
연결을 못 할 때, 시스템 curl(Windows schannel) 으로 폴백.

순서:
  1) urllib.request 시도
  2) 실패 시 system curl 시도
  3) 둘 다 실패 시 None
"""

from __future__ import annotations
import json
import shutil
import subprocess
import urllib.request
from typing import Any


_CURL = shutil.which("curl") or "curl"
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def fetch(url: str, timeout: int = 6, headers: dict[str, str] | None = None) -> bytes | None:
    """URL → 바이트. 실패 시 None."""
    h = {"User-Agent": DEFAULT_UA}
    if headers:
        h.update(headers)

    # 1) urllib
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        pass

    # 2) curl 폴백 (Windows schannel)
    try:
        cmd = [
            _CURL, "-s", "-L",
            "--max-time", str(timeout),
            "-A", h["User-Agent"],
        ]
        for k, v in h.items():
            if k.lower() == "user-agent":
                continue
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(url)
        out = subprocess.run(cmd, capture_output=True, timeout=timeout + 2, check=False)
        if out.returncode == 0 and out.stdout:
            return out.stdout
    except Exception:
        pass

    return None


def fetch_json(url: str, timeout: int = 6, headers: dict[str, str] | None = None) -> Any | None:
    data = fetch(url, timeout=timeout, headers=headers)
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None
