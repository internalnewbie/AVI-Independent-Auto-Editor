"""Idempotent Windows installer for the Auto Editor v0.3.4.

Called by CAI_MOT_LAN.bat in the app's existing .venv. Avoid upgrading
already usable packages or switching CUDA Torch to CPU.
"""
from __future__ import annotations

import importlib.metadata as meta
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'logs' / 'install_latest.log'
PYTORCH_CUDA_INDEX = 'https://download.pytorch.org/whl/cu126'
PYTORCH_CPU_INDEX = 'https://download.pytorch.org/whl/cpu'
TORCH_VERSION = '2.9.1'


def log(message):
    print(message, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(str(message) + '\n')


def command(*args, allow_fail=False):
    args = [str(x) for x in args]
    log('\n>>> ' + subprocess.list2cmdline(args))
    p = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, errors='replace')
    for line in p.stdout:
        log(line.rstrip())
    status = p.wait()
    if status and not allow_fail:
        raise RuntimeError(f'Cài đặt thất bại (exit {status}). Xem logs\\install_latest.log')
    return status == 0


def pip(*args, allow_fail=False):
    return command(sys.executable, '-m', 'pip', *args, allow_fail=allow_fail)


def get_version(package):
    try:
        return meta.version(package)
    except meta.PackageNotFoundError:
        return None


def major_minor(ver):
    if not ver:
        return (0, 0)
    import re
    m = re.match(r'^(\d+)\.(\d+)', ver)
    return tuple(int(v) for v in m.groups()) if m else (0, 0)


def requirements_ready():
    """Match requirements-ai.txt; don't invoke pip when no dependency is missing."""
    packages = {
        'faster-whisper': '>=1.0,<2',
        'transformers': '>=4.46,<5',
        'Pillow': '>=10',
        'numpy': '>=1.26',
        'opencv-python': '>=4.8,<5',
        'ctranslate2': '',
        'av': '==18.1.0',
    }
    from packaging.specifiers import SpecifierSet
    missing = []
    for name, spec in packages.items():
        found = get_version(name)
        if not found or (spec and found not in SpecifierSet(spec)):
            missing.append(f'{name}{spec} (current={found or "missing"})')
    return missing


def usable_torch(*, use_cuda):
    """Existing CPU torch is fine for CPU; NVIDIA wants an existing CUDA build."""
    if major_minor(get_version('torch')) < (2, 1):
        return False
    try:
        import torch
    except Exception as exc:
        log('[Torch] Installed, but import failed: ' + str(exc)[:200])
        return False
    if not use_cuda:
        log('[Torch] Existing build OK (CPU available): ' + torch.__version__)
        return True
    if getattr(torch.version, 'cuda', None):
        log('[Torch] Existing CUDA build: ' + str(torch.__version__) +
            '; CUDA available=' + str(torch.cuda.is_available()))
        if not torch.cuda.is_available():
            log('[WARNING] CUDA runtime unavailable; app will fall back to CPU.' )
        return True
    log('[Torch] CPU-only build found on NVIDIA machine; CUDA build is needed.')
    return False


def install_torch(*, use_cuda, installer=pip):
    if usable_torch(use_cuda=use_cuda):
        log('[SKIP] PyTorch already suitable; no reinstall or upgrade.')
        return 'cuda' if use_cuda else 'cpu'
    if use_cuda:
        log('[INSTALL] PyTorch CUDA build (no silent CPU downgrade).')
        success = installer('install', f'torch=={TORCH_VERSION}+cu126',
                            '--index-url', PYTORCH_CUDA_INDEX, allow_fail=True)
        if not success:
            raise RuntimeError('Cài PyTorch CUDA thất bại; KHÔNG tự chuyển sang CPU. '
                               'Xem logs\\install_latest.log')
        return 'cuda'
    log('[INSTALL] PyTorch CPU, only because torch was missing/too old.')
    installer('install', f'torch=={TORCH_VERSION}+cpu',
              '--index-url', PYTORCH_CPU_INDEX)
    return 'cpu'


def main():
    if (sys.version_info[:2] not in ((3, 11), (3, 12))
            or sys.maxsize < 2**32 or platform.system() != 'Windows'):
        raise RuntimeError('Windows x64 và Python 3.11/3.12 là bắt buộc.')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text('=== AI smart installation / reuse ===\n', encoding='utf-8')
    log('Python: ' + sys.executable)
    if sys.executable.lower().endswith('pythonw.exe') or '.venv' not in str(Path(sys.executable)).lower():
        raise RuntimeError('Hãy chạy CAI_MOT_LAN.bat, không chạy qua IDLE.')

    from autoedit.hardware import scan_gpu
    nvidia = scan_gpu()
    log('NVIDIA hardware: ' + str(nvidia))
    cuda_needed = bool(nvidia)

    # pip 22.3 was problematic with typing-extensions metadata; install/update
    # only when necessary, and always fetch dependency tools from regular PyPI.
    if major_minor(get_version('pip')) < (24, 2):
        log('[INSTALL] Old pip: upgrading from official PyPI.')
        pip('install', '--upgrade', 'pip', '--index-url', 'https://pypi.org/simple')
    else:
        log('[SKIP] pip is already recent: ' + str(get_version('pip')))
    if not get_version('packaging') or not get_version('wheel'):
        log('[INSTALL] Missing packaging or wheel.')
        pip('install', 'packaging>=24', 'wheel', '--index-url', 'https://pypi.org/simple')
    else:
        log('[SKIP] wheel + packaging already installed.')
    if not get_version('setuptools'):
        pip('install', 'setuptools', '--index-url', 'https://pypi.org/simple')

    # If all installed, never call pip: avoids huge downloads and unnecessary upgrades.
    torch_ok = usable_torch(use_cuda=cuda_needed)
    missing = requirements_ready()
    if torch_ok and not missing:
        log('[SKIP] All Whisper, CLIP, OpenCV, CTranslate2 + Torch dependencies ready.')
    else:
        if not torch_ok:
            log('[INSTALL] Preparing missing PyTorch prerequisites.')
            pip('install', 'typing_extensions>=4.10', 'packaging', 'flit_core>=3.11,<4',
                'filelock', 'networkx', 'jinja2', 'fsspec', 'sympy>=1.13.3',
                '--index-url', 'https://pypi.org/simple')
            install_torch(use_cuda=cuda_needed)
        if missing:
            log('[INSTALL] Missing/incompatible AI dependencies: ' + '; '.join(missing))
            pip('install', '-r', 'requirements-ai.txt',
                '--index-url', 'https://pypi.org/simple')
        else:
            log('[SKIP] Whisper + CLIP packages already satisfy requirements.')

    command(sys.executable, '-c',
            'import cv2, torch, ctranslate2, faster_whisper, transformers, PIL; '
            'print("AI_IMPORT_OK; PyTorch:", torch.__version__, '
            '"CUDA available:", torch.cuda.is_available())')
    # Regression check for the PyAV/faster-whisper metadata_errors incompatibility.
    # This is an actual decode (short generated silence), not only an import test.
    command(sys.executable, '-c',
            'import tempfile,wave; from pathlib import Path; '
            'from faster_whisper.audio import decode_audio; '
            'p=Path(tempfile.gettempdir())/"avi_install_audio_smoke.wav"; '
            'w=wave.open(str(p),"wb"); w.setnchannels(1); '
            'w.setsampwidth(2); w.setframerate(16000); '
            'w.writeframes(bytes(16000)); w.close(); '
            'a=decode_audio(str(p),sampling_rate=16000); '
            'p.unlink(missing_ok=True); '
            'assert len(a)==8000, len(a); print("AUDIO_DECODE_OK")')
    log('[SUCCESS] Python AI dependencies ready.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        log('INSTALL ERROR: ' + str(error))
        raise SystemExit(1)
