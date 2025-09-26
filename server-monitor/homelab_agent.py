#!/usr/bin/env python3
"""
Homelab Agent
- Reads secrets/config from a .env file
- Gathers machine metrics
- Upserts to FastAPI /machines via form-encoded POST
- Intended to run as a background service (systemd)

Requires:
  pip install psutil requests python-dotenv
"""

from __future__ import annotations

import os
import time
import socket
import signal
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict

import psutil
import requests
from dotenv import load_dotenv


# ----------------------------
# config / env
# ----------------------------
def load_config() -> Dict[str, str]:
    # Try local .env first, then /etc/homelab-agent/.env
    if os.path.exists(".env"):
        load_dotenv(".env")
    else:
        load_dotenv("/etc/homelab-agent/.env")

    cfg = {
        "SERVER_URL": os.getenv("SERVER_URL", "http://127.0.0.1:8000"),
        "MACHINE_ID": os.getenv("MACHINE_ID", socket.gethostname()),
        "MACHINE_NAME": os.getenv("MACHINE_NAME", socket.gethostname()),
        "POST_PATH": os.getenv("POST_PATH", "/machines"),
        "SLEEP_SECONDS": os.getenv("SLEEP_SECONDS", "15"),
        "REQUEST_TIMEOUT": os.getenv("REQUEST_TIMEOUT", "5"),
        "DISK_PATH": os.getenv("DISK_PATH", "/"),  # which mount to measure
        "LOG_FILE": os.getenv("LOG_FILE", "/var/log/homelab-agent.log"),
    }
    # basic sanitize
    try:
        int(cfg["SLEEP_SECONDS"])
        int(cfg["REQUEST_TIMEOUT"])
    except ValueError:
        cfg["SLEEP_SECONDS"] = "15"
        cfg["REQUEST_TIMEOUT"] = "5"
    return cfg


# ----------------------------
# logging
# ----------------------------
def build_logger(log_file: str) -> logging.Logger:
    logger = logging.getLogger("homelab_agent")
    logger.setLevel(logging.INFO)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Also log to stdout (optional; systemd will capture it)
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


# ----------------------------
# metrics
# ----------------------------
def get_cpu_cores() -> int:
    return os.cpu_count() or 1


def get_ram_bytes() -> tuple[int, int]:
    vm = psutil.virtual_memory()
    return int(vm.used), int(vm.total)


def get_disk_bytes(path: str = "/") -> tuple[int, int]:
    du = psutil.disk_usage(path)
    return int(du.used), int(du.total)


def get_cpu_temp_c() -> float:
    """
    Best-effort average CPU temperature (°C).
    Returns NaN if not available.
    """
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
        if not temps:
            return float("nan")
        # Heuristics: prefer 'coretemp', else take average of the first group
        if "coretemp" in temps and temps["coretemp"]:
            vals = [t.current for t in temps["coretemp"] if t.current is not None]
        else:
            first_key = next(iter(temps))
            vals = [t.current for t in temps[first_key] if t.current is not None]
        return float(sum(vals) / max(1, len(vals))) if vals else float("nan")
    except Exception:
        return float("nan")


def get_net_bytes_total() -> int:
    io = psutil.net_io_counters()
    return int(io.bytes_sent + io.bytes_recv)


# ----------------------------
# http
# ----------------------------
def post_metrics(
    base_url: str,
    path: str,
    payload: Dict[str, str | int | float],
    timeout: int,
    logger: logging.Logger,
) -> None:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        # Your FastAPI route expects form fields (Form(...)), so use data=
        resp = requests.post(url, data=payload, timeout=timeout)
        if resp.status_code >= 400:
            logger.warning("POST %s -> %s %s", url, resp.status_code, resp.text[:200])
        else:
            logger.info("POST %s -> %s", url, resp.status_code)
    except Exception as e:
        logger.error("POST %s failed: %s", url, e)


# ----------------------------
# main loop
# ----------------------------
_SHOULD_STOP = False


def _signal_handler(signum, frame):
    global _SHOULD_STOP
    _SHOULD_STOP = True


def main():
    cfg = load_config()
    logger = build_logger(cfg["LOG_FILE"])
    logger.info("homelab-agent starting")

    # signals
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    sleep_seconds = int(cfg["SLEEP_SECONDS"])
    timeout = int(cfg["REQUEST_TIMEOUT"])
    disk_path = cfg["DISK_PATH"]

    # Seed network counters
    prev = get_net_bytes_total()
    prev_t = time.time()

    while not _SHOULD_STOP:
        try:
            now = time.time()
            total_now = get_net_bytes_total()
            dt = max(1e-6, now - prev_t)
            net_bps = (total_now - prev) / dt  # bytes per second
            prev, prev_t = total_now, now

            payload = {
                "MACHINE_ID": cfg["MACHINE_ID"],
                "MACHINE_NAME": cfg["MACHINE_NAME"],
                "CPU_CORES": get_cpu_cores(),
                "RAM_USED": get_ram_bytes()[0],
                "RAM_TOTAL": get_ram_bytes()[1],
                "STORAGE_USED": get_disk_bytes(disk_path)[0],
                "STORAGE_TOTAL": get_disk_bytes(disk_path)[1],
                "CPU_TEMPS": round(get_cpu_temp_c(), 2),
                "NETWORK_USAGE": int(net_bps),
            }

            post_metrics(cfg["SERVER_URL"], cfg["POST_PATH"], payload, timeout, logger)
        except Exception as e:
            logger.exception("Loop error: %s", e)

        for _ in range(sleep_seconds):
            if _SHOULD_STOP:
                break
            time.sleep(1)

    logger.info("homelab-agent stopping")


if __name__ == "__main__":
    main()
