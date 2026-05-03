import threading
import webbrowser
import uvicorn

PORT = 8000
URL = f"http://localhost:{PORT}/"


def open_browser():
    webbrowser.open(URL)


if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()

    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=PORT,
        reload=True,
    )