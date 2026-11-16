#!/usr/bin/env bash
set -euo pipefail
# Historical extended GFP comparison, not the primary released-LabOP witness.
# Use gfp_labop.py for the unextended check; this script explicitly replays
# the archived ClarifyLysate/FractionationUpdater experiment.

if [[ $# != 4 ]]; then
  echo "Usage: bash reproduce.sh CULSMA_REPO LABOP_REPO PYTHON_3_12_8 PYTHON_3_11_11" >&2
  exit 2
fi

package=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$package/../.." && pwd)
culsma_commit=5364676bc2437b4981a00ce0133c730af243e469
labop_commit=2e2bd88150c71a440771fd369f40295dfd622324

"$3" -c 'import sys; assert sys.version_info[:3] == (3, 12, 8), sys.version'
"$4" -c 'import sys; assert sys.version_info[:3] == (3, 11, 11), sys.version'

output="${COMPARISON_RUNTIME_DIR:-$root/benchmarks/local-results/comparison-runtime}"
mkdir -p "$(dirname "$output")"
mkdir "$output"
mkdir "$output"/{build,culsma-source,labop-source,culsma,labop,magnetic-culsma}
export TMPDIR="$output/build"

git -C "$1" archive "$culsma_commit" src | tar -x -C "$output/culsma-source"
git -C "$2" archive "$labop_commit" | tar -x -C "$output/labop-source"

"$3" -m venv "$output/culsma-env"
"$4" -m venv "$output/labop-env"
culsma_python="$output/culsma-env/bin/python"
labop_python="$output/labop-env/bin/python"
{
  "$culsma_python" -m pip install --no-deps lark==1.3.1
  # The upstream project metadata uses moving URLs. Install the complete
  # locked dependency set without resolving those URLs a second time.
  "$labop_python" -m pip install --no-deps -r "$package/labop-requirements.txt" "$output/labop-source"
  "$culsma_python" -m pip check
  "$labop_python" -m pip check
} > "$output/install.log" 2>&1

{
  printf 'Culsma commit %s\n' "$culsma_commit"
  "$culsma_python" --version
  "$culsma_python" -m pip list --format=freeze
  printf '\nLabOP commit %s\n' "$labop_commit"
  "$labop_python" --version
  "$labop_python" -m pip list --format=freeze
  printf '\nInput SHA-256\n'
  cd "$package"
  shasum -a 256 gfp.culs gfp_labop_extended.py fractionation.py check.py expected.json labop-requirements.txt magnetic.culs check_magnetic.py
} > "$output/versions.txt"

cd "$root"
PYTHONPATH="$output/culsma-source/src" "$culsma_python" -m culsma.cli run \
  benchmarks/comparison/gfp.culs --output "$output/culsma/output.json" \
  --artifacts-dir "$output/culsma" > "$output/culsma/cli.log" 2>&1
"$labop_python" -u "$package/gfp_labop_extended.py" "$output/labop" > "$output/labop/execution.log" 2>&1
"$labop_python" "$package/check.py" "$output/culsma" "$output/labop" "$output/comparison.json"
PYTHONPATH="$output/culsma-source/src" "$culsma_python" -m culsma.cli run \
  benchmarks/comparison/magnetic.culs --output "$output/magnetic-culsma/output.json" \
  --artifacts-dir "$output/magnetic-culsma" > "$output/magnetic-culsma/cli.log" 2>&1
"$labop_python" "$package/check_magnetic.py" "$output/magnetic-culsma" \
  "$output/labop-source" "$output/magnetic-comparison.json"
printf 'Results saved under %s\n' "$output"
