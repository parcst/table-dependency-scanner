"""HTTP server frontend for the table dependency scanner."""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional

from .inflection import singularize
from .models import Confidence, ScanResult
from .output import write_csv
from .repo import cleanup, clone_repo
from .runner import run_scan

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8642

# ─── Scan state (module-level, single concurrent scan) ───
_scan_lock = threading.Lock()
_scan_thread: Optional[threading.Thread] = None
_scan_cancelled = threading.Event()
_scan_progress: Dict[str, Any] = {"phase": "idle", "detail": ""}
_scan_result: Optional[Dict[str, Any]] = None
_scan_error: Optional[str] = None


def _set_progress(phase: str, detail: str = ""):
    global _scan_progress
    _scan_progress = {"phase": phase, "detail": detail}


def _run_scan_async(params: Dict[str, Any]):
    """Run the scan in a background thread, updating progress."""
    global _scan_result, _scan_error

    _scan_result = None
    _scan_error = None
    cloned_path = None

    try:
        source = params["source"]
        repo = params.get("repo", "")
        local_path = params.get("localPath", "")
        table_name = params.get("tableName", "rewards")
        pk_column = params.get("pkColumn", "id")
        min_confidence = Confidence[params.get("minConfidence", "LOW")]
        output_path = params.get("outputPath", "")
        strict_mode = bool(params.get("strictMode", False))

        if source == "github":
            _set_progress("cloning", f"Cloning {repo}...")
            if _scan_cancelled.is_set():
                return
            repo_path = clone_repo(repo)
            cloned_path = repo_path.parent
        else:
            repo_path = Path(local_path)

        if _scan_cancelled.is_set():
            return

        singular = singularize(table_name)
        fk_column = f"{singular}_{pk_column}" if pk_column else ""

        def progress_cb(phase: str, detail: str = ""):
            _set_progress(phase, detail)

        def cancel_check() -> bool:
            return _scan_cancelled.is_set()

        scan_data = run_scan(
            repo_path, table_name, min_confidence,
            fk_column=fk_column, strict_mode=strict_mode,
            progress_cb=progress_cb, cancel_check=cancel_check,
        )

        if _scan_cancelled.is_set():
            return

        results = scan_data["results"]
        stats = scan_data["stats"]

        if output_path:
            with open(output_path, "w", newline="") as f:
                write_csv(results, f)

        results_json = [
            {
                "file_path": r.file_path,
                "line_number": r.line_number,
                "table_name": r.table_name,
                "column_name": r.column_name,
                "reference_type": r.reference_type.value,
                "code_snippet": r.code_snippet,
                "confidence": r.confidence.value,
                "schema_verified": r.schema_verified,
            }
            for r in results
        ]

        _scan_result = {
            "status": "ok",
            "results": results_json,
            "stats": stats,
            "message": f"Found {len(results_json)} results",
        }
        _set_progress("done", f"{len(results_json)} results found")

    except Exception as e:
        if not _scan_cancelled.is_set():
            _scan_error = str(e)
            _set_progress("error", str(e))
    finally:
        if cloned_path:
            cleanup(cloned_path)


class ScanHandler(SimpleHTTPRequestHandler):
    """Handle API routes and serve static files."""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        elif self.path.startswith("/api/browse"):
            self._handle_browse()
        elif self.path == "/api/scan/progress":
            self._handle_progress()
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        if self.path == "/api/scan":
            self._handle_scan()
        elif self.path == "/api/scan/cancel":
            self._handle_cancel()
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def _serve_file(self, filepath: Path, content_type: str):
        try:
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_json(404, {"status": "error", "message": "File not found"})

    def _send_json(self, code: int, data: Dict[str, Any]):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_browse(self):
        """List directories for the path picker."""
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        target = params.get("path", [""])[0] or os.path.expanduser("~")

        target_path = Path(target)
        if not target_path.is_dir():
            self._send_json(400, {"status": "error", "message": f"Not a directory: {target}"})
            return

        try:
            entries = []
            for entry in sorted(target_path.iterdir()):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    entries.append({"name": entry.name, "path": str(entry), "is_dir": True})
            self._send_json(200, {
                "status": "ok",
                "current": str(target_path.resolve()),
                "parent": str(target_path.parent.resolve()),
                "entries": entries,
            })
        except PermissionError:
            self._send_json(403, {"status": "error", "message": "Permission denied"})

    def _handle_scan(self):
        """Start an async scan."""
        global _scan_thread

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"status": "error", "message": f"Invalid JSON: {e}"})
            return

        source = body.get("source", "local")
        repo = body.get("repo", "")
        local_path = body.get("localPath", "")

        if source == "github" and not repo:
            self._send_json(400, {"status": "error", "message": "repo is required for GitHub source"})
            return
        if source == "local" and not local_path:
            self._send_json(400, {"status": "error", "message": "localPath is required for local source"})
            return
        if source == "local" and not Path(local_path).is_dir():
            self._send_json(400, {"status": "error", "message": f"Not a directory: {local_path}"})
            return

        try:
            Confidence[body.get("minConfidence", "LOW")]
        except KeyError:
            self._send_json(400, {"status": "error", "message": f"Invalid confidence: {body.get('minConfidence')}"})
            return

        with _scan_lock:
            if _scan_thread and _scan_thread.is_alive():
                self._send_json(409, {"status": "error", "message": "A scan is already running"})
                return

            _scan_cancelled.clear()
            _set_progress("starting", "Initializing scan...")

            _scan_thread = threading.Thread(target=_run_scan_async, args=(body,), daemon=True)
            _scan_thread.start()

        self._send_json(200, {"status": "ok", "message": "Scan started"})

    def _handle_progress(self):
        """Return current scan progress or final results."""
        global _scan_result, _scan_error, _scan_thread

        phase = _scan_progress.get("phase", "idle")

        if _scan_cancelled.is_set():
            self._send_json(200, {"status": "cancelled", "phase": "cancelled", "detail": "Scan cancelled"})
            return

        if phase == "done" and _scan_result:
            result = _scan_result
            _scan_result = None
            _set_progress("idle")
            self._send_json(200, result)
            return

        if phase == "error" and _scan_error:
            err = _scan_error
            _scan_error = None
            _set_progress("idle")
            self._send_json(200, {"status": "error", "message": err})
            return

        self._send_json(200, {
            "status": "scanning",
            "phase": _scan_progress.get("phase", "idle"),
            "detail": _scan_progress.get("detail", ""),
        })

    def _handle_cancel(self):
        """Cancel the running scan."""
        _scan_cancelled.set()
        _set_progress("cancelled", "Scan cancelled")
        self._send_json(200, {"status": "ok", "message": "Cancel requested"})

    def log_message(self, format, *args):
        """Suppress default request logging noise."""
        pass


def main():
    server = HTTPServer(("localhost", PORT), ScanHandler)
    server.daemon_threads = True
    url = f"http://localhost:{PORT}"
    print(f"Table Dependency Scanner running at {url}")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
