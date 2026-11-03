import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import patch

from autoedit import qwen_engine

@dataclass
class FakeCandidate:
    path: str
    start: float = 0.0
    end: float = 3.0
    motion: float = .2
    @property
    def duration(self): return self.end - self.start


class QwenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = Path(self.tmp.name) / 'test.mp4'
        p.write_bytes(b'nonempty dummy video')
        self.candidates = [FakeCandidate(str(p))]
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake_ollama(self, path, payload):
        self.calls.append((path, payload))
        if path == '/api/tags':
            return {'models': [{'name': 'qwen3-vl:4b-instruct'}]}
        if payload.get('prompt') == '':
            return {'response': ''}
        return {'response': json.dumps({
            'description_en': 'A red race car goes around a circuit.',
            'subjects': ['race car'], 'actions': ['turning'],
            'scene': 'racetrack', 'visible_text': [], 'uncertain': ['driver identity']
        })}

    def test_qwen_catalog_caches_individual_scene_and_exports(self):
        with patch.object(qwen_engine, 'describe_candidate') as mock_describe:
            # Fake imagery provided directly avoids GPU/video model dependencies.
            records = qwen_engine.analyze_catalog(
                self.candidates, cache_dir=self.tmp.name, transport=self.fake_ollama,
                frame_extractor=lambda c, n: ['ZmFrZQ=='] * n, log=lambda x: None)
            self.assertEqual(mock_describe.call_count, 0)
        self.assertEqual(records[0]['description_en'], 'A red race car goes around a circuit.')
        self.assertIn('race car', qwen_engine.caption_text(records[0]))
        self.assertEqual(sum(bool(p == '/api/generate' and x.get('prompt')) for p, x in self.calls), 1)
        self.calls = []
        records2 = qwen_engine.analyze_catalog(
            self.candidates, cache_dir=self.tmp.name, transport=self.fake_ollama,
            frame_extractor=lambda c, n: (_ for _ in ()).throw(AssertionError('cache miss')),
            log=lambda x: None)
        self.assertEqual(records2, records)
        self.assertEqual(sum(bool(p == '/api/generate' and x.get('prompt')) for p, x in self.calls), 0)
        qwen_engine.export_catalog(records, Path(self.tmp.name)/'out')
        self.assertTrue((Path(self.tmp.name)/'out'/'footage_catalog.csv').exists())

    def test_modified_file_invalidates_cache(self):
        qwen_engine.analyze_catalog(self.candidates, cache_dir=self.tmp.name,
           transport=self.fake_ollama, frame_extractor=lambda c, n: ['ZmFrZQ=='], log=lambda x: None)
        self.calls = []
        Path(self.candidates[0].path).write_bytes(b'file was changed')
        qwen_engine.analyze_catalog(self.candidates, cache_dir=self.tmp.name,
           transport=self.fake_ollama, frame_extractor=lambda c, n: ['ZmFrZQ=='], log=lambda x: None)
        self.assertEqual(sum(bool(p == '/api/generate' and x.get('prompt')) for p, x in self.calls), 1)

    def test_missing_model_is_actionable(self):
        def fake(path, payload):
            return {'models': []}
        with self.assertRaisesRegex(RuntimeError, 'ollama pull qwen3-vl:4b-instruct'):
            qwen_engine.analyze_catalog(self.candidates, cache_dir=self.tmp.name,
                transport=fake, frame_extractor=lambda c, n: [], log=lambda x: None)

    def test_validation_rejects_unsupported_fields(self):
        with self.assertRaisesRegex(ValueError, 'description_en'):
            qwen_engine._clean_fields({'scene': 'stadium'})
        with self.assertRaisesRegex(ValueError, 'frame'):
            qwen_engine.analyze_catalog(self.candidates, cache_dir=self.tmp.name,
                samples=0, transport=self.fake_ollama, log=lambda x: None)

    def test_limit_scans_only_first_n(self):
        candidates = [FakeCandidate(self.candidates[0].path, start=i, end=i + 2) for i in range(3)]
        records = qwen_engine.analyze_catalog(candidates, cache_dir=self.tmp.name,
            limit=1, transport=self.fake_ollama, frame_extractor=lambda c, n: ['ZmFrZQ=='],
            log=lambda x: None)
        self.assertEqual(len(records), 1)

    def test_semantic_fusion_can_override_weak_visual_score(self):
        import numpy as np
        from autoedit.ai_engine import plan_semantic
        c = [FakeCandidate(self.candidates[0].path), FakeCandidate(str(Path(self.tmp.name)/'other.mp4'))]
        Path(c[1].path).write_bytes(b'video2')
        beats = [{'index': 1, 'start_frame':0, 'end_frame':60, 'start':0, 'end':2, 'text':'red racing car', 'silent':False}]
        # Visual vectors favor candidate 2 marginally. Caption embeddings reverse it.
        feats = np.array([[[.6,.8]], [[.8,.6]]],dtype=float)
        txt = np.array([[1.0,0.0]])
        caps = np.array([[1.0,0.0]], dtype=float)
        # input wrong shape -> raises
        with self.assertRaises(ValueError):
            plan_semantic(c, beats, 'voice.wav', 2, feats, txt,
                caption_vectors=caps, catalog=[{},{}])
        caps = np.array([[1.0,0.0],[-1.0,0.0]],dtype=float)
        items = [{'description_en':'red race car'}, {'description_en':'blue street car'}]
        plan = plan_semantic(c, beats, 'voice.wav', 2, feats, txt,
                            caption_vectors=caps, catalog=items)
        self.assertEqual(plan['shots'][0]['source'], c[0].path)
        self.assertEqual(plan['shots'][0]['qwen_description'], 'red race car')

if __name__ == '__main__':
    unittest.main()
