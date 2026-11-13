"""Generate the launcher checksum manifest when preparing a release."""
import json

from Application.core.config import PROJECT_ROOT
from Application.core.file_check import MANIFEST_NAME, make_manifest


if __name__ == "__main__":
    target = PROJECT_ROOT / MANIFEST_NAME
    target.write_text(json.dumps(make_manifest(PROJECT_ROOT), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
