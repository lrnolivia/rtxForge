"""A game Steam already maps to a CUDA Proton build whose last run used one without: fixture-only."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stack_fixture as fx
import proton_cuda
import proton_stack

CONFIG = '''"InstallConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"CompatToolMapping"
				{
					"0"
					{
						"name"		"proton_experimental"
						"config"		""
					}
					"1174180"
					{
						"name"		"%s"
						"config"		""
					}
				}
			}
		}
	}
	"1174180"
	{
		"name"		"decoy outside the mapping"
	}
}
'''


class StaleRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.proc, self.wine = fx.driver(root)
        self.steam = root / 'Steam'
        (self.steam / 'config').mkdir(parents=True)
        experimental = fx.proton(root, 'Proton - Experimental', nvcuda=False)
        self.pfx = fx.prefix(root / 'library', 1174180, experimental, version='11.0-100')
        tools = self.steam / 'compatibilitytools.d'
        fx.proton(tools.parent / 'cuda-src', 'GE-Proton11-7')
        (tools / 'GE-Proton11-7').mkdir(parents=True)
        (tools / 'GE-Proton11-7' / 'files').symlink_to(tools.parent / 'cuda-src' / 'common' / 'GE-Proton11-7' / 'files')
        (tools / 'GE-Proton11-7' / 'compatibilitytool.vdf').write_text(
            '"compatibilitytools"\n{\n  "compat_tools"\n  {\n    "Proton-GE Latest"\n    {\n'
            '      "install_path" "."\n      "display_name" "Proton-GE Latest"\n    }\n  }\n}\n')
        self.roots = mock.patch.object(proton_stack, 'STEAM_ROOTS', (self.steam,))
        self.roots.start()

    def tearDown(self):
        self.roots.stop()
        self.tmp.cleanup()

    def map_to(self, name):
        (self.steam / 'config' / 'config.vdf').write_text(CONFIG % name)

    def cuda_reason(self):
        report = proton_stack.detect(self.pfx, 'nr-mfg', native_dlssg=True,
                                     driver_root=self.proc, driver_dirs=(str(self.wine),))
        return next(check['reason'] for check in report['checks'] if check['id'] == 'nvcuda')

    def test_mapped_to_a_cuda_build_asks_for_one_launch(self):
        self.map_to('Proton-GE Latest')
        self.assertEqual(proton_stack.mapped_tool(1174180)['name'], 'Proton-GE Latest')
        self.assertEqual(self.cuda_reason(), 'cuda-stale-run')
        lib = proton_stack.compat_tool(self.pfx.parent)['lib_dir']
        with self.assertRaisesRegex(proton_cuda.CudaError, 'Play it once'):
            proton_cuda.plan(lib, self.pfx.parent)

    def test_mapped_to_a_build_without_cuda_says_to_switch(self):
        self.map_to('proton_experimental')
        self.assertEqual(self.cuda_reason(), 'cuda-missing')
        with self.assertRaisesRegex(proton_cuda.CudaError, 'Proton-GE'):
            proton_cuda.plan(proton_stack.compat_tool(self.pfx.parent)['lib_dir'], self.pfx.parent)

    def test_no_mapping_or_config_says_to_switch(self):
        self.assertEqual(proton_stack.mapped_tool(1174180), {'name': None, 'lib_dir': None})
        self.assertEqual(self.cuda_reason(), 'cuda-missing')


if __name__ == '__main__':
    unittest.main()
