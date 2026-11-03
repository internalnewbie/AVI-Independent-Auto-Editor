"""Offline installation orchestration tests: no downloads/Windows commands."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest

import setup_all
import install_auto


class OneClickTests(unittest.TestCase):
    def test_ollama_already_installed_not_reinstalled(self):
        with patch.object(setup_all, 'lookup_ollama', return_value='C:/Ollama/ollama.exe'), \
             patch.object(setup_all, 'ollama_alive', return_value=True), \
             patch.object(setup_all, 'winget_install') as win:
            self.assertEqual(setup_all.install_ollama(), 'C:/Ollama/ollama.exe')
            win.assert_not_called()

    def test_missing_ollama_uses_winget(self):
        with patch.object(setup_all, 'lookup_ollama', side_effect=[None, 'C:/Ollama/ollama.exe']), \
             patch.object(setup_all, 'winget_install', return_value=True) as win, \
             patch.object(setup_all, 'ollama_alive', return_value=True):
            self.assertEqual(setup_all.install_ollama(), 'C:/Ollama/ollama.exe')
            win.assert_called_once_with('Ollama.Ollama')

    def test_existing_qwen_does_not_pull_again(self):
        with patch.object(setup_all, 'model_downloaded', return_value=True), \
             patch.object(setup_all, 'run') as cmd:
            setup_all.install_qwen('ollama.exe')
            cmd.assert_not_called()

    def test_missing_qwen_pulled_once(self):
        with patch.object(setup_all, 'model_downloaded', side_effect=[False, True]), \
             patch.object(setup_all, 'run') as cmd:
            setup_all.install_qwen('ollama.exe')
            cmd.assert_called_once_with(['ollama.exe','pull','qwen3-vl:4b-instruct'])

    def test_ffmpeg_existing_config(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'tools'
            folder.mkdir()
            (folder / 'ffmpeg.exe').touch()
            (folder / 'ffprobe.exe').touch()
            with patch.object(setup_all, 'ROOT', Path(temp)):
                self.assertEqual(setup_all.ffmpeg_bin(), folder.resolve())
                with patch.object(setup_all, 'winget_install') as win:
                    setup_all.install_ffmpeg()
                    win.assert_not_called()
                self.assertTrue((Path(temp) / '.ffmpeg_path.txt').is_file())

    def test_cuda_explicit_package_tag(self):
        commands = []
        def fake(*args, **kwargs):
            commands.append(args)
            return True
        with patch.object(install_auto, 'log'):
            self.assertEqual(install_auto.install_torch(use_cuda=True, installer=fake),'cuda')
        self.assertIn('torch==2.9.1+cu126',commands[0])

    def test_cpu_explicit_package_tag(self):
        commands = []
        def fake(*args, **kwargs):
            commands.append(args)
            return True
        with patch.object(install_auto, 'log'), patch.object(install_auto, 'usable_torch', return_value=False):
            self.assertEqual(install_auto.install_torch(use_cuda=False, installer=fake),'cpu')
        self.assertIn('torch==2.9.1+cpu',commands[0])

    def test_cuda_network_failure_not_silent_cpu(self):
        with patch.object(install_auto, 'log'), patch.object(install_auto, 'usable_torch', return_value=False):
            with self.assertRaisesRegex(RuntimeError,'KHÔNG tự chuyển'):
                install_auto.install_torch(use_cuda=True,
                                          installer=lambda *args, **kwargs: False)


if __name__ == '__main__':
    unittest.main()
