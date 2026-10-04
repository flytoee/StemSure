from pathlib import Path
from stemsure_reliable.cli import run

example = Path(__file__).with_name("demo_unclassified.las")
run(example, Path("demo_results_054"), ground_class=None, stem_class=None)
