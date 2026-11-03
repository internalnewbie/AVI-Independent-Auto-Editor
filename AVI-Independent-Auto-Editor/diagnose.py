import sys
import shutil
from pathlib import Path
print('=== AVI AUTO EDITOR v0.3 - DIAGNOSE ===')
print('Python:', sys.executable)
try:
    from autoedit.media import require_ffmpeg
    require_ffmpeg()
except Exception as exc:
    print('FFmpeg configuration:', exc)
print('FFmpeg:', shutil.which('ffmpeg') or '(not found)')
print('FFprobe:', shutil.which('ffprobe') or '(not found)')
for name in ('torch', 'faster_whisper', 'ctranslate2', 'transformers', 'cv2', 'PIL'):
    try:
        mod = __import__(name)
        print(name, 'OK', getattr(mod, '__version__', ''))
        if name == 'torch':
            print('PyTorch CUDA available:', mod.cuda.is_available())
            if mod.cuda.is_available():
                print('GPU:', mod.cuda.get_device_name(0))
    except Exception as exc:
        print(name, 'MISSING/ERROR:', str(exc)[:250])
try:
    from autoedit.qwen_engine import check_ollama
    print('Ollama model:', check_ollama())
except Exception as exc:
    print('Ollama Qwen unavailable:', str(exc)[:250])
print('Finished. For errors see logs/install_latest.log')
