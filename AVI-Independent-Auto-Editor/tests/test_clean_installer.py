"""Test the installer skips existing packages and never redownloads models needlessly."""
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import install_auto
import setup_all


class CleanInstallerTests(unittest.TestCase):
    def test_old_pip_detected(self):
        self.assertLess(install_auto.major_minor('22.3'), (24, 2))
        self.assertGreaterEqual(install_auto.major_minor('26.2.2'), (24, 2))

    def test_torch_cuda_already_installed_skips(self):
        calls = []
        with patch.object(install_auto, 'usable_torch', return_value=True), patch.object(install_auto, 'log'):
            status = install_auto.install_torch(use_cuda=True,
                installer=lambda *a, **kw: calls.append((a,kw)))
        self.assertEqual('cuda', status)
        self.assertEqual([], calls)

    def test_torch_cpu_already_installed_skips(self):
        calls = []
        with patch.object(install_auto, 'usable_torch', return_value=True), patch.object(install_auto, 'log'):
            status = install_auto.install_torch(use_cuda=False,
                installer=lambda *a, **kw: calls.append((a,kw)))
        self.assertEqual('cpu', status)
        self.assertEqual([], calls)

    def test_existing_requirements_skip(self):
        fake = {'faster-whisper':'1.1.1','transformers':'4.51.0',
                'Pillow':'11.0.0','numpy':'2.0.2',
                'opencv-python':'4.10.0.84','ctranslate2':'4.4.0','av':'18.1.0'}
        with patch.object(install_auto, 'get_version', side_effect=lambda p:fake.get(p)):
            self.assertEqual([], install_auto.requirements_ready())

    def test_incompatible_requirements_trigger_install(self):
        fake = {'faster-whisper':'1.1.1','transformers':'5.0.0',
                'Pillow':'9.5.0','numpy':'2.0.2',
                'opencv-python':'4.10.0.84','ctranslate2':'4.4.0','av':'18.1.0'}
        with patch.object(install_auto, 'get_version', side_effect=lambda p:fake.get(p)):
            missing = install_auto.requirements_ready()
        self.assertTrue(any('transformers' in x for x in missing))
        self.assertTrue(any('Pillow' in x for x in missing))

    def test_clean_root_only_two_bats(self):
        root = Path(install_auto.__file__).parent
        self.assertEqual({'CAI_MOT_LAN.bat','CHAY_AUTO_EDIT.bat'},
                         {p.name for p in root.glob('*.bat')})

    def test_cached_models_do_not_download_again(self):
        class HF:
            @staticmethod
            def snapshot_download(repo_id, local_files_only=False):
                if not local_files_only:
                    raise AssertionError('Unexpected download: ' + repo_id)
                return '/local/cache/' + repo_id
        with patch.dict('sys.modules', {'huggingface_hub':HF}), patch.object(setup_all, 'out'):
            setup_all.prefetch_models()

    def test_uncached_models_download(self):
        calls=[]
        class HF:
            @staticmethod
            def snapshot_download(repo_id, local_files_only=False):
                calls.append((repo_id, local_files_only))
                if local_files_only: raise FileNotFoundError('not cached')
                return '/model/' + repo_id
        with patch.dict('sys.modules', {'huggingface_hub':HF}), patch.object(setup_all, 'out'):
            setup_all.prefetch_models()
        self.assertEqual(4, len(calls))
        self.assertTrue(calls[0][1] and not calls[1][1])


if __name__ == '__main__': unittest.main()
