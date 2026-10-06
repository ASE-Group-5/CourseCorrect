#!/usr/bin/env python3
"""Cross-platform developer helper used by the VS Code tasks and launch configs (automates running the projects).

Usage: python scripts/dev.py <command>

Commands:
    setup      Create the root .venv, install requirements, create .env files.
    migrate    Apply database migrations (alembic upgrade head).
    prepare    setup + migrate (what the Run/Debug button runs first).
    backend    Run the FastAPI server with auto-reload on port 8000.
    frontend   Run the Streamlit app on port 8501.
    test       Run the backend pytest suite.
    revision   Create a new migration: dev.py revision "message".
    format     Format and lint-fix the whole project with ruff.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
STAMP = VENV / ".requirements.sha256"
REQUIREMENT_FILES = [
    BACKEND / "requirements.txt",
    FRONTEND / "requirements.txt",
    ROOT / "requirements-dev.txt",
]
MIN_PYTHON = (3, 10)


def venv_python() -> Path:
    """Returns the path to the venv's Python interpreter."""
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def info(message: str) -> None:
    print(f"[dev] {message}", flush=True)


def fail(message: str) -> None:
    print(f"\n[dev] [!] {message}\n", file=sys.stderr, flush=True)
    sys.exit(1)


def load_env_file(path: Path) -> dict[str, str]:
    """Parses a simple KEY=VALUE .env file (comments and blanks ignored)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def run(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> int:
    """Runs a command to completion and returns its exit code."""
    merged = {**os.environ, **(env or {})}
    try:
        return subprocess.call(command, cwd=cwd, env=merged)
    except KeyboardInterrupt:
        return 0


def run_foreground(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> None:
    """Runs a long-lived server, replacing this process where possible."""
    merged = {**os.environ, **(env or {})}
    os.chdir(cwd)
    if os.name == "nt":
        sys.exit(run(command, cwd, env))
    os.execve(command[0], command, merged)


def require_venv() -> Path:
    python = venv_python()
    if not python.exists():
        fail(
            "Virtual environment not found. Run the 'Setup' task first "
            "(Terminal > Run Task > Setup) or press F5."
        )
    return python


def cmd_setup() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
            f"(found {sys.version.split()[0]})."
        )

    if not venv_python().exists():
        info("Creating virtual environment at .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV)])

    digest = hashlib.sha256()
    for requirements in REQUIREMENT_FILES:
        digest.update(requirements.read_bytes())
    current = digest.hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == current:
        info("Dependencies already up to date.")
    else:
        info("Installing dependencies (first run takes a minute or two) ...")
        python = str(venv_python())
        for requirements in REQUIREMENT_FILES:
            code = run(
                [python, "-m", "pip", "install", "-q", "-r", str(requirements)],
                ROOT,
            )
            if code != 0:
                fail(f"pip failed installing {requirements.name}.")
        STAMP.write_text(current)
        info("Dependencies installed.")

    for folder in (BACKEND, FRONTEND):
        example, target = folder / ".env.example", folder / ".env"
        if not target.exists():
            shutil.copy(example, target)
            info(f"Created {target.relative_to(ROOT)} from .env.example")


def database_ready() -> bool:
    url = load_env_file(BACKEND / ".env").get("DATABASE_URL", "")
    if "USER:PASSWORD" in url:
        print(
            "\n[dev] [!] backend/.env still contains the placeholder database "
            "URLs.\n"
            "      1. Open backend/.env\n"
            "      2. Paste your Neon DATABASE_URL and DATABASE_URL_DIRECT\n"
            "         (or delete both lines to use a local SQLite file)\n"
            "      3. Press F5 again.\n",
            file=sys.stderr,
            flush=True,
        )
        return False
    return True


def cmd_migrate() -> None:
    python = require_venv()
    if not database_ready():
        sys.exit(1)
    info("Applying database migrations ...")
    code = run([str(python), "-m", "alembic", "upgrade", "head"], BACKEND)
    if code != 0:
        fail(
            "Migration failed. Check your DATABASE_URL_DIRECT in "
            "backend/.env and your internet connection."
        )
    info("Database is up to date.")


def cmd_prepare() -> None:
    cmd_setup()
    cmd_migrate()


def cmd_backend() -> None:
    python = require_venv()
    run_foreground(
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            "8000",
        ],
        BACKEND,
    )


def cmd_frontend() -> None:
    python = require_venv()
    env = load_env_file(FRONTEND / ".env")
    run_foreground(
        [
            str(python),
            "-m",
            "streamlit",
            "run",
            "app.py",
            "--server.port",
            "8501",
        ],
        FRONTEND,
        env,
    )


def cmd_test() -> None:
    python = require_venv()
    sys.exit(run([str(python), "-m", "pytest"], BACKEND))


def cmd_revision(message: str) -> None:
    python = require_venv()
    if not message.strip():
        fail("A migration message is required.")
    if not database_ready():
        sys.exit(1)
    sys.exit(
        run(
            [
                str(python),
                "-m",
                "alembic",
                "revision",
                "--autogenerate",
                "-m",
                message,
            ],
            BACKEND,
        )
    )


def cmd_format() -> None:
    python = str(require_venv())
    run([python, "-m", "ruff", "check", "--fix", "."], ROOT)
    sys.exit(run([python, "-m", "ruff", "format", "."], ROOT))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    command = sys.argv[1]
    commands = {
        "setup": cmd_setup,
        "migrate": cmd_migrate,
        "prepare": cmd_prepare,
        "backend": cmd_backend,
        "frontend": cmd_frontend,
        "test": cmd_test,
        "format": cmd_format,
    }
    if command == "revision":
        cmd_revision(" ".join(sys.argv[2:]))
    elif command in commands:
        commands[command]()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
