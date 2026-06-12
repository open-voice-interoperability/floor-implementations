#!/usr/bin/env python3
"""OFP test harness entrypoint.

Default behavior launches the GUI harness.
CLI passthrough remains available as: `python ofp_test.py cli ...`
"""

import sys

from harness.cli import main as cli_main
from harness.gui import launch_gui


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        raise SystemExit(cli_main(sys.argv[2:]))
    raise SystemExit(launch_gui())
