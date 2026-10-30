"""Linux packages carry matching, intact native overlays from the reviewed build."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('overlay_bundle_builder',ROOT/'packaging/build_appimage.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class OverlayBundleTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.payload=self.root/'payload';self.sha='a'*40
        policy=self.root/'providers/glass-overlay';policy.mkdir(parents=True)
        (policy/'rollout-policy.json').write_text(json.dumps({'schema':1,'required':True,'revision':1}))
        self.folders={name:self.root/'windows/out'/name for name in ('glass-overlay','skynizz-bridge','feeder-panel')}
        for folder in self.folders.values():folder.mkdir(parents=True)
        def file(folder,name,data):
            (folder/name).write_bytes(data)
            return {'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        dll=file(self.folders['glass-overlay'],'rtxforge-glass.dll',b'glass')
        glass={'schema':1,'renderer':'rmlui','revision':1,'commit':self.sha,'files':{'rtxforge-glass.dll':dll}}
        archive='rtxForge-Skynizz-v1-MFG.zip';info=file(self.folders['skynizz-bridge'],archive,b'archive')
        bridge={'variant':'nr-mfg-bridge','tag':'v1','commit':self.sha,'archive':archive,'release_size':info['size'],'sha256':info['sha256'],'glass_sha256':dll['sha256']}
        feeder={'schema':2,'commit':self.sha,'files':{'rtxforge-glass.dll':file(self.folders['feeder-panel'],'rtxforge-glass.dll',b'glass')}}
        for name in ('rtxforge-panel.addon64','rtxforge-quiet.addon64'):feeder['files'][name]=file(self.folders['feeder-panel'],name,name.encode())
        self.receipts=dict(zip(self.folders,(glass,bridge,feeder)));self.save()

    def save(self):
        for name,receipt in self.receipts.items():(self.folders[name]/'package.json').write_text(json.dumps(receipt))

    def stage(self):return builder.bundle_overlays(self.root,self.payload,self.sha)

    def test_matching_build_is_staged_with_required_refresh_policy(self):
        self.assertTrue(self.stage())
        self.assertEqual((self.payload/'providers/glass-overlay/rtxforge-glass.dll').read_bytes(),b'glass')
        self.assertEqual(json.loads((self.payload/'providers/glass-overlay/rollout.json').read_text())['required'],True)
        self.assertTrue((self.payload/'providers/feeder-panel/rtxforge-panel.addon64').is_file())

    def test_changed_bytes_refuse_packaging(self):
        (self.folders['feeder-panel']/'rtxforge-panel.addon64').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'changed'):self.stage()

    def test_other_source_revision_refuses_packaging(self):
        self.receipts['glass-overlay']['commit']='b'*40;self.save()
        with self.assertRaisesRegex(RuntimeError,'source revision'):self.stage()

    def test_mismatched_glass_refuses_packaging(self):
        self.receipts['skynizz-bridge']['glass_sha256']='0'*64;self.save()
        with self.assertRaisesRegex(RuntimeError,'different glass'):self.stage()

    def test_partial_artifacts_refuse_packaging(self):
        (self.folders['glass-overlay']/'package.json').unlink()
        with self.assertRaisesRegex(RuntimeError,'incomplete'):self.stage()

    def test_absent_artifacts_allowed_only_for_local_development(self):
        for folder in self.folders.values():(folder/'package.json').unlink()
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):self.assertFalse(self.stage())
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(RuntimeError,'missing'):self.stage()


if __name__=='__main__':unittest.main()
