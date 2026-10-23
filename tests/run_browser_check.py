"""Start an isolated backend, run Playwright, then terminate only that child."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 8002)) == 0:
            raise SystemExit('Port 8002 is occupied. Stop your previous test backend first.')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    server = subprocess.Popen([sys.executable, '-m', 'examples.frontend_test_server'],
                              cwd=root, creationflags=flags)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError('Disposable backend exited before listening')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1', 8002)) == 0:
                    break
            time.sleep(.25)
        else:
            raise RuntimeError('Disposable backend startup timed out')
        result = subprocess.run([sys.executable, 'tests/browser_check.py', *sys.argv[1:]], cwd=root)
        if result.returncode == 0:
            result = subprocess.run([sys.executable, 'tests/account_browser_check.py'], cwd=root)
        if result.returncode == 0:
            result = subprocess.run([sys.executable, 'tests/real_data_browser_check.py'], cwd=root)
        if result.returncode == 0:
            result = subprocess.run([sys.executable, 'tests/map_consistency_check.py'], cwd=root)
        raise SystemExit(result.returncode)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
