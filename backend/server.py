"""Standard-library REST server and UI audit store."""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .agent import run_conversation

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
history: list[dict] = []
history_lock = threading.RLock()


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, value: object):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("request body exceeds 100 KB")
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/agent/run" or path == "/api/examples/run":
                payload = self._body()
                if path == "/api/examples/run":
                    example_id = payload.get("id") if isinstance(payload, dict) else None
                    file = ROOT / "conversations" / f"{example_id}.json"
                    if not isinstance(example_id, str) or not example_id.startswith("cv_") or not file.is_file():
                        raise ValueError("id must name one of the supplied example conversations")
                    script = json.loads(file.read_text())
                    payload = {"conversation_id": script["id"], "today": script["today"], "turns": script["turns"]}
                result, events = run_conversation(payload)
                with history_lock:
                    record_id = f"run_{len(history) + 1:04d}"
                    record = {"id": record_id, "created_at": datetime.now(timezone.utc).isoformat(),
                              "turns": payload["turns"], "events": events, "result": result,
                              "resolved": False}
                    history.append(record)
                self._json(200, result if path == "/agent/run" else record)
                return
            if path.startswith("/api/handoffs/") and path.endswith("/resolve"):
                record_id = path.split("/")[3]
                with history_lock:
                    record = next((x for x in history if x["id"] == record_id), None)
                    if record is None or record["result"]["terminal_state"] != "escalated":
                        self._json(404, {"error": "handoff not found"})
                        return
                    record["resolved"] = True
                self._json(200, {"id": record_id, "resolved": True})
                return
            self._json(404, {"error": "route not found"})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            self._json(500, {"error": "internal server error"})

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/examples":
            examples = []
            for file in sorted((ROOT / "conversations").glob("*.json")):
                script = json.loads(file.read_text())
                examples.append({"id": script["id"], "description": script["description"]})
            self._json(200, examples)
            return
        if path == "/api/conversations":
            with history_lock:
                self._json(200, list(reversed(history)))
            return
        if path.startswith("/api/conversations/"):
            record_id = path.rsplit("/", 1)[-1]
            with history_lock:
                record = next((x for x in history if x["id"] == record_id), None)
                self._json(200, record) if record else self._json(404, {"error": "conversation not found"})
            return
        if path == "/api/stats":
            with history_lock:
                escalated = [x for x in history if x["result"]["terminal_state"] == "escalated"]
                self._json(200, {"conversations": len(history), "completed": len(history) - len(escalated),
                                 "escalated": len(escalated), "open": sum(not x["resolved"] for x in escalated),
                                 "urgent": sum(not x["resolved"] and x["result"]["escalation_reason"] == "clinical_urgent"
                                               for x in escalated)})
            return
        if path == "/api/health":
            self._json(200, {"ok": True})
            return
        target = DIST / path.lstrip("/")
        if path == "/" or not target.is_file() or DIST not in target.resolve().parents:
            target = DIST / "index.html"
        if not target.is_file():
            self._json(404, {"error": "frontend not built; run npm install and npm run build in frontend"})
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def serve(port: int | None = None, host: str | None = None):
    port = port if port is not None else int(os.environ.get("PORT", "8000"))
    host = host or ("0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SwasthiQ app listening on {host}:{port}", flush=True)
    server.serve_forever()
