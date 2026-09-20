"""Start built web/API servers, check HTTP, and stop only our process groups."""

import os
import signal
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def main() -> None:
    servers = [
        (
            [sys.executable, "-m", "uvicorn", "ranah_api.main:app", "--port", "18000"],
            "http://127.0.0.1:18000/health",
            b'"status":"ok"',
        ),
        (
            [
                "node",
                "node_modules/next/dist/bin/next",
                "start",
                "apps/web",
                "--port",
                "13000",
                "--hostname",
                "127.0.0.1",
            ],
            "http://127.0.0.1:13000",
            b"RanahResearch",
        ),
    ]
    for command, url, expected in servers:
        process = subprocess.Popen(command, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited: {command}")
                try:
                    with urlopen(url, timeout=1) as response:
                        assert response.status == 200
                        assert expected in response.read()
                    print(f"PASS {url}", flush=True)
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.2)
            else:
                raise TimeoutError(f"Server never became ready: {url}")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == "__main__":
    main()
