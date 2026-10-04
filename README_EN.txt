StemSure 0.5.4
Forest point-cloud diameter measurement software
Purpose
StemSure reads metric LAS or LAZ point clouds and returns candidate tree diameters, proposal locations, fitted section centers, geometric diagnostics, and measurement states. It estimates a ground surface when required and does not use a field reference table for measurement.
Installation
Python 3.12 or later is required. Windows with Python 3.12.10 is the verified platform. Other platforms are not included in the present verification.
python -m pip install stemsure-0.5.4-py3-none-any.whl
From the cloned repository: python -m pip install .
Synthetic example: python examples/run_example.py
Regression checks: python -m unittest discover -s tests -v
The package declares compatible dependency ranges. requirements-tested.txt specifies the exact versions used for release verification. It is a tested environment specification rather than a cross-platform lockfile with artifact hashes.
Command-line examples
Unclassified cloud: stemsure --input plot.las --output new_run --ground-class all --stem-class all
Change the central measurement height: stemsure --input plot.las --output height137 --ground-class all --stem-class all --breast-height 1.37
Already normalized heights: stemsure --input normalized.laz --output normalized_run --normalized --stem-class all
Classified cloud: stemsure --input classified.las --output classified_run --ground-class 2 --stem-class 1
Show version: stemsure --version
stemsure and stemsure-reliable call the same current implementation. Historical command aliases are not installed by 0.5.4; archived 0.5.0 and 0.5.1 packages remain available for their original results. python -m stemsure and python -m stemsure_reliable also use the current entry point.
Input settings
All coordinates must be in meters. --normalized means input Z is height above local ground. Without it, StemSure estimates a ground surface from the selected ground class. Class defaults are ground 2 and stem 1. For unclassified input, explicitly select all for both. Supply a plot-sized cloud; very large extents are rejected before allocating the proposal grid.
The default central height is 1.30 m, with neighboring sections 0.10 m below and above. Numerical diameter range is 5 to 70 cm and the local crop radius is 0.45 m. These geometric settings match 0.5.1.
Python interface
from pathlib import Path
from stemsure_reliable.cli import run
report = run(Path("plot.las"), Path("new_api_run"), ground_class=None, stem_class=None, normalized=False, seed=20260927, trials=20000, breast_height_m=1.30)
run returns a dictionary on success. Once it owns a new output directory, processing exceptions produce failure.json and are re-raised with their original exception type. Callers should catch the exception. An existing directory is refused without writing into it. CLI processing errors return exit code 2; argument syntax errors are handled before processing and may not generate failure.json.
Output and reuse
decisions.csv contains one row per generated candidate. See OUTPUT_FIELDS.txt for the schema. Candidate identifiers are local to a run; they are not permanent field-tree identifiers.
x_m and y_m retain proposal-location semantics for compatibility. proposal_x_m and proposal_y_m explicitly repeat that location. fitted_center_x_m and fitted_center_y_m are the central-section fitted circle center; they do not replace proposal coordinates used by earlier evaluation.
Section CSV files contain fitted parameters, geometric diagnostics, and the actual measurement_height_m. They do not contain every original inlier point. Retain the original point cloud for spatial and geometric inspection.
keep means the current geometric checks passed; review calls for inspection; reject means the central section did not yield a diameter. A keep state is not a calibrated error probability or automatic confirmation of tree identity. Large stems can be underestimated within the numerical diameter range and still pass these checks.
run_record.json identifies input SHA256, settings, seed, actual heights, dependency versions, and a source-code fingerprint. failure.json describes processing exceptions. Output directories are atomically reserved so a competing process cannot write into another run's directory.
Licensing and citation
LICENSE.txt contains the author-approved paper-reproduction license. Free use covers reproduction and verification of the associated paper; unrelated research and commercial use require written author authorization. This is source-available licensing with use restrictions, not an OSI open-source license. Third-party dependencies and data retain their own terms.
CITATION.txt records authors, version, and manuscript title. GitHub repository: https://github.com/flytoee/StemSure. Software releases and frozen paper-reproduction artifacts are listed there. A software DOI has not been assigned.
Changes in 0.5.4
Author-approved license, final manuscript title, repository metadata, synthetic example, and frozen paper-reproduction artifacts prepared for GitHub publication. The measurement implementation is retained from 0.5.3. Processing improvements listed below are inherited from 0.5.2.
Unified entry points; output-directory ownership; strict JSON exception records; dependency and code provenance; bilingual plain-text documentation and publication metadata. Circle fitting, preprocessing, candidate generation, decision thresholds, and coordinate semantics remain unchanged. The known floating-point sensitivity of proposal grid bins is retained and documented in OUTPUT_FIELDS.txt.
Contacts
Qianxi Qu: qqx@caf.ac.cn
Zifeng Tan: 13588391788@139.com
Qifu Luan: qifu.luan@caf.ac.cn
