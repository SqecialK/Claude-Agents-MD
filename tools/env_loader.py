"""Loads key=value pairs from a .env file into os.environ.

Uses python-dotenv when it's installed, and falls back to a minimal
built-in parser otherwise so the rest of the system doesn't hard-depend on
that package just to read a few config values.
"""

import os


def load_env(path: str = ".env") -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
        return
    except ImportError:
        pass

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
