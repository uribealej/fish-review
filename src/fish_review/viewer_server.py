"""Serve registered generated viewers locally without copying HTML into Streamlit messages."""
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import shutil
import threading
from urllib.parse import urlsplit


class ViewerServer:
    def __init__(self):
        self._paths = {}
        self._tokens = {}
        self._lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self._serve(False)

            def do_GET(self):
                self._serve(True)

            def _serve(self, body):
                route = urlsplit(self.path).path
                with owner._lock:
                    path = owner._paths.get(route)
                if path is None:
                    self.send_error(404)
                    return
                try:
                    handle = path.open("rb")
                except OSError:
                    self.send_error(404)
                    return
                with handle:
                    import os
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(os.fstat(handle.fileno()).st_size))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    if body:
                        try:
                            shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)
                        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                            pass

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._http.serve_forever, daemon=True)
        self._thread.start()

    def register(self, path):
        path = Path(path).resolve(strict=True)
        if not path.is_file() or not path.name.endswith("_raw_fluorescence.html"):
            raise ValueError("Only generated raw-fluorescence HTML viewers can be registered.")
        with self._lock:
            if path not in self._tokens:
                route = "/viewer/" + secrets.token_urlsafe(32)
                self._tokens[path] = route
                self._paths[route] = path
            route = self._tokens[path]
        return f"http://127.0.0.1:{self._http.server_port}{route}?v={path.stat().st_mtime_ns}"

    def close(self):
        self._http.shutdown()
        self._http.server_close()
        self._thread.join(timeout=2)


@lru_cache(maxsize=1)
def local_viewer_server():
    """One loopback server per app process, retained across Streamlit reruns."""
    return ViewerServer()
