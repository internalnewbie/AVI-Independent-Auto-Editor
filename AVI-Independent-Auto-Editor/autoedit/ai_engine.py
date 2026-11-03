"""Optional, local Whisper + CLIP components for AVI Auto Editor v0.2.

Models download on first use. No hosted inference and no proprietary executable code.
The CLIP similarity is a ranking heuristic, NOT a probability of correctness.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
from collections import Counter
from pathlib import Path
from typing import Callable

from .media import Candidate
from .planner import FPS


def transcribe_voice(audio_path: str, *, model_name: str = 'small', language: str = 'en',
                     device: str = 'auto', capabilities=None, stop=None,
                     log: Callable = print) -> dict:
    """Whisper with automatic CUDA->CPU failover, including lazy decode errors."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Chưa cài faster-whisper. Chạy CAI_MOT_LAN.bat.') from exc
    from .hardware import probe_cuda, select_device
    caps = capabilities if capabilities is not None else (probe_cuda() if device != 'cpu' else {})
    selected = select_device(device, backend='whisper', capabilities=caps)
    failure = None
    for actual in ([selected, 'cpu'] if device == 'auto' and selected == 'cuda' else [selected]):
        try:
            log(f'Whisper {model_name}: dang chay {actual.upper()}...')
            model = WhisperModel(model_name, device=actual,
                                 compute_type='float16' if actual == 'cuda' else 'int8')
            kwargs = dict(beam_size=5, vad_filter=True, word_timestamps=True,
                          condition_on_previous_text=False)
            if language and language.lower() != 'auto':
                kwargs['language'] = language
            segments, info = model.transcribe(audio_path, **kwargs)
            rows, words = [], []
            for part in segments:  # Whisper computation is lazy: consume inside try.
                if stop is not None and stop.is_set():
                    raise InterruptedError('Da dung Whisper.')
                row = {'start': round(float(part.start), 3), 'end': round(float(part.end), 3),
                       'text': part.text.strip()}
                rows.append(row)
                if part.words:
                    for w in part.words:
                        if w.start is not None and w.end is not None and w.word.strip():
                            words.append({'start': max(0.0, float(w.start)),
                                          'end': max(0.0, float(w.end)), 'text': w.word.strip()})
                elif row['text']:
                    words.append(dict(row))
            if not words:
                raise RuntimeError('Whisper khong tim thay loi noi trong narration.')
            log(f'Whisper: {len(rows)} cau, {len(words)} tu ({actual.upper()})')
            return {'language': info.language, 'model': model_name, 'segments': rows,
                    'words': words, 'device': actual, 'fallback_reason': failure}
        except InterruptedError:
            raise
        except (RuntimeError, OSError) as exc:
            if actual != 'cuda' or device != 'auto':
                raise
            failure = f'{type(exc).__name__}: {str(exc)[:300]}'
            log(f'Whisper CUDA loi, tu chuyen CPU: {failure}')
            # Reattempt from the beginning, never mix partial segments from GPU and CPU.
    raise RuntimeError('Whisper khong khoi tao duoc tren bat ky thiet bi nao.')


def _normalized_text(items: list[dict]) -> str:
    s = ' '.join(i['text'].strip() for i in items if i['text'].strip())
    return re.sub(r'\s+([.,;:!?])', r'\1', s).strip()


def words_to_beats(words: list[dict], duration: float, *, intro_seconds: float = 30,
                   intro_range=(1.2, 2.0), body_range=(3.0, 6.0),
                   max_clip_seconds: float = 6.0, fps: int = FPS) -> list[dict]:
    """Partition the entire narration duration into frame-accurate beats.

    Prefers Whisper word-end boundaries (punctuation is also preferred),
    but a hard time limit may force a cut mid-phrase. Silence retains a beat.
    """
    all_frames = round(duration * fps)
    if all_frames <= 0:
        raise ValueError('Narration có thời lượng không hợp lệ.')
    max_clip_frames = max(1, round(max_clip_seconds * fps))
    ends = sorted({(round(w['end'] * fps), w['text']) for w in words
                   if 0 < round(w['end'] * fps) < all_frames})
    beats = []
    head = 0
    while head < all_frames:
        low, high = intro_range if head < round(intro_seconds * fps) else body_range
        max_len = min(max_clip_frames, max(1, round(high * fps)))
        min_len = min(max_len, max(1, round(low * fps)))
        length = min(all_frames - head, max_len)
        if head < round(intro_seconds * fps):
            intro_left = round(intro_seconds * fps) - head
            if intro_left > 0:
                length = min(length, intro_left)
        if length < all_frames - head:
            options = [(p, text) for p, text in ends if head + min_len <= p <= head + length]
            if options:
                target = head + int((min_len + length) * 0.5)
                boundary = min(options, key=lambda item: (abs(item[0] - target) -
                              (int(.35 * fps) if re.search(r'[.!?;:]$', item[1]) else 0), -item[0]))
                length = boundary[0] - head
        if length < 1:
            length = 1
        tail = head + length
        selected = [w for w in words
                    if head <= (w['start'] + w['end']) * fps / 2 < tail]
        if not selected:
            # Silent beat: retain the previous speech context, never invent new speech.
            earlier = [w for w in words if w['end'] * fps <= tail]
            selected = earlier[-10:] if earlier else words[:10]
        beats.append({'index': len(beats) + 1, 'start_frame': head, 'end_frame': tail,
                      'start': round(head / fps, 3), 'end': round(tail / fps, 3),
                      'text': _normalized_text(selected),
                      'silent': not any(head <= (w['start'] + w['end']) * fps / 2 < tail
                                        for w in words)})
        head = tail
    return beats


def _pytorch_dependencies():
    try:
        import torch
        import numpy as np
        from PIL import Image
        from transformers import AutoProcessor, CLIPModel
    except ImportError as exc:
        raise RuntimeError('Thiếu CLIP/Torch/Pillow. Cài: py -3 -m pip install -r requirements-ai.txt') from exc
    return torch, np, Image, AutoProcessor, CLIPModel


class CLIPEncoder:
    """CLIP with independent GPU selection and CPU fallback in auto mode."""
    def __init__(self, model_name='openai/clip-vit-base-patch32', device='auto',
                 capabilities=None, log=print):
        from .hardware import probe_cuda, select_device
        self.torch, self.np, _, processor, model = _pytorch_dependencies()
        caps = capabilities if capabilities is not None else (probe_cuda() if device != 'cpu' else {})
        desired = select_device(device, backend='clip', capabilities=caps)
        self.allow_fallback = device == 'auto'
        self.log = log
        log(f'Nap CLIP {model_name}...')
        self.processor = processor.from_pretrained(model_name)
        self.model = model.from_pretrained(model_name).eval()
        self.device = 'cpu'
        self.model_name = model_name
        if desired == 'cuda':
            try:
                self.model.to('cuda')
                self.device = 'cuda'
            except (RuntimeError, OSError) as exc:
                if not self.allow_fallback:
                    raise
                log('CLIP CUDA loi, tu chuyen CPU: ' + str(exc)[:240])
                self.model.to('cpu')
                self.torch.cuda.empty_cache()
        log(f'CLIP device: {self.device.upper()}')

    def _normalize(self, arr):
        arr = arr.float()
        return arr / arr.norm(dim=-1, keepdim=True).clamp(min=1e-8)

    def _is_gpu_error(self, exc):
        msg = str(exc).lower()
        return any(term in msg for term in ('cuda', 'cublas', 'cudnn', 'out of memory',
                                             'device-side', 'gpu', 'driver'))

    def _encode_batch(self, values, *, kind):
        kwargs = {'text': values, 'padding': True, 'truncation': True, 'max_length': 77} if kind == 'text' else {'images': values}
        inputs = self.processor(return_tensors='pt', **kwargs)
        def perform():
            inp = {n: t.to(self.device) for n, t in inputs.items()}
            with self.torch.inference_mode():
                feat = (self.model.get_text_features(**inp) if kind == 'text'
                        else self.model.get_image_features(**inp))
                if not self.torch.is_tensor(feat):
                    feat = feat.pooler_output
                return self._normalize(feat).cpu().numpy()
        try:
            return perform()
        except (RuntimeError, OSError) as exc:
            if self.device != 'cuda' or not self.allow_fallback or not self._is_gpu_error(exc):
                raise
            self.log('CLIP gap loi CUDA, tu chuyen CPU: ' + str(exc)[:240])
            self.device = 'cpu'
            self.model.to('cpu')
            self.torch.cuda.empty_cache()
            return perform()

    def encode_texts(self, texts: list[str], batch_size: int = 16):
        return self.np.concatenate([self._encode_batch(texts[k:k+batch_size], kind='text')
                                    for k in range(0, len(texts), batch_size)], axis=0)

    def encode_images(self, images: list, batch_size: int = 16):
        return self.np.concatenate([self._encode_batch(images[k:k+batch_size], kind='image')
                                    for k in range(0, len(images), batch_size)], axis=0)


def _candidate_cache_key(candidates: list[Candidate], model: str, samples: int) -> str:
    digest = hashlib.sha256()
    digest.update((model + ':' + str(samples) + ':v02').encode())
    for c in candidates:
        p = Path(c.path)
        st = p.stat()
        digest.update(f'{p.resolve()}|{st.st_size}|{st.st_mtime_ns}|{c.start:.4f}|{c.end:.4f}\n'.encode())
    return digest.hexdigest()[:24]


def _video_frames(candidate: Candidate, cap, count: int):
    import cv2
    from PIL import Image
    frames = []
    # Sample across the clip; use more than one frame to avoid misleading thumbnails.
    for n in range(count):
        pos = candidate.start + candidate.duration * (n + 0.5) / count
        cap.set(cv2.CAP_PROP_POS_MSEC, pos * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = min(1.0, 640 / max(h, w))
        if scale < 1:
            frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
        frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    return frames


def index_footage(candidates: list[Candidate], encoder: CLIPEncoder, *,
                  cache_dir: str, samples: int = 3, stop=None, log=print,
                  progress=lambda x: None):
    """Return (num_candidates, samples, embedding_dim) float32 tensor.

    The cached index fingerprints source path, mtime, size and candidate boundaries.
    """
    import numpy as np
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('Cần opencv-python để đọc ảnh trong clip.') from exc
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    key = _candidate_cache_key(candidates, encoder.model_name, samples)
    cache = root / f'clip_index_{key}.npz'
    if cache.is_file():
        with np.load(cache, allow_pickle=False) as data:
            saved = data['features']
        if len(saved) == len(candidates) and saved.shape[1] == samples:
            log(f'Tải CLIP cache: {cache.name} (không phân tích lại 320 clip nếu không đổi)')
            progress(1.0)
            return saved
    pictures, coords = [], []
    features = None
    cap = None
    path = None

    def flush():
        nonlocal pictures, coords, features
        if not pictures:
            return
        encoded = encoder.encode_images(pictures)
        if features is None:
            features = np.zeros((len(candidates), samples, encoded.shape[-1]), dtype=np.float32)
        for (ci, si), vec in zip(coords, encoded):
            features[ci, si, :] = vec
        pictures, coords = [], []

    try:
        for i, c in enumerate(candidates):
            if stop is not None and stop.is_set():
                raise InterruptedError('Đã dừng lập chỉ mục CLIP.')
            if c.path != path:
                if cap is not None:
                    cap.release()
                path = c.path
                cap = cv2.VideoCapture(path)
            if cap is None or not cap.isOpened():
                log(f'CLIP: Không đọc được {c.path}')
                continue
            for j, img in enumerate(_video_frames(c, cap, samples)):
                pictures.append(img)
                coords.append((i, j))
                if len(pictures) >= 24:
                    flush()
            if i == 0 or (i + 1) % 25 == 0 or i + 1 == len(candidates):
                progress((i + 1) / len(candidates))
                log(f'CLIP index: {i + 1}/{len(candidates)} candidate')
        flush()
    finally:
        if cap is not None:
            cap.release()
    if features is None or not np.any(features):
        raise RuntimeError('CLIP không đọc được bất kỳ khung hình nào từ footage.')
    temp = root / (cache.name + '.tmp.npz')
    np.savez_compressed(temp, features=features)
    os.replace(temp, cache)
    return features


def load_identity_tags(path: str | None, candidates: list[Candidate]) -> dict:
    """CSV file,people,keywords where people/keywords use | separators.

    Labels come from the user's curation, NOT automatic face identification.
    """
    if not path or not Path(path).is_file():
        return {}
    lookup = {}
    with open(path, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            key = (row.get('file') or '').strip().replace('\\', '/').casefold()
            if not key:
                continue
            lookup[key] = {
                'people': {x.strip().casefold() for x in (row.get('people') or '').split('|') if x.strip()},
                'keywords': {x.strip().casefold() for x in (row.get('keywords') or '').split('|') if x.strip()},
            }
    tags = {}
    for c in candidates:
        p = Path(c.path)
        tags[c.path] = lookup.get(p.name.casefold(), lookup.get(p.as_posix().casefold(),
                       {'people': set(), 'keywords': set()}))
    return tags


def match_score_matrix(features, text_vectors):
    """Cosine similarities of best sampled frame per candidate and beat."""
    import numpy as np
    valid = np.linalg.norm(features, axis=2) > 0.00001
    sims = np.einsum('cse,be->bcs', features, text_vectors)
    sims[~valid[None, :, :].repeat(len(text_vectors), axis=0)] = -1.0
    return sims.max(axis=2)


def _mentioned_entities(text: str, all_entities: set[str]) -> set[str]:
    normalized = text.casefold()
    matched = {name for name in all_entities
               if re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', normalized)}
    # A narrow heuristic for royalty/person titles; this does not identify faces.
    matched.update(m.group(0).casefold() for m in re.finditer(
        r'\b(?:prince|princess|king|queen|duke|duchess|lord|lady)\s+[A-Za-z][A-Za-z\x27-]+\b',
        normalized, flags=re.IGNORECASE))
    return matched


def plan_semantic(candidates: list[Candidate], beats: list[dict], audio_path: str,
                  narration_duration: float, features, text_vectors, *,
                  seed=404, width=1920, height=1080,
                  intro_seconds=30, intro_range=(1.2, 2.0), body_range=(3.0, 6.0),
                  tags=None, review_threshold=0.21,
                  caption_vectors=None, catalog=None, caption_weight=.28) -> dict:
    """Select best semantic match; novel near-equivalent clips beat reused clips.

    Explicit identity labels are strong constraints. Untagged scenes remain
    possible but flagged when a named person is present in the script.
    """
    import numpy as np
    if not candidates or not beats:
        raise ValueError('Không có candidate hoặc beat.')
    if len(features) != len(candidates) or len(text_vectors) != len(beats):
        raise ValueError('Embedding dimensions không khớp candidate/beat.')
    rng = random.Random(seed)
    scores = match_score_matrix(features, text_vectors)
    if caption_vectors is not None:
        if caption_vectors.shape != (len(candidates), text_vectors.shape[1]):
            raise ValueError('Embedding Qwen caption dimensions không khớp CLIP.')
        import numpy as np
        cap_score = np.matmul(text_vectors, caption_vectors.T)
        scores = (1.0 - caption_weight) * scores + caption_weight * cap_score
    catalog = catalog or []
    if catalog and len(catalog) != len(candidates):
        raise ValueError('Qwen catalog length không khớp candidate.')
    tags = tags or {}
    known_people = set().union(*(v.get('people', set()) for v in tags.values())) if tags else set()
    known_keywords = set().union(*(v.get('keywords', set()) for v in tags.values())) if tags else set()
    consumed = Counter()
    shots = []
    details = []
    for bi, beat in enumerate(beats):
        start, end = beat['start_frame'], beat['end_frame']
        frames = end - start
        if frames < 1:
            continue
        viable = [i for i, c in enumerate(candidates) if round(c.duration * FPS) >= frames]
        if not viable:
            raise ValueError(f'Beat {bi+1}: không có footage đủ dài ({frames/FPS:.2f}s). '
                             'Giảm body_max hoặc sử dụng clip nguồn dài hơn.')
        mentioned = _mentioned_entities(beat['text'], known_people)
        keywords = _mentioned_entities(beat['text'], known_keywords)
        raw = scores[bi]
        score_map = {}
        candidate_meta = {}
        for idx in viable:
            c = candidates[idx]
            lab = tags.get(c.path, {'people': set(), 'keywords': set()})
            people = lab.get('people', set())
            kw = lab.get('keywords', set())
            # A known contradictory label is not evidence of the named person.
            mismatch = bool(mentioned and people and people.isdisjoint(mentioned))
            bonus = (0.20 * len(people.intersection(mentioned)) / len(mentioned)) if mentioned else 0.0
            bonus += 0.05 if keywords and not kw.isdisjoint(keywords) else 0.0
            if mentioned and not people:
                bonus -= 0.04  # unknown identity; allow if no labelled match
            if mismatch:
                bonus -= 0.25
            value = float(raw[idx]) + bonus
            score_map[idx] = value
            candidate_meta[idx] = (mismatch, bool(mentioned and not people))
        # Always prioritize a confirmed name match over an explicitly wrong name.
        if mentioned:
            positives = [idx for idx in viable if not tags.get(candidates[idx].path, {}).get('people', set()).isdisjoint(mentioned)]
            if positives:
                complete = [idx for idx in positives
                            if mentioned.issubset(tags.get(candidates[idx].path, {}).get('people', set()))]
                viable = complete or positives
            else:
                nonconflicting = [idx for idx in viable if not candidate_meta[idx][0]]
                if nonconflicting:
                    viable = nonconflicting
        best = max(score_map[i] for i in viable)
        # Only sacrifice a tiny score margin to favor footage not used before.
        comparable = [i for i in viable if score_map[i] >= best - 0.035]
        comparable.sort(key=lambda i: (consumed[(candidates[i].path, candidates[i].start)],
                                        candidates[i].path == (shots[-1]['source'] if shots else ''),
                                        -score_map[i], rng.random()))
        chosen_idx = comparable[0]
        c = candidates[chosen_idx]
        # Exact length; avoids over-reading the source clip.
        margin = max(0.0, c.duration - frames / FPS)
        # Center window for reproducible visual semantics around CLIP samples.
        offset = max(0.0, margin * 0.5)
        source_in = c.start + offset
        match_score = round(float(raw[chosen_idx]), 4)
        reasons = []
        if match_score < review_threshold:
            reasons.append('low_clip_similarity')
        if mentioned and not mentioned.issubset(tags.get(c.path, {}).get('people', set())):
            reasons.append('identity_not_confirmed')
        if beat.get('silent'):
            reasons.append('silence_context_reused')
        reused = consumed[(c.path, c.start)] > 0
        shot = {
            'index': len(shots) + 1, 'source': c.path,
            'source_in': round(source_in, 5),
            'source_out': round(source_in + frames / FPS, 5),
            'start_frame': start, 'end_frame': end, 'duration_frames': frames,
            'motion': c.motion,
            'beat_index': beat['index'], 'narration_text': beat['text'],
            'match_score': match_score,
            'qwen_description': catalog[chosen_idx]['description_en'] if catalog else '',
            'mentioned_entities': '|'.join(sorted(mentioned)),
            'review_reason': '|'.join(reasons), 'footage_reused': reused,
        }
        shots.append(shot)
        consumed[(c.path, c.start)] += 1
        details.append({'beat': beat['index'], 'start': beat['start'], 'end': beat['end'],
                        'text': beat['text'], 'clip': Path(c.path).name,
                        'cosine_similarity': match_score, 'semantic_similarity': match_score,
                        'qwen_description': shot['qwen_description'],
                        'used_count': consumed[(c.path, c.start)],
                        'people_mentioned': shot['mentioned_entities'], 'review_reason': shot['review_reason'], 'footage_reused': reused})
    total_frames = round(narration_duration * FPS)
    if shots[0]['start_frame'] != 0 or shots[-1]['end_frame'] != total_frames or any(
            x['end_frame'] != y['start_frame'] for x, y in zip(shots, shots[1:])):
        raise AssertionError('Timeline bị hở hoặc chồng frame.')
    return {
        'app': 'AVI Independent Auto Editor', 'version': '0.3.0', 'ai_enabled': True,
        'timeline': {'fps': FPS, 'width': width, 'height': height,
                     'frames': total_frames, 'duration_seconds': total_frames / FPS},
        'narration': str(Path(audio_path).resolve()), 'seed': seed,
        'intro_seconds': intro_seconds, 'settings': {'intro_range': list(intro_range),
                                                   'body_range': list(body_range),
                                                   'semantic_matching': True},
        'beats': beats, 'shots': shots, 'match_report': details,
        'stats': {'shot_count': len(shots), 'distinct_sources': len(set(s['source'] for s in shots)),
                  'available_candidates': len(candidates),
                  'reused_shots': sum(s['footage_reused'] for s in shots),
                  'review_shots': sum(bool(s['review_reason']) for s in shots)}
    }


def create_tag_csv(source_dir: str, destination: str) -> None:
    from .media import list_videos
    names = list_videos(source_dir)
    with open(destination, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['file', 'people', 'keywords'])
        for path in names:
            writer.writerow([Path(path).name, '', ''])
