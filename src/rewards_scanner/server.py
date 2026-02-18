"""HTTP server frontend for the table dependency scanner."""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict

from .inflection import singularize
from .models import Confidence, ScanResult
from .output import write_csv
from .repo import cleanup, clone_repo
from .runner import run_scan

STATIC_DIR = Path(__file__).parent / "static"
PORT = 8642


class ScanHandler(SimpleHTTPRequestHandler):
    """Handle API routes and serve static files."""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        elif self.path.startswith("/api/browse"):
            self._handle_browse()
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        if self.path == "/api/scan":
            self._handle_scan()
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
        """Run a scan and return JSON results."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"status": "error", "message": f"Invalid JSON: {e}"})
            return

        source = body.get("source", "local")
        repo = body.get("repo", "")
        local_path = body.get("localPath", "")
        table_name = body.get("tableName", "rewards")
        pk_column = body.get("pkColumn", "id")
        min_confidence_str = body.get("minConfidence", "LOW")
        output_path = body.get("outputPath", "")
        strict_mode = bool(body.get("strictMode", False))

        try:
            min_confidence = Confidence[min_confidence_str]
        except KeyError:
            self._send_json(400, {"status": "error", "message": f"Invalid confidence: {min_confidence_str}"})
            return

        cloned_path = None
        try:
            if source == "github":
                if not repo:
                    self._send_json(400, {"status": "error", "message": "repo is required for GitHub source"})
                    return
                repo_path = clone_repo(repo)
                cloned_path = repo_path.parent
            else:
                if not local_path:
                    self._send_json(400, {"status": "error", "message": "localPath is required for local source"})
                    return
                repo_path = Path(local_path)
                if not repo_path.is_dir():
                    self._send_json(400, {"status": "error", "message": f"Not a directory: {local_path}"})
                    return

            # Derive FK column: singular form of table + "_" + pk (e.g. rewards + id -> reward_id)
            singular = singularize(table_name)
            fk_column = f"{singular}_{pk_column}" if pk_column else ""
            scan_data = run_scan(
                repo_path, table_name, min_confidence,
                fk_column=fk_column, strict_mode=strict_mode,
            )
            results = scan_data["results"]
            stats = scan_data["stats"]

            # Optionally write CSV
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

            self._send_json(200, {
                "status": "ok",
                "results": results_json,
                "stats": stats,
                "message": f"Found {len(results_json)} results",
            })

        except Exception as e:
            self._send_json(500, {"status": "error", "message": str(e)})
        finally:
            if cloned_path:
                cleanup(cloned_path)

    def log_message(self, format, *args):
        """Suppress default request logging noise."""
        pass


def main():
    server = HTTPServer(("localhost", PORT), ScanHandler)
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
