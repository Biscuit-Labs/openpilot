from pathlib import Path
import re
import unittest

ROOT = Path(__file__).parents[3]
# Linux jobs that build openpilot reuse the run's one native build; macOS and the ARM release build compile their own.
OWN_BUILD = {'native_build', 'build_mac', 'build_release', 'source_integrity'}
RESTORE = 'uses: ./.github/workflows/restore-native-build\n'
SCONS = re.compile(r'^\s+run: scons\n', re.M)


class NativeBuildReuseTests(unittest.TestCase):
  def setUp(self):
    workflow = (ROOT / '.github/workflows/tests.yaml').read_text()
    self.jobs = dict(re.findall(r'^  ([a-z_]+):\n(.*?)(?=^  [a-z_]+:\n|\Z)', workflow, re.M | re.S))

  def test_every_linux_scons_job_restores_the_native_build_first(self):
    for name, body in self.jobs.items():
      build = SCONS.search(body)
      if name in OWN_BUILD or build is None:
        continue
      with self.subTest(job=name):
        self.assertIn('    needs: native_build\n', body)
        self.assertEqual(body.count(RESTORE), 1)
        self.assertLess(body.index(RESTORE), build.start())

  def test_required_jobs_still_run_when_the_native_build_fails(self):
    # A skipped required check counts as passed, so these must not inherit the default success() gate.
    for name in ('unit_tests', 'vehicle_contracts', 'aol_lifecycles', 'safety_release_contracts', 'process_replay'):
      with self.subTest(job=name):
        self.assertRegex(self.jobs[name], r'(?m)^    if: \$\{\{ !cancelled\(\)')

  def test_cache_is_produced_and_restored_under_one_name(self):
    name = 'native-build-cache-${{ github.run_attempt }}'
    action = (ROOT / '.github/workflows/restore-native-build/action.yaml').read_text()
    self.assertIn('        name: ' + name + '\n', self.jobs['native_build'])
    self.assertIn('      name: ' + name + '\n', action)
    self.assertRegex(action, r'continue-on-error: true\n\s+uses: actions/download-artifact')


if __name__ == '__main__':
  unittest.main()
