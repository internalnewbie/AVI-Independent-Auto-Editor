"""Regression checks for consolidated distribution; no network/models required."""
from pathlib import Path
from unittest.mock import patch
import unittest

from autoedit import qwen_engine
import setup_all
import install_auto

ROOT = Path(__file__).resolve().parents[1]

class ConsolidatedReleaseTests(unittest.TestCase):
    def test_qwen_instruct_is_default_everywhere(self):
        target = 'qwen3-vl:4b-instruct'
        self.assertEqual(qwen_engine.DEFAULT_MODEL, target)
        self.assertEqual(setup_all.MODEL, target)
        for f in ('autoedit/gui.py','autoedit/pipeline.py','AVI_Auto_Editor.py'):
            self.assertIn(target, (ROOT/f).read_text(encoding='utf-8'))
        self.assertIn("self.qwen_model = tk.StringVar(value='" + target + "')",
                      (ROOT/'autoedit/gui.py').read_text(encoding='utf-8'))

    def test_old_qwen_alias_redirects_to_instruct(self):
        self.assertEqual(qwen_engine.preferred_model('qwen3-vl:4b'), 'qwen3-vl:4b-instruct')
        self.assertEqual(qwen_engine.preferred_model('qwen3-vl:4b-instruct'), 'qwen3-vl:4b-instruct')
        self.assertEqual(qwen_engine.preferred_model('custom:model'), 'custom:model')

    def test_pyav_compatible_version_is_pinned(self):
        self.assertIn('av==18.1.0', (ROOT/'requirements-ai.txt').read_text())
        with patch.object(install_auto,'get_version',side_effect=lambda x: {
            'faster-whisper':'1.2.1', 'transformers':'4.50.0','Pillow':'11.0.0',
            'numpy':'2.0.0','opencv-python':'4.10.0', 'ctranslate2':'4.5.0',
            'av':'19.0.0'
        }.get(x)):
            missing = install_auto.requirements_ready()
        self.assertTrue(any('av==18.1.0' in x for x in missing))

    def test_pyav_compatible_version_is_skipped_if_installed(self):
        with patch.object(install_auto,'get_version',side_effect=lambda x: {
            'faster-whisper':'1.2.1', 'transformers':'4.50.0','Pillow':'11.0.0',
            'numpy':'2.0.0','opencv-python':'4.10.0', 'ctranslate2':'4.5.0',
            'av':'18.1.0'
        }.get(x)):
            self.assertEqual(install_auto.requirements_ready(), [])

    def test_audio_decode_smoke_in_installer(self):
        source = (ROOT/'install_auto.py').read_text()
        self.assertIn('decode_audio', source)
        self.assertIn('AUDIO_DECODE_OK', source)

    def test_top_level_only_two_launchers(self):
        self.assertEqual({p.name for p in ROOT.glob('*.bat')},
                         {'CAI_MOT_LAN.bat', 'CHAY_AUTO_EDIT.bat'})

if __name__ == '__main__':
    unittest.main()
