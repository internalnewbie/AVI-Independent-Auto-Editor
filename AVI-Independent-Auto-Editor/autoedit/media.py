"""Probe media and identify useful footage segments."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.mts', '.m2ts'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg'}


@dataclass
class VideoAsset:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


@dataclass
class Candidate:
    path: str
    start: float
    end: float
    motion: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return asdict(self)


def require_ffmpeg() -> None:
    # Accept portable ffmpeg.exe/ffprobe.exe alongside the application.
    project_root = Path(__file__).resolve().parents[1]
    configured = project_root / '.ffmpeg_path.txt'
    if configured.is_file():
        directory = Path(configured.read_text(encoding='utf-8').strip())
        if (directory / 'ffmpeg.exe').is_file() and (directory / 'ffprobe.exe').is_file():
            os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
    for folder in ('tools', 'bin', 'ffmpeg/bin'):
        local = project_root / folder
        suffix = '.exe' if os.name == 'nt' else ''
        if all((local / (name + suffix)).is_file() for name in ('ffmpeg', 'ffprobe')):
            os.environ['PATH'] = str(local) + os.pathsep + os.environ.get('PATH', '')
            break
    missing = [name for name in ('ffmpeg', 'ffprobe') if not shutil.which(name)]
    if missing:
        raise RuntimeError('Không tìm thấy ' + ', '.join(missing) +
                           '. Hãy cài FFmpeg và thêm thư mục bin vào PATH.')


def run_checked(command: list[str], stop=None, stderr: bool = False) -> str:
    """Run a subprocess with cancel support; never pass untrusted input via shell."""
    import threading
    if stop is not None and stop.is_set():
        raise InterruptedError('Người dùng đã dừng tác vụ.')
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            encoding='utf-8', errors='replace', creationflags=(0x08000000 if os.name == 'nt' else 0))
    # communicate() drains both pipes and handles long stderr safely.
    holder = {}
    def read():
        holder['out'], holder['err'] = proc.communicate()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    while reader.is_alive():
        reader.join(0.15)
        if stop is not None and stop.is_set():
            proc.kill()
            reader.join()
            raise InterruptedError('Đã dừng và hủy tiến trình FFmpeg.')
    if proc.returncode:
        msg = holder.get('err', '')[-2500:] or holder.get('out', '')[-2500:]
        raise RuntimeError(f'Lệnh xử lý media thất bại (mã {proc.returncode}):\n{msg}')
    return holder.get('err', '') if stderr else holder.get('out', '')


def probe(path: str, stop=None) -> dict:
    raw = run_checked(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                       '-of', 'json', str(path)], stop=stop)
    return json.loads(raw)


def media_duration(path: str, stop=None) -> float:
    data = probe(path, stop=stop)
    duration = float(data.get('format', {}).get('duration') or 0)
    if duration <= 0:
        duration = max((float(s.get('duration') or 0) for s in data.get('streams', [])), default=0)
    if duration <= 0:
        raise ValueError(f'Không đọc được thời lượng: {path}')
    return duration


def inspect_video(path: str, stop=None) -> VideoAsset:
    data = probe(path, stop=stop)
    stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not stream:
        raise ValueError(f'File không có video: {path}')
    rate = stream.get('avg_frame_rate', '30/1')
    try:
        numerator, denominator = rate.split('/')
        fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError, AttributeError):
        fps = 30
    duration = float(data.get('format', {}).get('duration') or stream.get('duration') or 0)
    if duration <= 0:
        raise ValueError(f'Không xác định được duration video: {path}')
    return VideoAsset(str(Path(path).resolve()), duration, int(stream.get('width') or 0),
                      int(stream.get('height') or 0), fps or 30,
                      any(s.get('codec_type') == 'audio' for s in data.get('streams', [])))


def list_videos(folder: str) -> list[str]:
    root = Path(folder).resolve()
    if not root.is_dir():
        raise FileNotFoundError('Thư mục video không tồn tại: ' + str(root))
    return sorted((str(p) for p in root.rglob('*') if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS),
                  key=str.casefold)


def detect_candidates(asset: VideoAsset, *, threshold: float = .42,
                      step: float = .75, max_scene: float = 12.0,
                      stop=None, log: Callable[[str], None] = print) -> list[Candidate]:
    """Lightweight sampled scene detection using frame histogram differences.

    If OpenCV is absent or decoding fails, return regular windows instead.
    All in/out points are in original source media seconds.
    """
    duration = asset.duration
    cuts = [0.0]
    motion_window = []
    try:
        import cv2
        cap = cv2.VideoCapture(asset.path)
        if not cap.isOpened():
            raise RuntimeError('OpenCV không đọc được video')
        try:
            count = max(2, math.ceil(duration / step))
            # Limit thumbnail decoding work for very long (>~25 min) sources.
            effective_step = max(step, duration / 1800)
            previous = None
            last_cut = 0.0
            for j in range(math.ceil(duration / effective_step)):
                if stop is not None and stop.is_set():
                    raise InterruptedError('Đã dừng phân tích video.')
                pos = j * effective_step
                cap.set(cv2.CAP_PROP_POS_MSEC, pos * 1000)
                ok, frame = cap.read()
                if not ok:
                    continue
                # Low resolution analysis, separate from final render.
                tiny = cv2.resize(frame, (160, 90))
                hsv = cv2.cvtColor(tiny, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
                cv2.normalize(hist, hist)
                gray = cv2.cvtColor(tiny, cv2.COLOR_BGR2GRAY)
                if previous is not None:
                    old_hist, old_gray = previous
                    difference = float(cv2.compareHist(hist, old_hist, cv2.HISTCMP_BHATTACHARYYA))
                    motion_window.append((pos, float(cv2.absdiff(gray, old_gray).mean()) / 255.0))
                    if difference >= threshold and pos-last_cut >= 1.0 and duration-pos >= 0.5:
                        cuts.append(round(pos, 3))
                        last_cut = pos
                previous = hist, gray
        finally:
            cap.release()
    except InterruptedError:
        raise
    except Exception as e:
        log(f'  Phát hiện cảnh đơn giản (không dùng OpenCV): {e}')
    cuts.append(duration)
    candidates = []
    for start, end in zip(cuts, cuts[1:]):
        # Partition lengthy scenes so the planner can visit many positions.
        chunks = max(1, math.ceil((end - start) / max_scene))
        for k in range(chunks):
            a = start + (end - start) * k / chunks
            b = start + (end - start) * (k+1) / chunks
            if b - a < .6:
                continue
            measured = [val for sec, val in motion_window if a <= sec < b]
            motion = sum(measured) / len(measured) if measured else 0.2
            candidates.append(Candidate(asset.path, round(a, 3), round(b, 3), round(motion, 4)))
    return candidates or [Candidate(asset.path, 0.0, duration, 0.2)]


def detect_voice_pauses(path: str, stop=None) -> list[float]:
    """Find approximate between-phrase pause centers using FFmpeg silencedetect.

    Speech recognition is NOT used. This only detects low-volume intervals.
    """
    command = ['ffmpeg', '-hide_banner', '-nostats', '-i', str(path),
               '-af', 'silencedetect=noise=-35dB:d=0.25', '-f', 'null', '-']
    output = run_checked(command, stop=stop, stderr=True)
    starts = []
    pauses = []
    for line in output.splitlines():
        start = re.search(r'silence_start:\s*([\d.]+)', line)
        end = re.search(r'silence_end:\s*([\d.]+)', line)
        if start:
            starts.append(float(start.group(1)))
        if end and starts:
            first = starts.pop(0)
            last = float(end.group(1))
            if last > first:
                pauses.append(round((first + last)/2, 3))
    return pauses
