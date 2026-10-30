"""Force UTF-8 on stdout/stderr for test scripts.

Why: GitHub Actions runs Windows jobs with a cp1252 console by default. Any
script that prints a Chinese path, group name or error message then dies with

    UnicodeEncodeError: 'charmap' codec can't encode characters ...

which looks like a test failure but is purely an output-encoding problem.

Usage (right after `import sys`):

    from _encoding import utf8_output
    utf8_output()
"""

from __future__ import annotations

import sys


def utf8_output() -> None:
    """Reconfigure stdout/stderr to UTF-8; never raise."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
