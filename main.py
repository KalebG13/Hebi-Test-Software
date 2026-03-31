from __future__ import annotations

import sys
from pathlib import Path


def _print_missing_dependency_help(package_name: str) -> None:
    project_root = Path(__file__).resolve().parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    print(
        f"Missing dependency: {package_name}\n"
        f"This project uses a local virtual environment.\n\n"
        f"Use one of these commands from:\n"
        f"{project_root}\n\n"
        f"1. {venv_python} main.py\n"
        f"2. .\\.venv\\Scripts\\Activate.ps1\n"
        f"   python main.py",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        from wheel_test_app.main_window import run
    except ModuleNotFoundError as exc:
        if exc.name in {"PySide6", "hebi", "numpy"}:
            _print_missing_dependency_help(exc.name)
            raise SystemExit(1) from exc
        raise

    run()
