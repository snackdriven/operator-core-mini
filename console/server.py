"""
server.py — three-pane console for an operator-root.

Stdlib-only HTTP server. Serves a static SPA + JSON API:

  GET  /                      static SPA (console/static/index.html)
  GET  /static/<path>         other static assets
  GET  /api/tree              file tree of the operator-root by layer
  GET  /api/file?path=<rel>   file body
  PUT  /api/file?path=<rel>   write file body (raw text request body)
  GET  /api/items             compact derived item list (id/path/freshness/ttl)
  POST /api/render            run a renderer; body { renderer, now?, energy?, skin? }
  POST /api/verb              execute a verb; body { verb, id, now? }

Run:

  python console/server.py [operator-root] [--port 8765] [--host 127.0.0.1]

Defaults to ``examples/operator-root-fixture/`` so first-run is instant.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
RENDERERS_DIR = REPO_ROOT / "renderers"
STATIC_DIR = THIS_DIR / "static"

sys.path.insert(0, str(THIS_DIR))
import verbs  # noqa: E402

RENDERER_IDS = [
    "session-primer",
    "daily-brief",
    "statusline",
    "narrator-list",
    "narrator-brief",
]

RENDERER_FILES = {
    "session-primer": "session_primer.py",
    "daily-brief": "daily_brief.py",
    "statusline": "statusline.py",
    "narrator-list": "narrator_list.py",
    "narrator-brief": "narrator_brief.py",
}

VOICE_AWARE = {"narrator-list", "narrator-brief"}

LAYERS = ["backpack", "doctrine", "hoard", "policy"]


# ---------------------------------------------------------------------------
# Frontmatter helpers (kept small; verbs.py owns the canonical loader)
# ---------------------------------------------------------------------------

def _read_frontmatter_lite(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---\n"):
        return None
    try:
        fm, _ = verbs._split_frontmatter(text)
    except Exception:
        return None
    return fm


# ---------------------------------------------------------------------------
# Tree + items
# ---------------------------------------------------------------------------

def build_tree(operator_root: Path) -> dict:
    """Return {layer: [{path, name}]} for the four substrate layers."""
    tree: dict[str, list] = {layer: [] for layer in LAYERS}
    for layer in LAYERS:
        root = operator_root / layer
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            rel = str(path.relative_to(operator_root))
            tree[layer].append({
                "path": rel,
                "name": path.name,
                "subdir": str(path.parent.relative_to(root)),
            })
    return tree


def build_items(operator_root: Path) -> list[dict]:
    """Compact item list with derived fields the palette uses."""
    items: list[dict] = []
    now = datetime.now(timezone.utc)
    for layer in ("backpack", "hoard"):
        root = operator_root / layer
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            if "_replaced" in path.parts:
                continue
            fm = _read_frontmatter_lite(path)
            if fm is None:
                continue
            ttl = fm.get("ttl_seconds")
            created_at = fm.get("created_at")
            stale = False
            if ttl and created_at:
                try:
                    ca = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    age_s = (now - ca).total_seconds()
                    stale = age_s > int(ttl)
                except (ValueError, TypeError):
                    pass
            items.append({
                "id": fm.get("id"),
                "path": str(path.relative_to(operator_root)),
                "layer": layer,
                "freshness_class": fm.get("freshness_class"),
                "memory_class": fm.get("memory_class"),
                "area": fm.get("area"),
                "tags": fm.get("tags") or [],
                "summary": fm.get("summary"),
                "dated": fm.get("dated"),
                "created_at": created_at,
                "ttl_seconds": ttl,
                "aged_out_at": fm.get("aged_out_at"),
                "stale": stale,
                "priority": (fm.get("renderer_hints") or {}).get("priority"),
            })
    return items


# ---------------------------------------------------------------------------
# Renderer invocation
# ---------------------------------------------------------------------------

def run_renderer(
    operator_root: Path,
    renderer_id: str,
    *,
    now: str | None = None,
    energy: str | None = None,
    skin: str | None = None,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    fname = RENDERER_FILES.get(renderer_id)
    if fname is None:
        return False, f"unknown renderer: {renderer_id}"
    script = RENDERERS_DIR / fname
    if not script.is_file():
        return False, f"renderer file missing: {script}"
    cmd = [sys.executable, str(script), str(operator_root)]
    if now:
        cmd += ["--now", now]
    if energy and renderer_id in VOICE_AWARE:
        cmd += ["--energy", energy]
    if skin and renderer_id in VOICE_AWARE:
        cmd += ["--skin", skin]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"renderer {renderer_id} timed out after {timeout}s"
    if proc.returncode != 0:
        return False, f"$ {' '.join(cmd)}\nexit={proc.returncode}\n{proc.stderr}"
    return True, proc.stdout


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ConsoleHandler(BaseHTTPRequestHandler):
    operator_root: Path  # set on the class before serving

    server_version = "OperatorConsole/0.1"

    def log_message(self, fmt: str, *args) -> None:  # quieter logs
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    # -- response helpers ---------------------------------------------------

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, ctype: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: Path) -> None:
        if not path.is_file():
            return self._send_text(404, "not found")
        ctype, _ = mimetypes.guess_type(str(path))
        ctype = ctype or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return ""
        return self.rfile.read(length).decode("utf-8")

    # -- path safety --------------------------------------------------------

    def _resolve_within_root(self, rel: str) -> Path | None:
        if not rel:
            return None
        # block traversal; allow forward slashes only
        if ".." in Path(rel).parts:
            return None
        if Path(rel).is_absolute():
            return None
        target = (self.operator_root / rel).resolve()
        try:
            target.relative_to(self.operator_root.resolve())
        except ValueError:
            return None
        return target

    # -- routing ------------------------------------------------------------

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        if path == "/" or path == "/index.html":
            return self._send_static(STATIC_DIR / "index.html")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            return self._send_static(STATIC_DIR / rel)
        if path == "/api/tree":
            return self._send_json(200, {
                "operator_root": str(self.operator_root),
                "tree": build_tree(self.operator_root),
            })
        if path == "/api/items":
            return self._send_json(200, {"items": build_items(self.operator_root)})
        if path == "/api/file":
            rel = (qs.get("path") or [""])[0]
            target = self._resolve_within_root(rel)
            if target is None or not target.is_file():
                return self._send_json(404, {"error": "not found"})
            try:
                return self._send_text(200, target.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                return self._send_json(415, {"error": "binary file"})
        if path == "/api/renderers":
            return self._send_json(200, {"renderers": RENDERER_IDS})
        return self._send_text(404, "not found")

    def do_PUT(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        if path == "/api/file":
            rel = (qs.get("path") or [""])[0]
            target = self._resolve_within_root(rel)
            if target is None:
                return self._send_json(400, {"error": "invalid path"})
            body = self._read_body()
            target.parent.mkdir(parents=True, exist_ok=True)
            verbs._atomic_write(target, body)
            return self._send_json(200, {"ok": True, "path": rel})
        return self._send_text(404, "not found")

    def do_POST(self) -> None:
        url = urllib.parse.urlparse(self.path)
        path = url.path

        if path == "/api/render":
            data = self._read_json()
            rid = data.get("renderer")
            if rid not in RENDERER_IDS:
                return self._send_json(400, {"error": f"unknown renderer: {rid}"})
            ok, output = run_renderer(
                self.operator_root,
                rid,
                now=data.get("now"),
                energy=data.get("energy"),
                skin=data.get("skin"),
            )
            return self._send_json(200, {"ok": ok, "output": output, "renderer": rid})

        if path == "/api/verb":
            data = self._read_json()
            verb = data.get("verb")
            item_id = data.get("id")
            now_str = data.get("now")
            now_dt = None
            if now_str:
                try:
                    now_dt = datetime.fromisoformat(str(now_str).replace("Z", "+00:00"))
                except ValueError:
                    return self._send_json(400, {"error": f"bad now: {now_str}"})
            if not isinstance(item_id, str) or not item_id:
                return self._send_json(400, {"error": "missing id"})
            try:
                if verb == "verify":
                    result = verbs.verify(self.operator_root, item_id, now=now_dt)
                elif verb == "pin":
                    result = verbs.pin(self.operator_root, item_id)
                elif verb == "unpin":
                    result = verbs.unpin(self.operator_root, item_id)
                elif verb == "demote":
                    result = verbs.demote(self.operator_root, item_id, now=now_dt)
                else:
                    return self._send_json(400, {"error": f"unknown verb: {verb}"})
            except Exception as exc:  # surface errors to the UI
                return self._send_json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return self._send_json(200 if result["ok"] else 409, result)

        return self._send_text(404, "not found")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument(
        "operator_root",
        nargs="?",
        default=str(REPO_ROOT / "examples" / "operator-root-fixture"),
        help="path to the operator root (default: examples/operator-root-fixture)",
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args(argv)

    operator_root = Path(args.operator_root).resolve()
    if not operator_root.is_dir():
        print(f"operator root does not exist: {operator_root}", file=sys.stderr)
        return 2

    ConsoleHandler.operator_root = operator_root
    server = ThreadingHTTPServer((args.host, args.port), ConsoleHandler)
    print(f"console: http://{args.host}:{args.port}  (root: {operator_root})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
