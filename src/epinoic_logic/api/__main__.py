"""``python -m epinoic_logic.api --markdown``: print ``docs/PUBLIC_API.md``."""
import sys

from . import markdown

if __name__ == "__main__":
    if sys.argv[1:] != ["--markdown"]:
        print("usage: python -m epinoic_logic.api --markdown", file=sys.stderr)
        raise SystemExit(2)
    sys.stdout.write(markdown())
