"""Tests for the real semantic matching algorithm, with deterministic mock embeddings.
External model weights are not required for these behavioral tests.
"""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from autoedit.ai_engine import (words_to_beats, plan_semantic, match_score_matrix,
                                create_tag_csv, load_identity_tags)
from autoedit.media import Candidate
from autoedit.exporter import export_metadata


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [Candidate('/tmp/william_A.mp4', 0, 10, .2),
                           Candidate('/tmp/william_B.mp4', 0, 10, .2),
                           Candidate('/tmp/charles.mp4', 0, 10, .2)]
        self.beats = [dict(index=i+1, start_frame=i*120, end_frame=(i+1)*120,
                           start=i*4.0, end=(i+1)*4.0, text='Prince William walks at Windsor',
                           silent=False) for i in range(3)]
        self.embed = np.array([[[.99, .1]], [[.99, .1]], [[.3, .95]]], dtype='float32')
        self.embed /= np.linalg.norm(self.embed, axis=2, keepdims=True)
        self.text = np.array([[1, 0]] * 3, dtype='float32')

    def plan(self, **kwargs):
        return plan_semantic(self.candidates, self.beats, '/tmp/voice.wav', 12,
                             self.embed, self.text, **kwargs)

    def test_prefers_new_equally_relevant_footage(self):
        p = self.plan()
        self.assertNotEqual(p['shots'][0]['source'], p['shots'][1]['source'])
        self.assertEqual(p['shots'][2]['source'], p['shots'][0]['source'])
        self.assertEqual(p['stats']['reused_shots'], 1)
        self.assertEqual([x['start_frame'] for x in p['shots']], [0, 120, 240])
        self.assertEqual(p['shots'][-1]['end_frame'], 360)

    def test_reuse_beats_semantically_incorrect_new_clip(self):
        self.embed[1] = [[-.6, .8]]  # unrelated new clip
        p = self.plan()
        self.assertEqual(p['shots'][0]['source'], p['shots'][1]['source'])

    def test_person_tags_override_mismatched_identity(self):
        self.embed[2] = [[1.0, 0.0]]  # visually closest, but explicitly WRONG person
        tags = {self.candidates[0].path: {'people': {'prince william'}, 'keywords': set()},
                self.candidates[1].path: {'people': {'prince william'}, 'keywords': set()},
                self.candidates[2].path: {'people': {'king charles'}, 'keywords': set()}}
        p = self.plan(tags=tags)
        self.assertTrue(all('william_' in s['source'] for s in p['shots']))
        self.assertTrue(all(s['mentioned_entities'] == 'prince william' for s in p['shots']))

    def test_missing_identity_label_flags_review(self):
        tags = {self.candidates[0].path: {'people': set(), 'keywords': set()},
                self.candidates[1].path: {'people': {'king charles'}, 'keywords': set()},
                self.candidates[2].path: {'people': {'king charles'}, 'keywords': set()}}
        p = self.plan(tags=tags)
        self.assertTrue(all('identity_not_confirmed' in s['review_reason'] for s in p['shots']))

    def test_score_below_threshold_flags_review(self):
        self.embed[:] = [[[0, 1]], [[0, 1]], [[0, 1]]]
        p = self.plan(review_threshold=0.2)
        self.assertTrue(all('low_clip_similarity' in s['review_reason'] for s in p['shots']))

    def test_beat_alignment_complete_without_gaps(self):
        words = [dict(start=i*.7+0.2, end=i*.7+.6,
                      text=('William.' if i%6==5 else 'goes')) for i in range(15)]
        beats = words_to_beats(words, 11.2, intro_seconds=3,
                               intro_range=(1.2, 2), body_range=(3, 6), max_clip_seconds=5)
        self.assertEqual(beats[0]['start_frame'], 0)
        self.assertEqual(beats[-1]['end_frame'], round(11.2 * 30))
        self.assertTrue(all(a['end_frame'] == b['start_frame'] for a,b in zip(beats, beats[1:])))
        self.assertTrue(all(0 < (b['end_frame']-b['start_frame']) <= 150 for b in beats))

    def test_exports_match_report_csv_and_xml(self):
        p = self.plan()
        p['sources'] = []
        with tempfile.TemporaryDirectory() as td:
            export_metadata(p, Path(td))
            self.assertTrue((Path(td) / 'match_report.csv').exists())
            self.assertTrue((Path(td) / 'timeline_premiere.xml').exists())
            self.assertTrue((Path(td) / 'beats.json').exists())
            with (Path(td) / 'match_report.csv').open(encoding='utf-8-sig') as file:
                report = list(csv.DictReader(file))
            self.assertEqual(len(report), 3)
            self.assertIn('cosine_similarity', report[0])
            self.assertEqual(len(json.loads((Path(td)/'plan.json').read_text())['shots']), 3)


if __name__ == '__main__':
    unittest.main()
