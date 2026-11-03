"""Write a Premiere-compatible FCP7 XML and optionally encode a review MP4."""
from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable
from .media import run_checked


def _node(parent, name, text=None, **attrs):
    child = ET.SubElement(parent, name, attrs)
    if text is not None:
        child.text = str(text)
    return child


def _rate(parent, fps=30):
    item = _node(parent, 'rate')
    _node(item, 'timebase', str(fps))
    _node(item, 'ntsc', 'FALSE')


def _file_node(parent, path, ref_id, duration, fps=30, media='video', width=None, height=None):
    node = _node(parent, 'file', id=ref_id)
    _node(node, 'name', Path(path).name)
    _node(node, 'pathurl', Path(path).resolve().as_uri())
    _rate(node, fps)
    _node(node, 'duration', duration)
    media_node = _node(node, 'media')
    if media == 'video':
        traits = _node(_node(media_node, 'video'), 'samplecharacteristics')
        _rate(traits, fps)
        if width and height:
            _node(traits, 'width', width)
            _node(traits, 'height', height)
        _node(traits, 'pixelaspectratio', 'square')
    else:
        _node(media_node, 'audio')
    return node


def write_premiere_xml(plan: dict, output: str) -> None:
    timeline = plan['timeline']
    fps = timeline['fps']
    root = ET.Element('xmeml', version='4')
    seq = _node(root, 'sequence', id='sequence-1')
    _node(seq, 'name', 'AVI Auto Edit - Project')
    _node(seq, 'duration', timeline['frames'])
    _rate(seq, fps)
    media = _node(seq, 'media')
    video = _node(media, 'video')
    fmt = _node(video, 'format')
    chars = _node(fmt, 'samplecharacteristics')
    _rate(chars, fps)
    _node(chars, 'width', timeline['width'])
    _node(chars, 'height', timeline['height'])
    _node(chars, 'anamorphic', 'FALSE')
    _node(chars, 'pixelaspectratio', 'square')
    track = _node(video, 'track')
    file_ids = {}
    assets = {a['path']: a for a in plan.get('sources', [])}
    seen_files = set()
    for shot in plan['shots']:
        path = shot['source']
        if path not in file_ids:
            file_ids[path] = f'video-file-{len(file_ids)+1}'
        item = _node(track, 'clipitem', id=f"video-clip-{shot['index']}")
        _node(item, 'name', Path(path).name)
        _node(item, 'enabled', 'TRUE')
        source_meta = assets.get(path, {})
        source_fps = max(1, round(source_meta.get('fps', fps)))
        _rate(item, source_fps)
        _node(item, 'start', shot['start_frame'])
        _node(item, 'end', shot['end_frame'])
        _node(item, 'in', round(shot['source_in'] * source_fps))
        _node(item, 'out', round(shot['source_out'] * source_fps))
        if path not in seen_files:
            duration_frames = max(1, round(source_meta.get('duration', 0) * source_fps))
            _file_node(item, path, file_ids[path], duration_frames, source_fps,
                       width=source_meta.get('width'), height=source_meta.get('height'))
            seen_files.add(path)
        else:
            _node(item, 'file', id=file_ids[path])
        _node(item, 'compositemode', 'normal')
    _node(track, 'enabled', 'TRUE')
    _node(track, 'locked', 'FALSE')
    audio = _node(media, 'audio')
    audio_track = _node(audio, 'track')
    aud = _node(audio_track, 'clipitem', id='narration-clip-1')
    _node(aud, 'name', Path(plan['narration']).name)
    _node(aud, 'enabled', 'TRUE')
    _node(aud, 'start', 0)
    _node(aud, 'end', timeline['frames'])
    _node(aud, 'in', 0)
    _node(aud, 'out', timeline['frames'])
    _file_node(aud, plan['narration'], 'narration-file-1', timeline['frames'], fps, 'audio')
    _node(audio_track, 'enabled', 'TRUE')
    _node(audio_track, 'locked', 'FALSE')
    _node(audio, 'outputchannelindex', 1)
    try:
        ET.indent(root, space='  ')
    except AttributeError:
        pass
    ET.ElementTree(root).write(str(output), encoding='utf-8', xml_declaration=True)


def export_metadata(plan: dict, output_dir: Path) -> None:
    with (output_dir / 'plan.json').open('w', encoding='utf-8') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    with (output_dir / 'shots.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(plan['shots'][0].keys()))
        writer.writeheader()
        writer.writerows(plan['shots'])
    if plan.get('ai_enabled'):
        (output_dir / 'beats.json').write_text(
            json.dumps(plan.get('beats', []), ensure_ascii=False, indent=2), encoding='utf-8')
        match_rows = plan.get('match_report') or []
        if match_rows:
            for filename in ('match_report.csv', 'report.csv'):
                with (output_dir / filename).open('w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(match_rows[0]))
                    writer.writeheader()
                    writer.writerows(match_rows)
    write_premiere_xml(plan, str(output_dir / 'timeline_premiere.xml'))


def render_mp4(plan: dict, output_dir: str, *, stop=None,
               log: Callable[[str], None] = print,
               progress: Callable[[int, int], None] = lambda i, n: None) -> str:
    """Encode silent normalized clips, concat them, then mux narration.

    Audio embedded in the source videos is intentionally discarded.
    """
    output = Path(output_dir)
    width = plan['timeline']['width']
    height = plan['timeline']['height']
    fps = plan['timeline']['fps']
    shots = plan['shots']
    result = output / 'final.mp4'
    if result.exists():
        raise FileExistsError('Đã có final.mp4 trong thư mục đích. Chọn thư mục mới để tránh ghi đè.')
    with tempfile.TemporaryDirectory(prefix='avi_autoedit_', dir=output) as workdir:
        work = Path(workdir)
        concat_lines = []
        for idx, shot in enumerate(shots, start=1):
            if stop is not None and stop.is_set():
                raise InterruptedError('Đã dừng render.')
            segment = work / f'seg_{idx:05d}.mp4'
            seconds = shot['duration_frames'] / fps
            vf = (f'scale={width}:{height}:force_original_aspect_ratio=increase,'
                  f'crop={width}:{height},setsar=1,fps={fps},format=yuv420p')
            # Force exact frame counts; -ss before -i is accurate with FFmpeg default decoding.
            cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                   '-ss', f"{shot['source_in']:.5f}", '-i', shot['source'],
                   '-an', '-vf', vf, '-frames:v', str(shot['duration_frames']),
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
                   '-movflags', '+faststart', str(segment)]
            run_checked(cmd, stop=stop)
            escaped = segment.as_posix().replace("'", "'\\''")
            concat_lines.append(f"file '{escaped}'")
            progress(idx, len(shots))
            if idx == 1 or idx % 10 == 0 or idx == len(shots):
                log(f'  Đã render {idx}/{len(shots)} clip...')
        manifest = work / 'concat.txt'
        manifest.write_text('\n'.join(concat_lines) + '\n', encoding='utf-8')
        temp_result = work / 'mux.mp4'
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'concat', '-safe', '0', '-i', str(manifest),
               '-i', plan['narration'], '-map', '0:v:0', '-map', '1:a:0',
               '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
               '-t', f"{plan['timeline']['duration_seconds']:.5f}",
               '-movflags', '+faststart', str(temp_result)]
        log('  Đang ghép narration và xuất final.mp4...')
        run_checked(cmd, stop=stop)
        os.replace(temp_result, result)
    return str(result)
