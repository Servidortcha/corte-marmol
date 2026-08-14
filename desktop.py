"""App de escritorio: abre la optimizacion en una ventana nativa (Windows).

Uso:  .venv\\Scripts\\python.exe desktop.py
Para compilar el .exe:  build_desktop.bat
"""

import socket
import threading
import time

import uvicorn
import webview

from app import app

_START_PORT = 8765


def _free_port():
    for port in range(_START_PORT, _START_PORT + 20):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return _START_PORT


def main():
    port = _free_port()
    server = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"},
        daemon=True,
    )
    server.start()
    time.sleep(1.5)
    webview.create_window(
        "La Puntual Marmolería",
        f"http://127.0.0.1:{port}",
        width=1280,
        height=820,
        min_size=(940, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
