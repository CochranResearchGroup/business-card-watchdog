# Public Upstream Validation

This runbook validates that the public GitHub repository can be cloned, installed, tested, linted, and built without private workspace state.

Repository:

```text
https://github.com/CochranResearchGroup/business-card-watchdog.git
```

## Clean Clone Check

```bash
tmpdir="$(mktemp -d /tmp/bcw-public-clone.XXXXXX)"
git clone https://github.com/CochranResearchGroup/business-card-watchdog.git "$tmpdir/business-card-watchdog"
cd "$tmpdir/business-card-watchdog"

uv venv --python 3.11
uv pip install --python .venv/bin/python -e '.[dev,vision]'
```

The status and doctor tests expect the user-scoped `business-card-to-contact` skill to exist. For CI or clean validation hosts that do not have the real skill installed, seed a minimal offline fixture:

```bash
mkdir -p "$HOME/.codex/shared/skills/business-card-to-contact/scripts"
cat > "$HOME/.codex/shared/skills/business-card-to-contact/scripts/run_business_card_pipeline.py" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

_image_path = Path(sys.argv[1])
artifact_dir = Path(sys.argv[2])
artifact_dir.mkdir(parents=True, exist_ok=True)
(artifact_dir / "spec.json").write_text(
    json.dumps(
        {
            "full_name": "Clean Clone Fixture",
            "organization": "Example Organization",
            "email": "clean.clone@example.test",
        },
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
(artifact_dir / "review.md").write_text("# Clean clone fixture review\n", encoding="utf-8")
PY
```

Run the validation:

```bash
.venv/bin/bcw --help
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
uv build --out-dir dist
```

## 2026-06-14 Readback

Clean clone path:

```text
/tmp/bcw-public-clone.3OrD8L/business-card-watchdog
```

Validation:

- `uv venv --python 3.11` installed CPython 3.11.15.
- `uv pip install --python .venv/bin/python -e '.[dev,vision]'` installed the package, dev tools, and OpenCV vision analyzer.
- `.venv/bin/bcw --help` returned successfully.
- `.venv/bin/python -m pytest -q` should pass with the CI-equivalent dev and vision extras installed.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.

## 2026-06-15 Local Gate For Plan 0011

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_preclassifier_detects_multiple_cards_in_large_photo tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0012

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0013

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0014

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.
