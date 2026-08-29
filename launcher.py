import faulthandler
import os
import sys
import tempfile
import traceback

_CRASH_LOG = None


def _install_crash_log() -> None:
    global _CRASH_LOG
    try:
        path = os.path.join(tempfile.gettempdir(), "DapFlashTool_crash.log")
        _CRASH_LOG = open(path, "a", encoding="utf-8")
        faulthandler.enable(_CRASH_LOG, all_threads=True)

        def excepthook(exc_type, exc, tb) -> None:
            traceback.print_exception(exc_type, exc, tb, file=_CRASH_LOG)
            _CRASH_LOG.flush()
            sys.__excepthook__(exc_type, exc, tb)

        sys.excepthook = excepthook
    except Exception:
        _CRASH_LOG = None


def main() -> int:
    _install_crash_log()
    from dap_flash_tool.app import main as app_main

    return app_main()


if __name__ == "__main__":
    raise SystemExit(main())
