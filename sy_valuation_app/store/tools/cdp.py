"""Python wrapper for cdp_shot.mjs (exact-size headless Chrome screenshots)."""
import json
import pathlib
import subprocess

SCR = pathlib.Path(__file__).resolve().parent
NODE = "node"
SCRIPT = SCR / "cdp_shot.mjs"


def shot(url: str, w: int, h: int, dpr: float, out: str, css_file: str | None = None,
         wait_ms: int = 1500, mobile: bool = True, max_ms: int = 60000) -> dict:
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
        url = pathlib.Path(url).resolve().as_uri()
    cmd = [NODE, str(SCRIPT), url, str(w), str(h), str(dpr), str(out),
           "--wait", str(wait_ms), "--mobile", "1" if mobile else "0", "--max", str(max_ms)]
    if css_file:
        cmd += ["--css", str(css_file)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=max_ms / 1000 + 60)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"cdp_shot failed: {r.stderr[-2000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])
