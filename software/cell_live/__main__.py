"""python -m cell_live              the backend and the operator console at http://127.0.0.1:8765/
python -m cell_live --once       run every check once, print JSON, exit
python -m cell_live find-camera  list the camera indexes that open on this PC
python -m cell_live --host 0.0.0.0   also accept other computers (prints a warning)

The checks are read-only. Robot motion happens only in a run armed and started through the
safety gate (POST /api/run/arm, then /api/run/start); see control/.
"""

from __future__ import annotations

import argparse
import json
import sys

from .app import LiveApp
from .checks.camera import find_cameras
from .live_config import LiveConfigError
from .server import LOCAL_CLIENTS, make_server

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["find-camera"]:
        try:
            print(json.dumps(find_cameras(), indent=2))
        except ImportError:
            print("opencv is missing. Install it with: python -m pip install opencv-python", file=sys.stderr)
            return 1
        return 0
    parser = argparse.ArgumentParser(prog="python -m cell_live", description="Live checks, real control and the operator console.")
    parser.add_argument("--config", help="path to live_config.json")
    parser.add_argument("--once", action="store_true", help="run every check once, print JSON, exit")
    parser.add_argument("--port", type=int, help="server port (default: server.port in live_config.json)")
    parser.add_argument("--host", help="bind address; anything but 127.0.0.1 also lets other computers send run commands")
    args = parser.parse_args(argv)
    remote = args.host is not None and args.host not in LOOPBACK_HOSTS
    try:
        app = LiveApp(args.config, allow_remote_control=remote)
    except LiveConfigError as error:
        print(f"live_config.json error: {error}", file=sys.stderr)
        return 1
    if args.once:
        for component_id in app.poller.checks:
            app.poller.check_now(component_id)
        print(json.dumps({"components": app.poller.snapshot(), "unconfirmed_config": app.unknowns()}, indent=2))
        return 0
    host = args.host or app.config.value("server", "host")
    port = args.port or app.config.value("server", "port")
    if remote:
        print(f"[cell_live] WARNING: listening on {host}: other computers can see the cell AND send run, stop and "
              f"settings requests. Without --host only this PC ({', '.join(LOCAL_CLIENTS[:2])}) can.", flush=True)
    server = make_server(app.poller, host, port, context=app)
    app.start()
    print(f"[cell_live] operator console: http://127.0.0.1:{port}/  (API under /api). "
          "A real run starts only through Arm + Start (safety gate). Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
