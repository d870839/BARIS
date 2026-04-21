"""Dev launcher: one terminal, one command — spawns the server + both
pygame clients as subprocesses. Output is interleaved to the parent
terminal; Ctrl+C shuts everything down cleanly.

Usage:
    python -m baris.dev                    # normal: Alice + Bob join a fresh game
    python -m baris.dev --debug            # preseed players with fat budget and Apollo/Soyuz unlocked
    python -m baris.dev --mode 3d --debug  # launch the Ursina 3D clients instead of the 2D pygame ones
    python -m baris.dev --port 9000 --names Red Blue
    python -m baris.dev --clients 0        # launch only the server (test with your own clients)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def _find_python(root: Path) -> str:
    """Prefer the project venv's Python so subprocesses have pygame etc.
    Falls back to the current interpreter if no venv is found."""
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",  # Windows
        root / ".venv" / "bin" / "python",          # Unix
        root / "venv"  / "Scripts" / "python.exe",
        root / "venv"  / "bin" / "python",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return sys.executable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true",
                        help="Server preseeds players with full kit when the game starts.")
    parser.add_argument("--mode", choices=["2d", "3d"], default="2d",
                        help="Which client to spawn. '2d' = pygame (default), "
                             "'3d' = Ursina first-person facility. Requires the "
                             "3d deps: pip install -r requirements-3d.txt.")
    parser.add_argument("--names", nargs="*", default=["Alice", "Bob"],
                        help="Client display names. Length drives number of clients unless --clients overrides.")
    parser.add_argument("--clients", type=int, default=None,
                        help="How many clients to spawn. Defaults to len(--names). Use 0 to launch only the server.")
    parser.add_argument("--python", default=None,
                        help="Python interpreter to launch subprocesses with. Default: project .venv if present, else this interpreter.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    python = args.python or _find_python(root)
    url = f"ws://localhost:{args.port}"
    n_clients = args.clients if args.clients is not None else len(args.names)
    client_module = "baris.client3d.main" if args.mode == "3d" else "baris.client.main"

    if python != sys.executable:
        print(f"[dev] using interpreter: {python}")

    server_cmd = [python, "-m", "baris.server.main", "--port", str(args.port)]
    if args.debug:
        server_cmd.append("--debug")

    procs: list[subprocess.Popen] = []
    try:
        print(f"[dev] starting server on {url} "
              f"(debug={args.debug}, mode={args.mode})...")
        procs.append(subprocess.Popen(server_cmd, cwd=root))
        time.sleep(0.7)  # let the server bind the port before clients dial it

        for i in range(n_clients):
            name = args.names[i] if i < len(args.names) else f"Player{i + 1}"
            print(f"[dev] starting {args.mode} client: {name}")
            procs.append(subprocess.Popen(
                [python, "-m", client_module, "--server", url, "--name", name],
                cwd=root,
            ))
            time.sleep(0.3)

        print("[dev] all launched. Close any window or hit Ctrl+C here to shut everything down.")
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"[dev] process {p.pid} exited; shutting down the rest...")
                    return
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[dev] Ctrl+C — stopping all processes...")
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        deadline = time.time() + 3.0
        for p in procs:
            remain = max(0.0, deadline - time.time())
            try:
                p.wait(timeout=remain)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
