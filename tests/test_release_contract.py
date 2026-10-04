"""Regression checks for ownership and strict failure records."""
import json
import math
from pathlib import Path
import tempfile
import unittest

from stemsure_reliable.execution import output_session, write_json


def strict_load(path):
    def reject(value):
        raise ValueError(value)
    return json.loads(path.read_text(encoding="utf8"), parse_constant=reject)


class ReleaseContractTests(unittest.TestCase):
    def test_nonfinite_arguments_are_json_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            write_json(path, {"options": [math.nan, math.inf, -math.inf]})
            self.assertEqual(strict_load(path)["options"], ["NaN", "Infinity", "-Infinity"])
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_competitor_cannot_write_into_owned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with output_session(output, Path("plot.las"), {}):
                with self.assertRaises(FileExistsError):
                    with output_session(output, Path("another.las"), {}):
                        self.fail("Competing session entered owned directory")
                self.assertFalse((output / "failure.json").exists())

    def test_exception_record_preserves_exception_type(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with self.assertRaises(ValueError) as caught:
                with output_session(output, Path("plot.las"), {"breast_height_m": math.nan}):
                    raise ValueError("invalid height")
            record = strict_load(output / "failure.json")
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["options"]["breast_height_m"], "NaN")
            self.assertEqual(caught.exception.stemsure_failure_path, output / "failure.json")

    def test_late_failure_marks_partial_report_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            with self.assertRaises(RuntimeError):
                with output_session(output, Path("plot.las"), {}):
                    write_json(output / "run_record.json", {"status": "completed"})
                    raise RuntimeError("guard export failed")
            self.assertEqual(strict_load(output / "run_record.json")["status"], "failed")
            self.assertTrue((output / "failure.json").exists())


if __name__ == "__main__":
    unittest.main()
