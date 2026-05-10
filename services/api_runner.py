# services/api_runner.py
import socket
import threading
import time
import traceback
import uvicorn

from services.api_server import app


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalAPIRunner:
    def __init__(self):
        self.port: int | None = None
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None
        self.last_error: str | None = None

    def start(self) -> int:
        # zaten çalışıyorsa portu geri ver
        if self._thread and self._thread.is_alive() and self.port:
            return self.port

        self.port = _find_free_port()

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",  # "info" yaparsan daha çok log alırsın
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        def run():
            try:
                self._server.run()
            except Exception:
                self.last_error = traceback.format_exc()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

        # thread ayağa kalksın
        time.sleep(0.2)
        return self.port

    def stop(self):
        if self._server:
            self._server.should_exit = True
