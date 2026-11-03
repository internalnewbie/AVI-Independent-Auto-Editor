"""Run via: python -m unittest discover -s tests -v"""
import unittest
from autoedit.media import Candidate
from autoedit.planner import create_plan


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.samples = [Candidate('/a.mp4', 0, 40, .1), Candidate('/b.mp4', 0, 40, .1)]

    def test_complete_timeline_without_gaps(self):
        result = create_plan(self.samples, '/voice.wav', 35.23, seed=42)
        shots = result['shots']
        self.assertEqual(shots[0]['start_frame'], 0)
        self.assertEqual(shots[-1]['end_frame'], round(35.23*30))
        self.assertEqual(sum(s['duration_frames'] for s in shots), result['timeline']['frames'])
        self.assertTrue(all(a['end_frame'] == b['start_frame'] for a,b in zip(shots,shots[1:])))

    def test_seed_is_deterministic(self):
        first = create_plan(self.samples, '/voice.wav', 18, seed=24)
        second = create_plan(self.samples, '/voice.wav', 18, seed=24)
        self.assertEqual(first['shots'], second['shots'])

    def test_audio_pause_alignment(self):
        result = create_plan(self.samples, '/voice.wav', 12.0, seed=404,
                             intro_seconds=0, pause_points=[3.5, 7.0, 10.5],
                             body_range=(3.0,4.0))
        self.assertGreaterEqual(result['stats']['cuts_near_pauses'], 1)
        self.assertTrue(any(s['end_frame'] in [105, 210, 315] for s in result['shots']))

    def test_source_in_out_within_bounds(self):
        result = create_plan([Candidate('/c.mp4', 5, 6, .2)], '/voice.wav', 10)
        self.assertTrue(all(5 <= s['source_in'] < s['source_out'] <= 6.001 for s in result['shots']))

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            create_plan([], '/voice.wav', 10)


if __name__ == '__main__':
    unittest.main()
