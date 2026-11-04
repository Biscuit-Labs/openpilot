"""Release-shaped metadata fixtures; never qualify or execute fixture model bytes."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from openpilot.common.file_chunker import package_file
from openpilot.starpilot.models import manager
from openpilot.starpilot.models import catalog as catalog_module
from openpilot.starpilot.models.runtime_selection import NATIVE_ABI, NATIVE_GENERATION, NATIVE_REVISION


@contextmanager
def native_fixture(root: Path, data: bytes):
  shipped = root / 'shipped'
  source = root / 'native-fixture-source.pkl'
  source.write_bytes(data)
  for relative in ('rdf43_driving_tinygrad.pkl', 'compat9d/rdf43_driving_tinygrad.pkl'):
    destination = shipped / relative
    if not Path(f'{destination}.chunkmanifest').exists():
      package_file(source, destination)
  source.unlink()
  identity = {'artifact_sha256': hashlib.sha256(data).hexdigest(), 'artifact_size': len(data),
              'qualification_sha256': hashlib.sha256(b'metadata fixture, no runtime qualification').hexdigest()}
  doc = {'generation': NATIVE_GENERATION, 'compiler_revision': NATIVE_REVISION, 'artifact_abi': NATIVE_ABI,
         'models': [{'id': 'rdf43', 'name': 'RDF metadata fixture', 'version': 'v15', 'uses_external_gpu': False,
                     'artifact_format': NATIVE_ABI, 'artifact_chunk_count': 1, **identity}],
         'stock': {name: dict(identity) for name in ('dmonitoring_model_tinygrad.pkl',
                   'dm_warp_1928x1208_tinygrad.pkl', 'dm_warp_1344x760_tinygrad.pkl')}}
  path = root / 'native-fixture-catalog.json'
  path.write_text(json.dumps(doc))
  with ExitStack() as stack:
    for module in (manager, catalog_module):
      stack.enter_context(patch.object(module, 'NATIVE_CATALOG_PATH', path))
    yield doc
