"""Local Qwen3-VL footage catalogue through Ollama's documented HTTP API.

No proprietary program files, remote API keys or external image uploads.
Images are sent only to the locally configured Ollama host (localhost).
Cache is per candidate and survives interrupted runs.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Callable

DEFAULT_MODEL = 'qwen3-vl:4b-instruct'
BASE_URL = 'http://127.0.0.1:11434'
CATALOG_VERSION = 'v03-3-instruct'

PROMPT = '''Analyze the attached images as consecutive samples of ONE short video shot, in order.
Describe ONLY facts visible in those images. Do not infer events, motives, exact place,
people's names or real identities unless words are clearly readable. Avoid guessing.
Be useful for matching these images to documentary narration, about ANY topic.
Return a JSON object with precisely these keys:
{
  "description_en": "one or two specific descriptive sentences, in English",
  "subjects": ["visible people/objects/animals, generic roles only"],
  "actions": ["observable movements or activities"],
  "scene": "visible environment or setting; unknown if unclear",
  "visible_text": ["clearly readable signs/text only"],
  "uncertain": ["claims that cannot be established from the images"]
}
No markdown and no extra prose. Descriptions should not assert proper names or events.
'''


# Ollama's /api/generate accepts a JSON Schema in its `format` field.
# Request constrained fields instead of trusting a prose-only response.
CATALOG_SCHEMA = {
    'type': 'object',
    'properties': {
        'description_en': {'type': 'string'},
        'subjects': {'type': 'array', 'items': {'type': 'string'}},
        'actions': {'type': 'array', 'items': {'type': 'string'}},
        'scene': {'type': 'string'},
        'visible_text': {'type': 'array', 'items': {'type': 'string'}},
        'uncertain': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['description_en', 'subjects', 'actions', 'scene',
                 'visible_text', 'uncertain'],
}


class QwenResponseError(ValueError):
    """All attempts failed. `last_reply` is diagnostic only; never cached as footage."""

    def __init__(self, message, last_reply=None, attempts=None):
        super().__init__(message)
        self.last_reply = last_reply
        self.attempts = attempts or []


def _api(path: str, payload: dict | None = None, *, timeout: int = 300,
         transport=None):
    """Injectable transport for deterministic offline tests."""
    if transport is not None:
        return transport(path, payload)
    if payload is None:
        req = urllib.request.Request(BASE_URL + path)
    else:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(BASE_URL + path, data=data,
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # An Ollama HTTP 400 is different from an unreachable Ollama server.
        body = exc.read(1000).decode('utf-8', errors='replace')
        raise RuntimeError(f'Ollama HTTP {exc.code}: {body[:500]}') from exc
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError('Không kết nối Ollama local (127.0.0.1:11434). '
                           'Hãy khởi động Ollama và kiểm tra model. Chi tiết: ' + str(exc)) from exc



def preferred_model(model):
    """Resolve old short aliases to non-thinking Instruct models for clip tagging.

    Those aliases were used by v0.3.3 and may still be present in old UI state.
    Do not map custom models or named '-thinking' variants silently.
    """
    aliases = {f'qwen3-vl:{n}': f'qwen3-vl:{n}-instruct'
               for n in ('2b', '4b', '8b')}
    return aliases.get(model, model)


def check_ollama(model=DEFAULT_MODEL, *, transport=None):
    model = preferred_model(model)
    data = _api('/api/tags', transport=transport, timeout=10)
    names = [x.get('name', '') for x in data.get('models', [])]
    if model not in names:
        raise RuntimeError(f'Chưa tải model {model}. Chạy: ollama pull {model}. '
                           f'Model sẵn có: {", ".join(names) or "(không có)"}')
    return names


def _catalog_key(candidate, model, samples):
    p = Path(candidate.path).resolve()
    st = p.stat()
    value = f'{CATALOG_VERSION}|{model}|{samples}|{p}|{st.st_size}|{st.st_mtime_ns}|{candidate.start:.5f}|{candidate.end:.5f}'
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]


def _images_for_candidate(candidate, samples=3):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('Thiếu opencv-python. Chạy CAI_MOT_LAN.bat.') from exc
    cap = cv2.VideoCapture(candidate.path)
    if not cap.isOpened():
        raise RuntimeError('Không đọc được footage: ' + candidate.path)
    items = []
    try:
        for k in range(samples):
            t = candidate.start + (candidate.end - candidate.start) * (k + .5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            ratio = min(1.0, 640 / max(1, h, w))
            if ratio < 1:
                frame = cv2.resize(frame, (int(w * ratio), int(h * ratio)))
            ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if ok:
                items.append(base64.b64encode(encoded.tobytes()).decode('ascii'))
    finally:
        cap.release()
    if not items:
        raise RuntimeError('Không trích được frame từ ' + candidate.path)
    return items


def _clean_fields(value):
    if not isinstance(value, dict):
        raise ValueError('Qwen không trả về JSON object.')
    def text(k):
        return str(value.get(k) or '').strip()[:1500]
    def arr(k):
        v = value.get(k, [])
        if not isinstance(v, list):
            return []
        return [str(x).strip()[:140] for x in v if str(x).strip()][:20]
    result = {'description_en': text('description_en'),
              'subjects': arr('subjects'), 'actions': arr('actions'),
              'scene': text('scene'), 'visible_text': arr('visible_text'),
              'uncertain': arr('uncertain')}
    if not result['description_en']:
        raise ValueError('Qwen trả JSON nhưng không có description_en.')
    return result


def _parse_response(reply):
    """Read a structured answer; tolerate wrappers, never invent scene facts."""
    if not isinstance(reply, dict):
        raise ValueError('Ollama trả về đối tượng không hợp lệ.')
    raw = reply.get('response', '')
    if isinstance(raw, dict):
        return _clean_fields(raw)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('Qwen trả response rỗng; done_reason=' + str(reply.get('done_reason', '?'))
                         + '; eval_count=' + str(reply.get('eval_count', '?'))
                         + '; thinking_chars=' + str(len(reply.get('thinking') or '')))
    raw = raw.strip().lstrip('\ufeff')
    # Some model/ollama versions add hidden reasoning or Markdown despite JSON mode.
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.I | re.S).strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I).strip()
    raw = re.sub(r'\s*```$', '', raw).strip()
    try:
        return _clean_fields(json.loads(raw))
    except (ValueError, TypeError):
        pass
    # Accept one complete embedded JSON object, but reject partial/truncated JSON.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', raw):
        try:
            parsed, _ = decoder.raw_decode(raw, match.start())
            return _clean_fields(parsed)
        except (ValueError, TypeError):
            continue
    raise ValueError('Không tìm thấy JSON hoàn chỉnh có description_en; '
                     'done_reason=' + str(reply.get('done_reason', '?')))


def _generate_fields(images, *, model=DEFAULT_MODEL, transport=None):
    """Generate constrained JSON; retry with a shorter task if needed."""
    errors = []
    last_reply = None
    for attempt in range(2):
        # Instruct variants produce an answer directly instead of spending the
        # entire generation budget on an internal reasoning phase.  When
        # retrying, fewer frames and a shorter prompt further reduce token use.
        payload = {
            'model': preferred_model(model),
            'prompt': PROMPT if attempt == 0 else (
                'Describe the visible content of these video frames. '
                'Return ONLY compact JSON with keys: description_en (sentence), '
                'subjects (array), actions (array), scene (string), '
                'visible_text (array), uncertain (array). '
                'Do not guess identities, events or locations.'),
            'images': images if attempt == 0 or len(images) <= 2
                       else [images[0], images[-1]],
            'stream': False, 'think': False,
            'format': CATALOG_SCHEMA if attempt == 0 else 'json',
            'options': {'temperature': 0, 'num_predict': 2048 if attempt else 1536,
                        'num_ctx': 8192},
            'keep_alive': '10m',
        }
        try:
            last_reply = _api('/api/generate', payload, transport=transport, timeout=600)
        except RuntimeError as exc:
            # Older Ollama builds may not support a schema format; retry with 'json'.
            if attempt == 0 and ('HTTP 400' in str(exc) or 'HTTP 422' in str(exc)):
                errors.append(str(exc))
                continue
            raise
        try:
            return _parse_response(last_reply)
        except ValueError as exc:
            errors.append(f'lần {attempt + 1}: {exc}')
    reason = last_reply.get('done_reason', '?') if isinstance(last_reply, dict) else '?'
    raise QwenResponseError(
        'Qwen trả JSON không hợp lệ sau 2 lần thử. '
        + '; '.join(errors) + '. done_reason=' + str(reason),
        last_reply=last_reply, attempts=errors)


def describe_candidate(candidate, *, model=DEFAULT_MODEL, samples=3,
                       transport=None):
    images = _images_for_candidate(candidate, samples=samples)
    return _generate_fields(images, model=preferred_model(model), transport=transport)


def _save_failure(root, key, candidate, exc):
    """Store safe-sized model text for debugging, not base64 frames or API keys."""
    errors_dir = root / 'qwen_errors'
    try:
        errors_dir.mkdir(parents=True, exist_ok=True)
        reply = getattr(exc, 'last_reply', None)
        record = {
            'source': str(candidate.path),
            'start': candidate.start,
            'end': candidate.end,
            'error': str(exc),
            'attempts': getattr(exc, 'attempts', []),
            'done_reason': reply.get('done_reason') if isinstance(reply, dict) else None,
            'eval_count': reply.get('eval_count') if isinstance(reply, dict) else None,
            'prompt_eval_count': reply.get('prompt_eval_count') if isinstance(reply, dict) else None,
            'thinking_chars': len(reply.get('thinking') or '') if isinstance(reply, dict) else None,
            'response': str(reply.get('response', ''))[:20000] if isinstance(reply, dict) else '',
        }
        path = errors_dir / (key + '.json')
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
        return path
    except OSError:
        return None


def unload_qwen(model=DEFAULT_MODEL, *, transport=None):
    try:
        _api('/api/generate', {'model': preferred_model(model), 'prompt': '', 'keep_alive': 0,
                               'stream': False}, transport=transport, timeout=45)
    except Exception:
        pass  # Cache completed descriptions even when model unload has a problem.


def analyze_catalog(candidates, *, cache_dir, model=DEFAULT_MODEL, samples=3,
                    limit=None, stop=None, log: Callable = print,
                    progress=lambda x: None, transport=None, frame_extractor=None):
    """Qwen describes arbitrary candidates. Uses separate atomic cache entry per scene.

    limit is for quick TEST scanning; never silently use a partial catalog for final edit.
    """
    if not 1 <= samples <= 8:
        raise ValueError('Số frame Qwen phải từ 1 đến 8.')
    resolved_model = preferred_model(model)
    if resolved_model != model:
        log(f'[Qwen] Đổi model cũ {model} -> {resolved_model} để tránh output rỗng.')
    model = resolved_model
    check_ollama(model, transport=transport)
    root = Path(cache_dir) / 'qwen_catalog'
    root.mkdir(parents=True, exist_ok=True)
    selected = list(candidates) if limit is None else list(candidates)[:max(0, limit)]
    result = []
    try:
        for i, c in enumerate(selected, 1):
            if stop is not None and stop.is_set():
                raise InterruptedError('Đã dừng phân tích kho footage.')
            name = _catalog_key(c, model, samples)
            item_path = root / (name + '.json')
            if item_path.exists():
                try:
                    item = json.loads(item_path.read_text(encoding='utf-8'))
                    if item.get('cache_key') != name:
                        raise ValueError('cache mismatch')
                    cached = True
                except (OSError, ValueError):
                    cached = False
            else:
                cached = False
            if not cached:
                try:
                    if frame_extractor is None:
                        item_fields = describe_candidate(c, model=model, samples=samples,
                                                         transport=transport)
                    else:
                        # Enables reliable testing without decoding video/model files.
                        item_fields = _generate_fields(frame_extractor(c, samples),
                                                       model=model, transport=transport)
                except QwenResponseError as exc:
                    error_file = _save_failure(root, name, c, exc)
                    detail = f' Chi tiết: {error_file}' if error_file else ''
                    raise ValueError(f'Qwen không mô tả được clip {Path(c.path).name}: {exc}.'
                                     + detail) from exc
                item = {**item_fields, 'cache_key': name, 'source': str(Path(c.path).resolve()),
                        'start': round(c.start, 4), 'end': round(c.end, 4),
                        'model': model, 'samples': samples}
                temp = item_path.with_suffix('.tmp')
                temp.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temp, item_path)
            result.append(item)
            log(f'Qwen {i}/{len(selected)} {Path(c.path).name} '
                f'{"[cache]" if cached else "[AI]"}: {item["description_en"][:105]}')
            progress(i / max(1, len(selected)))
    finally:
        unload_qwen(model, transport=transport)
    return result


def export_catalog(items, destination):
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'footage_catalog.json').write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'footage_catalog.csv').open('w', newline='', encoding='utf-8-sig') as f:
        cols = ['source', 'start', 'end', 'description_en', 'subjects', 'actions',
                'scene', 'visible_text', 'uncertain', 'model']
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for item in items:
            writer.writerow({key: ' | '.join(item.get(key, [])) if isinstance(item.get(key), list)
                             else item.get(key, '') for key in cols})


def caption_text(item):
    """Compact English text suitable for CLIP's 77-token text encoder."""
    return '. '.join(filter(None, [item.get('description_en', ''),
               ', '.join(item.get('subjects', [])[:5]),
               ', '.join(item.get('actions', [])[:4]), item.get('scene', '')]))[:350]
