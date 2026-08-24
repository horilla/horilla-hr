#!/usr/bin/env python
"""Generate a local .env from .env.example with fresh random secrets.

Used by `make env`. Refuses to overwrite an existing .env.
"""

import pathlib
import secrets
import sys

from django.core.management.utils import get_random_secret_key

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def main() -> int:
    if TARGET.exists():
        print(f"{TARGET.name} already exists — delete it first to regenerate.")
        return 1

    # docker compose reads .env for variable interpolation, where a literal "$"
    # is parsed as a variable reference. Swap it out so the key survives intact.
    secret_key = get_random_secret_key().replace("$", "-")

    text = EXAMPLE.read_text()
    for placeholder, value in (
        ("SECRET_KEY=<generate-me>", f"SECRET_KEY={secret_key}"),
        ("DB_INIT_PASSWORD=<generate-me>", f"DB_INIT_PASSWORD={secrets.token_hex(24)}"),
    ):
        if placeholder not in text:
            print(f"Expected {placeholder!r} in {EXAMPLE.name}; aborting.")
            return 1
        text = text.replace(placeholder, value)

    TARGET.write_text(text)
    print(f"Created {TARGET.name} with a generated SECRET_KEY and DB_INIT_PASSWORD.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
