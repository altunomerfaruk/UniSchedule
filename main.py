"""Start the UniSchedule development servers from the project root."""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
SITE_URL = f"http://127.0.0.1:{FRONTEND_PORT}/"
API_HEALTH_PATH = "/api/health"
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimitInformation),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class ProcessJob:
    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, wintypes.INT, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def add(self, process: subprocess.Popen) -> None:
        if not self.kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def check_requirements() -> tuple[Path, str, Path]:
    python = BACKEND / ".venv" / "Scripts" / "python.exe"
    vite = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if not python.is_file():
        raise RuntimeError("Backend virtual environment missing. Run: cd backend; python -m venv .venv; .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    if not node:
        raise RuntimeError("Node.js is not on PATH. Install Node.js and reopen the terminal.")
    if not vite.is_file():
        raise RuntimeError("Frontend dependencies missing. Run: cd frontend; npm install")
    return python, node, vite


def port_in_use(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(0.3)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def app_is_ready(opener) -> bool:
    try:
        with opener.open(SITE_URL, timeout=1) as response:
            if response.status != 200 or b"<title>UniSchedule</title>" not in response.read():
                return False
        # Verify the browser's API route, including Vite's proxy to the backend.
        with opener.open(SITE_URL + API_HEALTH_PATH.lstrip("/"), timeout=1) as response:
            health = json.load(response)
            return response.status == 200 and isinstance(health, dict) and health.get("status") == "ok"
    except (OSError, ValueError):
        return False


def backend_file_times() -> dict[Path, int]:
    times = {}
    for path in (BACKEND / "app").rglob("*.py"):
        try:
            times[path] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue  # An editor may atomically replace a file during the scan.
    return times


def open_browser() -> None:
    try:
        if webbrowser.open(SITE_URL, new=2):
            return
    except (OSError, webbrowser.Error):
        pass
    print(f"Open UniSchedule at {SITE_URL}", file=sys.stderr, flush=True)


def start_backend(python: Path, job: ProcessJob) -> subprocess.Popen:
    process = subprocess.Popen(
        [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=BACKEND,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        job.add(process)
    except OSError:
        stop_processes([process], None)
        raise
    return process


def wait_until_ready(processes: list[subprocess.Popen], timeout: float = 45) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, process in zip(("backend", "frontend"), processes):
            if process.poll() is not None:
                raise RuntimeError(f"The {name} server exited with code {process.returncode}.")
        if app_is_ready(opener):
            return
        time.sleep(0.25)
    raise RuntimeError(f"The servers did not become ready within {timeout:g} seconds. Check the messages above.")


def stop_processes(processes: list[subprocess.Popen], job: ProcessJob | None) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except OSError:
                pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(process.poll() is None for process in processes):
        time.sleep(0.1)
    if job is not None:
        job.close()
    for process in processes:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Start UniSchedule backend and frontend development servers.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window after startup.")
    args = parser.parse_args()
    if os.name != "nt":
        print("This launcher is intended for Windows.", file=sys.stderr)
        return 1
    processes: list[subprocess.Popen] = []
    job = None
    try:
        occupied = [port for port in (BACKEND_PORT, FRONTEND_PORT) if port_in_use(port)]
        if occupied:
            if len(occupied) == 2 and app_is_ready(build_opener(ProxyHandler({}))):
                print(f"UniSchedule is already running: {SITE_URL}", flush=True)
                print("This session does not own the existing servers.", flush=True)
                if not args.no_browser:
                    open_browser()
                return 0
            raise RuntimeError(f"Port {occupied[0]} is already in use. Stop that server before starting UniSchedule.")
        python, node, vite = check_requirements()
        job = ProcessJob()
        file_times = backend_file_times()
        backend = start_backend(python, job)
        processes.append(backend)
        frontend = subprocess.Popen([node, str(vite), "--host", "127.0.0.1", "--port", str(FRONTEND_PORT), "--strictPort"], cwd=FRONTEND, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        processes.append(frontend)
        job.add(frontend)
        wait_until_ready(processes)
        print(f"UniSchedule ready: {SITE_URL}", flush=True)
        print(f"API documentation: http://127.0.0.1:{BACKEND_PORT}/docs", flush=True)
        if not args.no_browser:
            open_browser()
        print("Press Ctrl+C to stop both servers.", flush=True)
        backend_ready = True
        while frontend.poll() is None:
            current_times = backend_file_times()
            if current_times != file_times:
                print("Backend code changed; restarting the API...", flush=True)
                if backend.poll() is None:
                    stop_processes([backend], None)
                backend = start_backend(python, job)
                processes[0] = backend
                file_times = current_times
                try:
                    wait_until_ready(processes, timeout=20)
                    backend_ready = True
                    print("Backend reloaded.", flush=True)
                except RuntimeError as error:
                    backend_ready = False
                    if backend.poll() is None:
                        stop_processes([backend], None)
                    print(f"Backend reload failed. {error} Save a correction to retry.", file=sys.stderr, flush=True)
            if backend_ready and backend.poll() is not None:
                raise RuntimeError(f"The backend server exited with code {backend.returncode}.")
            time.sleep(0.5)
        raise RuntimeError(f"The frontend server exited with code {frontend.returncode}.")
    except KeyboardInterrupt:
        print("\nStopping UniSchedule...", flush=True)
        return 0
    except (OSError, RuntimeError) as error:
        print(f"UniSchedule could not start: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        stop_processes(processes, job)


if __name__ == "__main__":
    result = main()
    if sys.gettrace() is None:
        raise SystemExit(result)
