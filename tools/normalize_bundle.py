"""Restore the pristine native binaries inside a packaged macOS .app.

Why: PyInstaller re-signs the binaries it collects, which changes their bytes.
The app checks the bundled binaries against the pinned hashes in
`namepicker/native_manifest.py` at startup, so a re-signed copy would look
"tampered" and trigger a needless restore on first run.

This step runs after PyInstaller and overwrites the bundled copies with the
pristine ones from `namepicker/native_backup/*.gz`, then verifies the hashes.
The replaced files already carry an ad-hoc signature (arm64 macOS refuses to run
unsigned code), so execution still works.

Usage:
    python tools/normalize_bundle.py "dist/ClassManageSystem.app"
"""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import stat
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)

from _encoding import utf8_output

utf8_output()

MANIFEST = os.path.join(_ROOT, "namepicker", "native_manifest.py")
BACKUP_DIR = os.path.join(_ROOT, "namepicker", "native_backup")


def pinned_hashes() -> set[str]:
    text = open(MANIFEST, encoding="utf-8").read()
    return set(re.findall(r"[0-9a-f]{64}", text))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python tools/normalize_bundle.py <ClassManageSystem.app>")
        return 2
    app = sys.argv[1]
    native_dir = os.path.join(app, "Contents", "Frameworks", "native")
    if not os.path.isdir(native_dir):
        print(f"[FAIL] not a packaged .app: {native_dir} does not exist")
        return 1

    pinned = pinned_hashes()
    bad = []
    for name in ("cmd_sign", "cmd_verify"):
        target = os.path.join(native_dir, name)
        source = os.path.join(BACKUP_DIR, name + ".gz")
        if not os.path.isfile(source):
            bad.append(f"{name}: missing pristine copy {source}")
            continue
        with gzip.open(source, "rb") as fh:
            payload = fh.read()
        digest = hashlib.sha256(payload).hexdigest()
        if digest not in pinned:
            bad.append(f"{name}: pristine copy does not match the manifest")
            continue
        with open(target, "wb") as fh:
            fh.write(payload)
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        after = hashlib.sha256(open(target, "rb").read()).hexdigest()
        if after != digest:
            bad.append(f"{name}: copy did not land intact")
            continue
        print(f"[OK  ] {name}: restored pristine copy ({digest[:16]})")

    if bad:
        for line in bad:
            print(f"[FAIL] {line}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error::{line}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
