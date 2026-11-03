"""Main pipeline. AI opt-in remains compatible with the original v0.1 paths."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from . import __version__
from .media import (require_ffmpeg, inspect_video, media_duration,
                    list_videos, detect_candidates, detect_voice_pauses)
from .planner import create_plan
from .exporter import export_metadata, render_mp4


def _get_transcription(narration: Path, *, model, language, device, capabilities=None, cache: Path, stop, log):
    from .ai_engine import transcribe_voice
    st = narration.stat()
    key = hashlib.sha256(f'{narration.resolve()}|{st.st_size}|{st.st_mtime_ns}|{model}|{language}|v02'.encode()).hexdigest()[:24]
    cache.mkdir(parents=True, exist_ok=True)
    name = cache / ('transcript_' + key + '.json')
    if name.is_file():
        log(f'Dùng Whisper cache: {name.name}')
        return json.loads(name.read_text(encoding='utf-8'))
    data = transcribe_voice(str(narration), model_name=model, language=language, device=device,
                            capabilities=capabilities, stop=stop, log=log)
    temp = name.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(name)
    return data


def process(source_dir: str, narration_path: str, output_dir: str,
            *, render: bool = False, seed: int = 404,
            intro_seconds: float = 30.0, intro_min: float = 1.2, intro_max: float = 2.0,
            body_min: float = 3.0, body_max: float = 6.0,
            width: int = 1920, height: int = 1080,
            threshold: float = 0.42, prefer_moving: bool = True,
            ai_enabled: bool = False, whisper_model: str = 'small',
            language: str = 'en', ai_device: str = 'auto',
            clip_model: str = 'openai/clip-vit-base-patch32',
            tags_file: str | None = None, review_threshold: float = .21,
            qwen_enabled: bool = False, qwen_model: str = 'qwen3-vl:4b-instruct',
            qwen_samples: int = 3,
            cache_dir: str | None = None,
            stop=None, log: Callable[[str], None] = print,
            progress: Callable[[float], None] = lambda x: None) -> dict:
    require_ffmpeg()
    src = Path(source_dir).resolve()
    narration = Path(narration_path).resolve()
    destination = Path(output_dir).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f'Thư mục footage không tồn tại: {src}')
    if not narration.is_file():
        raise FileNotFoundError(f'File narration không tồn tại: {narration}')
    if qwen_enabled and not ai_enabled:
        raise ValueError('Để ghép Qwen với narration phải bật Whisper + CLIP. Chế độ scan riêng không cần. ')
    if not 0 <= threshold <= 1:
        raise ValueError('Ngưỡng phát hiện cảnh phải từ 0 đến 1.')
    if not -1 <= review_threshold <= 1:
        raise ValueError('Ngưỡng CLIP review phải từ -1 đến 1.')
    if intro_min <= 0 or body_min <= 0 or intro_min > intro_max or body_min > body_max:
        raise ValueError('Khoảng độ dài shot không hợp lệ.')
    if destination == src or destination == narration.parent:
        raise ValueError('Thư mục xuất không được trùng thư mục footage hoặc audio.')
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('Thư mục xuất phải rỗng. Chọn thư mục mới để tránh ghi đè.')
    duration = media_duration(str(narration), stop=stop)
    from .media import probe
    data = probe(str(narration), stop=stop)
    if not any(s.get('codec_type') == 'audio' for s in data.get('streams', [])):
        raise ValueError('Narration phải có audio track.')
    log(f'AVI Independent Auto Editor {__version__} - ' + ('Whisper + CLIP' if ai_enabled else 'Legacy'))
    log(f'Audio narration: {duration:.2f} giây')
    cache = Path(cache_dir).expanduser() if cache_dir else (Path.home() / '.avi_autoedit_cache')
    transcript = None
    pause_points = []
    hardware = None
    if ai_enabled:
        from .hardware import probe_cuda, describe_hardware
        hardware = probe_cuda() if ai_device != 'cpu' else None
        if hardware is not None:
            log('Quet phan cung: ' + describe_hardware(hardware))
            for message in hardware['notes']:
                log('  ' + message)
        else:
            log('AI device: CPU (lua chon thu cong).')
        transcript = _get_transcription(narration, model=whisper_model, language=language,
                                        device=ai_device, capabilities=hardware, cache=cache, stop=stop, log=log)
        progress(.10)
    else:
        pause_points = detect_voice_pauses(str(narration), stop=stop)
        log(f'Phát hiện {len(pause_points)} khoảng nghỉ audio (chưa hiểu lời thoại).')
    paths = [p for p in list_videos(str(src)) if not Path(p).is_relative_to(destination)]
    if not paths:
        raise ValueError('Không tìm thấy video trong folder nguồn.')
    log(f'Tìm thấy {len(paths)} video nguồn.')
    candidates, assets = [], []
    for i, path in enumerate(paths, 1):
        if stop is not None and stop.is_set():
            raise InterruptedError('Đã dừng.')
        try:
            asset = inspect_video(path, stop=stop)
            assets.append(asset)
            new_candidates = detect_candidates(asset, threshold=threshold, stop=stop, log=log)
            candidates.extend(new_candidates)
            log(f'[{i}/{len(paths)}] {Path(path).name}: {asset.duration:.1f}s, {len(new_candidates)} cảnh')
        except InterruptedError:
            raise
        except Exception as exc:
            log(f'[{i}/{len(paths)}] BỎ QUA {Path(path).name}: {exc}')
        progress((.10 if ai_enabled else 0) + (.30 if ai_enabled else .65) * i / len(paths))
    if not candidates:
        raise ValueError('Không có candidate video hợp lệ.')
    if ai_enabled:
        from .ai_engine import (CLIPEncoder, words_to_beats, index_footage,
                                load_identity_tags, plan_semantic)
        usable = [c for c in candidates if c.duration >= .6]
        if prefer_moving and any(c.motion >= .006 for c in usable):
            usable = [c for c in usable if c.motion >= .006]
        if not usable:
            raise ValueError('Không có candidate dài tối thiểu 0,6 giây.')
        max_clip = max(c.duration for c in usable)
        beats = words_to_beats(transcript['words'], duration, intro_seconds=intro_seconds,
                               intro_range=(intro_min, intro_max), body_range=(body_min, body_max),
                               max_clip_seconds=max_clip)
        log(f'Whisper chia thành {len(beats)} đoạn narration có timestamp.')
        catalog = None
        if qwen_enabled:
            from .qwen_engine import analyze_catalog
            log(f'Qwen bắt đầu mô tả {len(usable)} đoạn footage; cache sẽ giữ qua các dự án.')
            catalog = analyze_catalog(usable, cache_dir=str(cache), model=qwen_model,
                                      samples=qwen_samples, stop=stop, log=log,
                                      progress=lambda x: progress(.40 + .16 * x))
        # Qwen is unloaded before CLIP loads: reduces peak GPU memory on 12 GB cards.
        encoder = CLIPEncoder(clip_model, device=ai_device, capabilities=hardware, log=log)
        features = index_footage(usable, encoder, cache_dir=str(cache), stop=stop, log=log,
                                 progress=lambda f: progress((.56 if qwen_enabled else .40) + (.19 if qwen_enabled else .35) * f))
        if stop is not None and stop.is_set():
            raise InterruptedError('Đã dừng.')
        vectors = encoder.encode_texts([b['text'] or 'A quiet scene.' for b in beats])
        caption_vectors = None
        if catalog:
            from .qwen_engine import caption_text
            caption_vectors = encoder.encode_texts([caption_text(item) for item in catalog])
        progress(.82)
        labels = load_identity_tags(tags_file, usable)
        if labels:
            log('Áp dụng nhãn nhân vật do người dùng cung cấp.')
        plan = plan_semantic(usable, beats, str(narration), duration, features, vectors,
                             seed=seed, width=width, height=height,
                             intro_seconds=intro_seconds, intro_range=(intro_min, intro_max),
                             body_range=(body_min, body_max), tags=labels,
                             review_threshold=review_threshold,
                             caption_vectors=caption_vectors, catalog=catalog)
        plan['ai'] = {'whisper_model': whisper_model, 'language': transcript['language'],
                      'qwen_enabled': qwen_enabled, 'qwen_model': qwen_model if qwen_enabled else None,
                      'clip_model': clip_model, 'device_mode': ai_device,
                      'whisper_device': transcript.get('device', 'unknown_cache'),
                      'clip_device': encoder.device,
                      'review_threshold': review_threshold,
                      'identity_tags_file': str(Path(tags_file).resolve()) if tags_file else None}
        progress(.84)
    else:
        plan = create_plan(candidates, str(narration), duration, seed=seed,
                           intro_seconds=intro_seconds,
                           intro_range=(intro_min, intro_max), body_range=(body_min, body_max),
                           width=width, height=height, prefer_moving=prefer_moving,
                           pause_points=pause_points)
    plan['sources'] = [vars(a) for a in assets]
    log(f"Timeline: {plan['stats']['shot_count']} shot, {plan['stats']['distinct_sources']} video nguồn")
    destination.mkdir(parents=True, exist_ok=True)
    export_metadata(plan, destination)
    if ai_enabled and qwen_enabled:
        from .qwen_engine import export_catalog
        export_catalog(catalog, destination)
    if ai_enabled:
        (destination / 'transcript.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2),
                                                      encoding='utf-8')
        (destination / 'transcript.txt').write_text('\n'.join(
            f"[{x['start']:.2f} - {x['end']:.2f}] {x['text']}" for x in transcript['segments']),
            encoding='utf-8')
        report = (f'AVI Independent Auto Editor {__version__} - Whisper + CLIP' + (' + Qwen' if qwen_enabled else '') + '\n'
                  f'Footage: {len(assets)} | Candidates: {len(candidates)}\n'
                  f'Narration: {narration.name} | {duration:.2f} giây\n'
                  f'Beats: {len(plan["beats"])} | Shots: {len(plan["shots"])}\n'
                  f'Reused clips: {plan["stats"]["reused_shots"]}\n'
                  f'Qwen model: {qwen_model if qwen_enabled else "OFF"}\n'
                  f'Whisper device: {plan["ai"]["whisper_device"]} | CLIP device: {plan["ai"]["clip_device"]}\n'
                  f'Review needed: {plan["stats"]["review_shots"]}\n'
                  'CLIP cosine_similarity KHÔNG phải xác suất chính xác.\n'
                  'Tên người/sự kiện không được CLIP xác minh: hãy bổ sung footage_tags.csv.\n'
                  'XML tham chiếu media gốc: đừng di chuyển file nguồn.\n')
    else:
        report = (f'AVI Independent Auto Editor {__version__} - không bật AI\n'
                  f'Video source: {len(assets)} | Candidate shot: {len(candidates)}\n'
                  f'Shot on timeline: {len(plan["shots"])} | Audio: {narration.name}\n'
                  f'Phát hiện khoảng nghỉ: {len(pause_points)}\n'
                  'Chế độ legacy chưa khớp ngữ nghĩa voice-hình.\n')
    (destination / 'QUALITY_REPORT.txt').write_text(report, encoding='utf-8')
    if render:
        def on_segment(i, n):
            progress((.85 if ai_enabled else .70) + (.14 if ai_enabled else .29) * i / n)
        path = render_mp4(plan, str(destination), stop=stop, log=log, progress=on_segment)
        log('Xuất MP4: ' + path)
    progress(1.0)
    log('HOÀN THÀNH: ' + str(destination / 'timeline_premiere.xml'))
    return plan


def scan_footage(source_dir: str, output_dir: str, *, qwen_model='qwen3-vl:4b-instruct',
                 qwen_samples=3, limit=None, cache_dir=None, threshold=.42,
                 stop=None, log=print, progress=lambda f: None):
    """Standalone Qwen catalog scan; no narration, Whisper or CLIP required."""
    from .qwen_engine import analyze_catalog, export_catalog
    from .media import require_ffmpeg, list_videos, inspect_video, detect_candidates
    require_ffmpeg()
    src = Path(source_dir).resolve()
    out = Path(output_dir).resolve()
    if not src.is_dir():
        raise FileNotFoundError('Không thấy folder footage: ' + str(src))
    if src == out or out.is_relative_to(src):
        raise ValueError('Thư mục báo cáo phải nằm ngoài kho footage.')
    paths = list_videos(str(src))
    if not paths:
        raise ValueError('Không có video trong thư mục.')
    scenes = []
    for i, filename in enumerate(paths, 1):
        if stop is not None and stop.is_set():
            raise InterruptedError('Đã dừng quét footage.')
        try:
            candidates = detect_candidates(inspect_video(filename, stop=stop), threshold=threshold, stop=stop, log=log)
            scenes.extend(c for c in candidates if c.duration >= .6)
        except InterruptedError:
            raise
        except Exception as exc:
            log(f'Bỏ qua file {Path(filename).name}: {exc}')
        progress(.2 * i / len(paths))
    if not scenes:
        raise ValueError('Không có phân đoạn video hợp lệ để phân tích.')
    log(f'Qwen: {len(scenes)} cảnh từ {len(paths)} video.')
    cache = str(Path(cache_dir).expanduser()) if cache_dir else str(Path.home() / '.avi_autoedit_cache')
    catalog = analyze_catalog(scenes, cache_dir=cache, model=qwen_model,
                              samples=qwen_samples, limit=limit, stop=stop, log=log,
                              progress=lambda x: progress(.2 + .8*x))
    export_catalog(catalog, out)
    log(f'Xuất {len(catalog)} mô tả: {out / "footage_catalog.csv"}')
    return catalog
