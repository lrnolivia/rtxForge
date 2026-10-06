import importlib.util,json,hashlib,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('backup',Path(__file__).parents[1]/'scripts/prepare_release_backup.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class BackupTests(unittest.TestCase):
 def seed(self,root):
  data=b'synthetic AppImage bytes';(root/'test.AppImage').write_bytes(data);value={'appimage':'test.AppImage','commit':'a'*40,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)};(root/'rtxforge-update.json').write_text(json.dumps(value));return value
 def test_preserves_verified_artifact_and_manifest(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.seed(root);files=module.prepare(root,root/'backup');self.assertEqual(len(files),3);self.assertEqual(files[0].read_bytes(),b'synthetic AppImage bytes');self.assertEqual(files,module.prepare(root,root/'backup'))
 def test_corrupt_previous_artifact_is_not_published(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.seed(root);(root/'test.AppImage').write_bytes(b'changed');self.assertRaises(ValueError,module.prepare,root,root/'backup');self.assertFalse((root/'backup').exists())
 def test_unsafe_manifest_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);v=self.seed(root);v['appimage']='../test.AppImage';(root/'rtxforge-update.json').write_text(json.dumps(v));self.assertRaises(ValueError,module.prepare,root,root/'backup')
 def test_conflicting_backup_is_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);self.seed(root);files=module.prepare(root,root/'backup');files[0].write_bytes(b'preserve me');self.assertRaises(ValueError,module.prepare,root,root/'backup');self.assertEqual(files[0].read_bytes(),b'preserve me')
if __name__=='__main__':unittest.main()
