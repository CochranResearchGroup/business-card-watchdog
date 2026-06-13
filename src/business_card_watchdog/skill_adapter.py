from __future__ import annotations

import subprocess
from pathlib import Path

from .config import AppConfig
from .models import SkillRunResult


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


class BusinessCardSkillAdapter:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def pipeline_script(self) -> Path:
        return self.config.skill_root / "scripts" / "run_business_card_pipeline.py"

    def check_ready(self) -> tuple[bool, str]:
        if not self.config.skill_root.exists():
            return False, f"skill root not found: {self.config.skill_root}"
        if not self.pipeline_script.exists():
            return False, f"pipeline script not found: {self.pipeline_script}"
        return True, "ready"

    def run_pipeline(self, image_path: Path, artifact_dir: Path, *, apply_google: bool) -> SkillRunResult:
        ready, message = self.check_ready()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        if not ready:
            return SkillRunResult(status="failed", artifact_dir=artifact_dir, error=message)

        command = [
            "python3",
            str(self.pipeline_script),
            str(image_path),
            str(artifact_dir),
            "--require-review",
        ]
        if apply_google:
            command.append("--apply-google")

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        spec_path = artifact_dir / "spec.json"
        review_path = artifact_dir / "review.md"
        if completed.returncode != 0:
            return SkillRunResult(
                status="failed",
                artifact_dir=artifact_dir,
                spec_path=spec_path if spec_path.exists() else None,
                review_path=review_path if review_path.exists() else None,
                stdout=completed.stdout,
                stderr=completed.stderr,
                error=f"pipeline exited {completed.returncode}",
            )
        return SkillRunResult(
            status="ok",
            artifact_dir=artifact_dir,
            spec_path=spec_path if spec_path.exists() else None,
            review_path=review_path if review_path.exists() else None,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

