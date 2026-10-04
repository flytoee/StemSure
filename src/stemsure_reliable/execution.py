"""Owned output sessions, strict JSON records, and runtime provenance."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import metadata
import hashlib
import json
import math
from pathlib import Path
import platform

from stemsure_run.cli import failure_code
from . import __version__


def json_safe(value):
    """Retain invalid numeric arguments as text, never NaN/Infinity tokens."""
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    return value


def write_json(path: Path, record: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(json_safe(record), ensure_ascii=False,
                                    indent=2, allow_nan=False) + "\n", encoding="utf8")
    temporary.replace(path)


def runtime_provenance() -> dict:
    dependencies = {}
    for name in ("numpy", "pandas", "scipy", "laspy", "lazrs"):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = None
    root = Path(__file__).resolve().parent.parent
    sources = {}
    for package in ("stemsure", "stemsure_guard", "stemsure_run",
                    "stemsure_checked", "stemsure_reliable"):
        for file in sorted((root / package).glob("*.py")):
            sources[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True,
                                      separators=(",", ":")).encode("utf8")).hexdigest()
    return {"dependency_versions": dependencies,
            "platform": {"system": platform.system(), "machine": platform.machine(),
                         "python_version": platform.python_version()},
            "source_files_sha256": sources, "source_bundle_sha256": digest}


@contextmanager
def output_session(output_dir: Path, input_path: Path, options: dict):
    """Claim the new directory atomically; only its owner may write records."""
    output_dir = Path(output_dir).resolve()
    # Outside try: a losing process must not write into the winner's directory.
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield output_dir
    except Exception as exc:
        try:
            code = failure_code(exc) if isinstance(exc, (OSError, ValueError)) else "INTERNAL_PROCESSING_ERROR"
            record = {"status": "failed", "software_version": __version__,
                      "created_at_utc": datetime.now(timezone.utc).isoformat(),
                      "input_path": str(Path(input_path).resolve(strict=False)),
                      "reason_code": code, "diagnostic": str(exc),
                      "exception_type": type(exc).__name__, "options": options,
                      "reference_data_used": False}
            write_json(output_dir / "failure.json", record)
            report_path = output_dir / "run_record.json"
            if report_path.exists():
                report = json.loads(report_path.read_text(encoding="utf8"))
                report.update(status="failed", failure_record="failure.json", reason_code=code)
                write_json(report_path, report)
            exc.stemsure_failure_path = output_dir / "failure.json"
        except (OSError, ValueError) as record_exc:
            exc.stemsure_failure_record_error = str(record_exc)
        raise
