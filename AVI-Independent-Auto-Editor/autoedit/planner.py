"""Generate repeat-aware editable timelines aligned to narration duration."""
from __future__ import annotations

import random
from collections import Counter, deque
from pathlib import Path
from .media import Candidate

FPS = 30


def create_plan(candidates: list[Candidate], audio_path: str, narration_duration: float,
                *, seed: int = 404, intro_seconds: float = 30.0,
                intro_range: tuple[float, float] = (1.2, 2.0),
                body_range: tuple[float, float] = (3.0, 6.0),
                width: int = 1920, height: int = 1080,
                prefer_moving: bool = True, pause_points: list[float] | None = None) -> dict:
    if not candidates:
        raise ValueError('Không có footage đủ điều kiện để dựng.')
    if narration_duration <= 0:
        raise ValueError('Audio narration phải có độ dài lớn hơn 0.')
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError('Độ phân giải phải là số dương chẵn.')
    rng = random.Random(seed)
    usable = [c for c in candidates if c.duration >= .6]
    if not usable:
        raise ValueError('Không có cảnh nào dài ít nhất 0,6 giây.')
    moving = [c for c in usable if c.motion >= .006]
    # If all available clips are static, do not produce an empty project.
    if prefer_moving and moving:
        usable = moving
    rng.shuffle(usable)
    total_frames = max(1, round(narration_duration * FPS))
    remaining = total_frames
    pause_frames = sorted(set(round(p * FPS) for p in (pause_points or []) if 0 < p < narration_duration))
    aligned_cuts = 0
    head = 0
    shots = []
    recently_used = deque(maxlen=min(5, max(1, len(set(c.path for c in usable)) - 1)))
    consumed = Counter()
    while remaining > 0:
        current_seconds = head / FPS
        low, high = intro_range if current_seconds < intro_seconds else body_range
        goal_frames = min(remaining, max(1, round(rng.uniform(low, high) * FPS)))
        # Hard cut at end of intro, then switch to slower cuts.
        if current_seconds < intro_seconds:
            intro_left = round(intro_seconds * FPS) - head
            if intro_left > 0:
                goal_frames = min(goal_frames, intro_left)
        # Prefer naturally quiet boundaries close to the requested cut duration.
        # No transcription/AI is involved; only pause positions from audio level.
        from_pause = [p-head for p in pause_frames
                      if max(1, round(low*FPS)) <= p-head <= min(remaining, round(high*FPS))]
        pause_goal = None
        if from_pause:
            snapped = min(from_pause, key=lambda span: abs(span-goal_frames))
            if current_seconds >= intro_seconds or head+snapped <= round(intro_seconds*FPS):
                goal_frames = snapped
                pause_goal = snapped
        # Pick with anti-repeat: use unused scenes before revisiting; avoid recent source.
        viable = [c for c in usable if round(c.duration * FPS) >= goal_frames]
        if not viable:
            viable = usable
        viable.sort(key=lambda c: (
            consumed[(c.path, c.start)],
            c.path in recently_used,
            -c.motion,
            rng.random(),
        ))
        # Randomly choose from the best-scoring pool (all unused novel sources).
        baseline = consumed[(viable[0].path, viable[0].start)]
        fresh = [c for c in viable if consumed[(c.path, c.start)] == baseline and c.path not in recently_used]
        chosen = rng.choice(fresh[:min(12, len(fresh))]) if fresh else viable[0]
        allowed = max(1, round(chosen.duration * FPS))
        frames = min(remaining, goal_frames, allowed)
        frames = max(1, frames)
        if pause_goal is not None and frames == pause_goal:
            aligned_cuts += 1
        clip_seconds = frames / FPS
        margin = max(0.0, chosen.duration - clip_seconds)
        # Random subposition in the original media. Avoid overread by ~one frame.
        offset = rng.uniform(0, max(0, margin-1/FPS)) if margin > 1/FPS else 0.0
        source_in = round(chosen.start + offset, 5)
        shots.append({
            'index': len(shots) + 1,
            'source': chosen.path,
            'source_in': source_in,
            'source_out': round(source_in + clip_seconds, 5),
            'start_frame': head,
            'end_frame': head + frames,
            'duration_frames': frames,
            'motion': chosen.motion,
        })
        head += frames
        remaining -= frames
        recently_used.append(chosen.path)
        consumed[(chosen.path, chosen.start)] += 1
    return {
        'app': 'AVI Independent Auto Editor', 'version': '0.1.0',
        'timeline': {'fps': FPS, 'width': width, 'height': height,
                     'frames': total_frames, 'duration_seconds': round(total_frames / FPS, 5)},
        'narration': str(Path(audio_path).resolve()),
        'seed': seed, 'intro_seconds': intro_seconds, 'voice_pause_points': pause_points or [],
        'settings': {'intro_range': list(intro_range), 'body_range': list(body_range),
                     'prefer_moving': prefer_moving},
        'shots': shots,
        'stats': {'shot_count': len(shots), 'distinct_sources': len(set(x['source'] for x in shots)),
                  'available_candidates': len(candidates), 'cuts_near_pauses': aligned_cuts},
    }
