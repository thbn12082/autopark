"""Durable Windows supervisor for the user-authorized full dataset download.

Adopt already running workers, restart interrupted workers with bounded retries,
and let the verifier/extractor finish without keeping the chat turn open.
"""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
LOGS = ROOT / "download_metadata"
LOGS.mkdir(exist_ok=True)
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel.WaitForSingleObject.restype = wintypes.DWORD
kernel.CloseHandle.argtypes = [wintypes.HANDLE]

COMMANDS = {
    "full": ["datasets/download_full.py", "datasets/full_download_jobs.json", "--workers", "8"],
    "acdc": ["datasets/download_acdc.py"],
    "watch": ["datasets/watch_full_downloads.py"],
}
EXPECTED = {
    "full": [j["name"] for j in json.loads((ROOT / "full_download_jobs.json").read_text())],
    "acdc": ["acdc_gt_trainval.zip", "acdc_gt_trainval_ref.zip", "acdc_rgb_anon_trainvaltest.zip"],
}


def complete(role):
    if role == "watch":
        path = ROOT / "full_dataset_inventory.json"
        return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("complete", False)
    for name in EXPECTED[role]:
        path = ROOT / "raw/full" / name
        meta = path.with_suffix(".zip.json")
        if not path.exists() or not meta.exists():
            return False
        if json.loads(meta.read_text(encoding="utf-8")).get("status") != "verified":
            return False
    return True


def save_state(status, roles):
    state = {"status": status, "updated_utc": datetime.now(timezone.utc).isoformat(),
             "supervisor_pid": __import__('os').getpid(),
             "roles": {key: {k: v for k, v in value.items() if k not in ("handle", "process")}
                       for key, value in roles.items()}}
    tmp = LOGS / "supervisor_state.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LOGS / "supervisor_state.json")


def main():
    adopted = json.loads((LOGS / "adopt_workers.json").read_text(encoding="utf-8-sig"))
    roles = {}
    for name in COMMANDS:
        pid = adopted.get(name)
        handle = kernel.OpenProcess(0x00100000, False, pid) if pid else None
        roles[name] = {"pid": pid, "handle": handle, "restarts": 0, "status": "adopted"}
    while True:
        if all(complete(role) for role in COMMANDS):
            save_state("complete", roles)
            print("All authorized downloads verified and extracted", flush=True)
            return
        exhausted = False
        for name, command in COMMANDS.items():
            role = roles[name]
            if complete(name):
                role["status"] = "complete"
                continue
            alive = role["handle"] and kernel.WaitForSingleObject(role["handle"], 0) == 258
            if alive:
                role["status"] = "running"
                continue
            if role["handle"]:
                kernel.CloseHandle(role["handle"])
                role["handle"] = None
            if role["restarts"] >= 3:
                role["status"] = "failed_after_retries"
                exhausted = True
                continue
            role["restarts"] += 1
            with (LOGS / (name + "_worker.log")).open("a", encoding="utf-8") as log:
                process = subprocess.Popen([sys.executable, "-X", "utf8", *command], cwd=PROJECT,
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
            role.update(pid=process.pid, handle=kernel.OpenProcess(0x00100000, False, process.pid),
                        status="restarted", process=process)
            print("Started", name, process.pid, flush=True)
        save_state("needs_attention" if exhausted else "running", roles)
        if exhausted and all(complete(name) or roles[name]["status"] == "failed_after_retries"
                             for name in ("full", "acdc")):
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
