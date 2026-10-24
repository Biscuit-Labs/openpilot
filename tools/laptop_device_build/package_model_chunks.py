"""Package the compiled small-model outputs using established Dom model parts."""
import argparse
from pathlib import Path
import sys


# Resolve this checkout's stdlib-only owner, even for an absolute CLI invocation
# with no PYTHONPATH or installed workspace package.
import importlib.util
_spec = importlib.util.spec_from_file_location("model_file_chunker", Path(__file__).resolve().parents[2] / "openpilot/common/file_chunker.py")
_chunk_owner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_chunk_owner)
package_file = _chunk_owner.package_file

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--source', type=Path, required=True)
  parser.add_argument('--destination', type=Path, required=True)
  args = parser.parse_args()
  root = Path(__file__).resolve().parents[2]
  sys.path.insert(0, str(root))
  from tools.laptop_device_build.qcom_artifact_contract import native_records, verified_native_asset
  native = native_records(root) if args.source.resolve() == (root / 'openpilot/selfdrive/modeld/models').resolve() else None
  for name in ('dmonitoring_model_tinygrad.pkl', 'rdf43_driving_tinygrad.pkl'):
    if native is not None:
      source = verified_native_asset(root, name, prefer_regular=True)
    else:
      source = (_chunk_owner.materialize_file_chunked(args.source / name)
                if name == 'rdf43_driving_tinygrad.pkl' or not (args.source / name).is_file() else args.source / name)
    package_file(source, args.destination / name)

if __name__ == '__main__':
  main()
