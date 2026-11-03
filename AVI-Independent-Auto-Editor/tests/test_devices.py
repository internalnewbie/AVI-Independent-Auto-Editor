"""Hardware routing and automatic fallback; tests never require real GPU/model files."""
import sys
import types
import unittest
from unittest.mock import patch

from autoedit.hardware import select_device, describe_hardware
from autoedit.ai_engine import transcribe_voice


class DeviceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.both = {'torch_cuda': True, 'whisper_cuda': True}
        self.only_clip = {'torch_cuda': True, 'whisper_cuda': False}
        self.no_gpu = {'torch_cuda': False, 'whisper_cuda': False}

    def test_auto_cuda_both(self):
        self.assertEqual(select_device('auto', backend='clip', capabilities=self.both), 'cuda')
        self.assertEqual(select_device('auto', backend='whisper', capabilities=self.both), 'cuda')

    def test_independent_fallback(self):
        self.assertEqual(select_device('auto', backend='clip', capabilities=self.only_clip), 'cuda')
        self.assertEqual(select_device('auto', backend='whisper', capabilities=self.only_clip), 'cpu')

    def test_auto_all_cpu(self):
        self.assertEqual(select_device('auto', backend='clip', capabilities=self.no_gpu), 'cpu')
        self.assertEqual(select_device('auto', backend='whisper', capabilities=self.no_gpu), 'cpu')

    def test_forced_cpu_ignores_available_gpu(self):
        self.assertEqual(select_device('cpu', backend='clip', capabilities=self.both), 'cpu')
        self.assertEqual(select_device('cpu', backend='whisper', capabilities=self.both), 'cpu')

    def test_explicit_cuda_failure(self):
        with self.assertRaises(RuntimeError):
            select_device('cuda', backend='whisper', capabilities=self.only_clip)

    def test_pretty_diagnostics(self):
        result = {**self.only_clip, 'gpus': [{'name':'RTX 3060','vram_mb':'12288'}]}
        text = describe_hardware(result)
        self.assertIn('RTX 3060', text)
        self.assertIn('PyTorch/CLIP: CUDA', text)
        self.assertIn('CTranslate2/Whisper: CPU', text)


class AutoWhisperRetryTests(unittest.TestCase):
    def test_gpu_decode_failure_restarts_cleanly_on_cpu(self):
        calls = []
        class FakeModel:
            def __init__(self, name, device, compute_type):
                calls.append((device, compute_type))
                self.device = device

            def transcribe(self, audio, **kwargs):
                def lazy():
                    if self.device == 'cuda':
                        raise RuntimeError('CUDNN_STATUS_EXECUTION_FAILED')
                    part = types.SimpleNamespace(start=0, end=2, text='Prince William.',
                        words=[types.SimpleNamespace(start=0, end=1, word='Prince'),
                               types.SimpleNamespace(start=1, end=2, word='William.')])
                    yield part
                return lazy(), types.SimpleNamespace(language='en')
        with patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            data = transcribe_voice('voice.wav', device='auto', capabilities={
                'torch_cuda': True, 'whisper_cuda': True}, log=lambda msg: None)
        self.assertEqual(calls, [('cuda', 'float16'), ('cpu', 'int8')])
        self.assertEqual(data['device'], 'cpu')
        self.assertEqual(data['words'][1]['text'], 'William.')
        self.assertIn('CUDNN', data['fallback_reason'])

    def test_cpu_only_not_gpu(self):
        calls = []
        class FakeModel:
            def __init__(self, name, device, compute_type):
                calls.append(device)
            def transcribe(self, audio, **kwargs):
                part = types.SimpleNamespace(start=0, end=1, text='hello', words=None)
                return iter([part]), types.SimpleNamespace(language='en')
        with patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            data = transcribe_voice('voice.wav', device='cpu', capabilities={}, log=lambda msg: None)
        self.assertEqual(calls, ['cpu'])
        self.assertEqual(data['device'], 'cpu')

    def test_manual_cuda_does_not_silently_fallback(self):
        class FakeModel:
            def __init__(self, name, device, compute_type):
                raise RuntimeError('No cuBLAS DLL')
        with patch.dict(sys.modules, {'faster_whisper': types.SimpleNamespace(WhisperModel=FakeModel)}):
            with self.assertRaisesRegex(RuntimeError, 'No cuBLAS'):
                transcribe_voice('voice.wav', device='cuda',
                                 capabilities={'torch_cuda': True, 'whisper_cuda': True},
                                 log=lambda msg: None)


if __name__ == '__main__':
    unittest.main()
