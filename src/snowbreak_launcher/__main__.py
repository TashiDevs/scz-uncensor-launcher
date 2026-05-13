from __future__ import annotations

import sys


def main() -> int:
    if "--smoke-test" in sys.argv:
        return 0

    if "--apply-update" in sys.argv:
        from snowbreak_launcher.self_update import apply_self_update_from_args

        return apply_self_update_from_args(sys.argv[1:])

    try:
        from snowbreak_launcher.app import SnowbreakLauncherApp, create_application
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print("PySide6 is not installed yet. Run: python -m pip install -r requirements.txt")
            return 1
        raise

    qt_app = create_application(sys.argv)
    window = SnowbreakLauncherApp()
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
