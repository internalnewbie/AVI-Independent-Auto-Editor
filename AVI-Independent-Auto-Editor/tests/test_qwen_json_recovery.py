"""Failure cases from Ollama/Qwen formatting inconsistencies."""
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from autoedit import qwen_engine as qw

VALID = {"description_en": "A person walks across a street.",
         "subjects": ["person"], "actions": ["walking"],
         "scene": "street", "visible_text": [], "uncertain": []}


@dataclass
class Clip:
    path: str
    start: float = 0
    end: float = 5


class JsonRecoveryTests(unittest.TestCase):
    def test_normal_json(self):
        self.assertEqual(qw._parse_response({'response': json.dumps(VALID)}), VALID)

    def test_markdown_code_fence(self):
        answer = '```json\n' + json.dumps(VALID) + '\n```'
        self.assertEqual(qw._parse_response({'response': answer}), VALID)

    def test_think_prefix_and_prose_suffix(self):
        answer = '<think>an internal explanation</think>\nHere is the JSON:\n' + json.dumps(VALID) + '\nDone.'
        self.assertEqual(qw._parse_response({'response': answer}), VALID)

    def test_response_object(self):
        self.assertEqual(qw._parse_response({'response': VALID}), VALID)

    def test_empty_response_identifies_failure_reason(self):
        with self.assertRaisesRegex(ValueError, 'rỗng.*length'):
            qw._parse_response({'response': '', 'done_reason': 'length'})

    def test_partial_json_rejected_not_invented(self):
        with self.assertRaises(ValueError):
            qw._parse_response({'response': '{"description_en":"An unfinished scene", "subjects": ['})

    def test_retry_json_format_on_invalid_first(self):
        calls = []
        def transport(path, payload):
            calls.append(payload)
            if len(calls) == 1:
                return {'response': 'not JSON'}
            return {'response': json.dumps(VALID), 'done_reason': 'stop'}
        got = qw._generate_fields(['fakebase64'], transport=transport)
        self.assertEqual(got, VALID)
        self.assertEqual(calls[0]['format']['type'], 'object')
        self.assertEqual(calls[1]['format'], 'json')

    def test_retry_on_older_ollama_rejecting_schema(self):
        calls=[]
        def transport(path, payload):
            calls.append(payload)
            if len(calls) == 1:
                raise RuntimeError('Ollama HTTP 400: invalid format')
            return {'response': json.dumps(VALID)}
        self.assertEqual(qw._generate_fields(['img'], transport=transport), VALID)
        self.assertEqual(len(calls), 2)

    def test_failed_two_attempts_logged_and_not_cached(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'sample.mp4'
            source.write_bytes(b'sample footage')
            def transport(path, payload):
                if path=='/api/tags':
                    return {'models': [{'name': 'qwen3-vl:4b-instruct'}]}
                if not payload.get('prompt'):
                    return {'response': ''}
                return {'response': '{ "description_en": ', 'done_reason': 'length'}
            with self.assertRaisesRegex(ValueError, 'Chi tiết:'):
                qw.analyze_catalog([Clip(str(source))], cache_dir=td,
                    transport=transport, frame_extractor=lambda c,n:['fake'], log=lambda m:None)
            d=Path(td)/'qwen_catalog'
            self.assertEqual(list(d.glob('*.json')), [])
            logs=list((d/'qwen_errors').glob('*.json'))
            self.assertEqual(len(logs),1)
            self.assertEqual(json.loads(logs[0].read_text())['done_reason'], 'length')

    def test_no_name_guess_when_response_missing_description(self):
        with self.assertRaises(ValueError):
            qw._parse_response({'response':json.dumps({'scene':'street', 'subjects':['person']})})


if __name__=='__main__':
    unittest.main()
