"""Cross-branch API regressions, without touching an installed game."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'scripts')]
import library_media
import proton_overlay
import linux_overlay_host as host
import transactions as t

class IntegrationContracts(unittest.TestCase):
    def test_fresh_overlay_defaults_and_windows_alias(self):
        self.assertEqual(proton_overlay.preferences(library_media.DEFAULTS)['InGamePanel'],1)
        self.assertEqual(proton_overlay.preferences({'overlay_renderer':'rtxforge'})['InGamePanel'],1)
        for key,code in [('Insert',45),('F8',119),('Disabled',0)]:
            self.assertEqual(proton_overlay.preferences({'optiscaler_hotkey':key})['ShortcutKey'],code)

    def test_mapping_binds_exact_prefix_executable_and_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);proc=root/'proc';p=proc/'42';p.mkdir(parents=True)
            prefix=root/'prefix';exe=root/'Game.exe';channel=root/'panel.8.map'
            (p/'environ').write_bytes(b'WINEPREFIX='+str(prefix).encode()+b'\0')
            (p/'maps').write_text(f'0000-0001 r--p 0 00:00 1 {exe}\n0001-0002 rw-s 0 00:00 2 {channel}\n')
            self.assertEqual(host.mapped_process(prefix,exe,channel,proc),42)
            self.assertIsNone(host.mapped_process(root/'other',exe,channel,proc))
            self.assertIsNone(host.mapped_process(prefix,root/'other.exe',channel,proc))

    def test_mapping_refuses_links_and_wrong_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/'channel';file.write_bytes(bytes(512))
            with host.open_mapping(file,512) as mem:self.assertEqual(len(mem),512)
            link=root/'link';link.symlink_to(file)
            with self.assertRaises(OSError):host.open_mapping(link,512)
            with self.assertRaises(t.Refusal):host.open_mapping(file,64)
            os.link(file,root/'hardlink')
            with self.assertRaises(t.Refusal):host.open_mapping(file,512)

    def test_real_file_mailbox_acknowledges_protocol_seven(self):
        import struct,threading,time
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'controls.8.map';raw=bytearray(512)
            struct.pack_into('<4i',raw,0,host.controls.MAGIC,7,8,2)
            for key,offset in host.controls.OFFSETS.items():
                struct.pack_into('<f' if key in host.controls._FLOATS else '<i',raw,offset,host.controls.DEFAULTS[key])
            struct.pack_into('<i',raw,112,5)
            struct.pack_into('<i',raw,420,1)
            path.write_bytes(raw)
            with patch.object(host,'mapped_process',return_value=42):
                with host.FileMailbox(Path(directory),'Game.exe',path) as box:
                    self.assertEqual(box.read()['version'],7)
                    def acknowledge():
                        with host.open_mapping(path,512) as mem:
                            deadline=time.monotonic()+2
                            while time.monotonic()<deadline:
                                command=struct.unpack_from('<i',mem,16)[0]
                                if command and not command&1:
                                    struct.pack_into('<i',mem,412,struct.unpack_from('<i',mem,404)[0])
                                    struct.pack_into('<i',mem,24,1)
                                    struct.pack_into('<i',mem,20,command)
                                    return
                                time.sleep(.005)
                    worker=threading.Thread(target=acknowledge);worker.start()
                    self.assertEqual(box.apply({'dynamic_mfg':1})['values']['dynamic_mfg'],1)
                    worker.join()
                    struct.pack_into('<i',box.mem,420,-1)
                    with self.assertRaises(t.Refusal):box.apply({'dynamic_mfg':1})

    def test_panel_reviews_are_session_bound_and_single_use(self):
        from unittest.mock import Mock
        h=host.Host.__new__(host.Host);h.settings=lambda:dict(library_media.DEFAULTS)
        h.engine=object();h.controls=Mock();h.reviews={};h.review_id=0
        row={'game':'/fixture/game','exe':'Game.exe'}
        review={'plans':[{'name':'Fixture','summary':'NR off'}],'blocked':[],'skipped':[]}
        with patch.object(host.linux_runtime,'global_review',return_value=review) as prepare, patch.object(host.linux_runtime,'apply_review',return_value={'message':'Updated 1 game.'}) as apply:
            result=h.handle({'op':'global-review','changes':{'nr':False}},row,8,(42,100))
            self.assertTrue(result['ready'])
            prepare.assert_called_once_with(h.engine,{'nr':False})
            command={'op':'apply-review','review_id':result['review_id']}
            self.assertTrue(h.handle(command,row,8,(43,101))['error'])
            apply.assert_not_called()
            self.assertNotIn('error',h.handle(command,row,8,(42,100)))
            apply.assert_called_once_with(review)
            self.assertTrue(h.handle(command,row,8,(42,100))['error'])
        with patch.object(host.linux_runtime,'menus_review',return_value=review):
            result=h.handle({'op':'menus-review'},row,8,(42,100))
            h.handle({'op':'discard-review'},row,8,(42,100))
            self.assertTrue(h.handle({'op':'apply-review','review_id':result['review_id']},row,8,(42,100))['error'])

    def test_save_uses_exact_bound_game_and_session(self):
        h=host.Host.__new__(host.Host);h.settings=lambda:dict(library_media.DEFAULTS)
        from unittest.mock import Mock
        h.controls=Mock()
        row={'game':'/fixture/game','exe':'Game.exe'}
        response=h.handle({'op':'save','changes':{'enabled':0}},row,9)
        h.controls.save.assert_called_once_with({'row':row,'pid':9,'changes':{'enabled':0}})
        self.assertNotIn('error',response)
        h.controls.save.side_effect=t.Refusal('Game changed')
        self.assertTrue(h.handle({'op':'save','changes':{'enabled':0}},row,9)['error'])

if __name__=='__main__':unittest.main()
