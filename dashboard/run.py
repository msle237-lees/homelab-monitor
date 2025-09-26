#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import platform
import signal
import sys
from pathlib import Path
from typing import Optional, Tuple, List

ROOT = Path(__file__).resolve().parent
DB_DIR = ROOT / "db_manager"
TUI_DIR = ROOT / "textual"

def venv_python(venv_dir: Path) -> Path:
    if platform.system().lower() == "windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"

def first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.is_dir():
            py = venv_python(p)
            if py.exists():
                return py
    return None

def ensure_logs_dir() -> Path:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    return logs

async def _pipe_stream(reader: asyncio.StreamReader, prefix: str, tee_file):
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            print(f"[{prefix}] {text}")
            if tee_file:
                tee_file.write(text + "\n")
                tee_file.flush()
    except Exception as e:
        print(f"[{prefix}] stream error: {e}")

async def spawn_process(
    cmd: List[str],
    cwd: Path,
    env: Optional[dict] = None,
    log_prefix: str = "proc",
    log_file: Optional[Path] = None,
) -> Tuple[asyncio.subprocess.Process, asyncio.Task, asyncio.Task]:
    tee = open(log_file, "a", buffering=1) if log_file else None
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_task = asyncio.create_task(_pipe_stream(proc.stdout, f"{log_prefix}:out", tee))
    stderr_task = asyncio.create_task(_pipe_stream(proc.stderr, f"{log_prefix}:err", tee))
    return proc, stdout_task, stderr_task

async def terminate_process(proc: asyncio.subprocess.Process, name: str, grace: float = 5.0):
    if proc is None or proc.returncode is not None:
        return
    try:
        print(f"[{name}] terminating…")
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace)
        print(f"[{name}] exited with {proc.returncode}")
    except asyncio.TimeoutError:
        print(f"[{name}] kill (timeout)")
        proc.kill()

async def wait_for_http(url: str, timeout: float = 20.0, interval: float = 0.5) -> bool:
    import urllib.request, urllib.error
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if 200 <= resp.status < 300:
                    return True
        except urllib.error.URLError:
            pass
        await asyncio.sleep(interval)
    return False

async def main():
    parser = argparse.ArgumentParser(description="Run homelab-monitor stack")
    parser.add_argument("--no-api", action="store_true", help="Do not start FastAPI server")
    parser.add_argument("--no-ui", action="store_true", help="Do not start Textual UI")
    parser.add_argument("--api-host", default="127.0.0.1", help="API host (default: 127.0.0.1)")
    parser.add_argument("--api-port", default="8000", help="API port (default: 8000)")
    parser.add_argument("--refresh-seconds", default=None, help="Override HOMELAB_REFRESH_SECONDS for TUI")
    args = parser.parse_args()

    logs_dir = ensure_logs_dir()

    db_python = first_existing([DB_DIR / "db-venv", DB_DIR / "venv"])
    tui_python = first_existing([TUI_DIR / "textual-venv"])

    if not args.no_api and not db_python:
        print("ERROR: Could not find a Python in db_manager venv (db-venv/ or venv/).")
        sys.exit(1)
    if not args.no_ui and not tui_python:
        print("ERROR: Could not find a Python in textual venv (textual-venv/).")
        sys.exit(1)

    api_proc = api_t_out = api_t_err = None
    tui_proc = tui_t_out = tui_t_err = None

    stop_event = asyncio.Event()

    def handle_sig():
        stop_event.set()

    loop = asyncio.get_event_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, handle_sig)
        loop.add_signal_handler(signal.SIGTERM, handle_sig)
    except NotImplementedError:
        pass

    try:
        # Start API
        api_url = f"http://{args.api_host}:{args.api_port}"
        if not args.no_api:
            api_cmd = [
                str(db_python),
                "-m",
                "uvicorn",
                "run:app",
                "--host", args.api_host,
                "--port", str(args.api_port),
                "--reload",
            ]
            api_proc, api_t_out, api_t_err = await spawn_process(
                api_cmd, cwd=DB_DIR, env=os.environ.copy(),
                log_prefix="api", log_file=logs_dir / "api.log"
            )
            print(f"[api] started pid={api_proc.pid} at {api_url}")
            if not await wait_for_http(f"{api_url}/"):
                print("[api] did not become healthy in time; continuing anyway…")

        # Start TUI
        if not args.no_ui:
            tui_env = os.environ.copy()
            tui_env["HOMELAB_API_URL"] = api_url
            if args.refresh_seconds is not None:
                tui_env["HOMELAB_REFRESH_SECONDS"] = str(args.refresh_seconds)

            tui_cmd = [str(tui_python), "app.py"]
            tui_proc, tui_t_out, tui_t_err = await spawn_process(
                tui_cmd, cwd=TUI_DIR, env=tui_env,
                log_prefix="tui", log_file=logs_dir / "tui.log"
            )
            print(f"[tui] started pid={tui_proc.pid} (HOMELAB_API_URL={tui_env['HOMELAB_API_URL']})")

        # ---------- FIXED WAIT LOOP: wrap waits in Tasks ----------
        async def make_task_or_none(coro):
            return asyncio.create_task(coro) if coro is not None else None

        api_wait_task = await make_task_or_none(api_proc.wait() if (api_proc and not args.no_api) else None)
        tui_wait_task = await make_task_or_none(tui_proc.wait() if (tui_proc and not args.no_ui) else None)
        stop_task = asyncio.create_task(stop_event.wait())

        def active_tasks():
            return {t for t in (api_wait_task, tui_wait_task, stop_task) if t is not None and not t.done()}

        if args.no_api and not args.no_ui:
            await tui_wait_task
        elif not args.no_api and args.no_ui:
            await api_wait_task
        else:
            # Both running: wait until any of them completes or we receive a signal
            while True:
                tasks = active_tasks()
                if not tasks:
                    break
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if stop_task in done:
                    break
                # If either child exits, stop the loop and begin shutdown
                if api_wait_task in done or tui_wait_task in done:
                    break

    finally:
        # Shutdown in reverse order: UI then API
        if tui_proc and tui_proc.returncode is None:
            await terminate_process(tui_proc, "tui")
        if api_proc and api_proc.returncode is None:
            await terminate_process(api_proc, "api")

        # Cancel any pending wait/pipe tasks
        for t in (api_t_out, api_t_err, tui_t_out, tui_t_err):
            if t and not t.done():
                t.cancel()

        # Also cancel stop_task / api_wait_task / tui_wait_task if they exist
        for t in tuple(
            filter(
                None,
                (locals().get(n, None) for n in ["stop_task", "api_wait_task", "tui_wait_task"]),
            )
        ):
            try:
                if t and not t.done():
                    t.cancel()
            except Exception:
                pass

        print("All done.")


if __name__ == "__main__":
    asyncio.run(main())
