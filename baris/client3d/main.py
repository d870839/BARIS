"""Entry point for the 3D BARIS client. Spins up an Ursina app and
instantiates BarisClient, which owns the scene and the network loop."""
from __future__ import annotations

import argparse
import logging

from ursina import Ursina

from baris.client3d.app import BarisClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="ws://localhost:8765")
    parser.add_argument("--name", default="Player")
    parser.add_argument("--auto-ready", action="store_true",
                        help="Skip the lobby — send READY automatically right "
                             "after joining. Handy for single-machine dev when "
                             "alt-tabbing between two windows to ready up is "
                             "annoying.")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = Ursina(title="BARIS 3D — Race Into Space", borderless=False)
    BarisClient(args.server, args.name, auto_ready=args.auto_ready)
    app.run()


if __name__ == "__main__":
    main()
