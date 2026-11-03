"""AVI Independent Auto Editor v0.3.4, one-click setup orchestrator.

Run only from CAI_MOT_LAN.bat inside the application's own .venv.
No system-wide pip, no API keys, no upload of user footage.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'logs' / 'setup_all_latest.log'
MODEL = 'qwen3-vl:4b-instruct'
BASE_URL = 'http://127.0.0.1:11434'


def out(message):
    print(message, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(str(message) + '\n')


def run(args, *, required=True, timeout=None, env=None):
    args = [str(s) for s in args]
    out('\n>>> ' + subprocess.list2cmdline(args))
    try:
        p = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding='utf-8', errors='replace', env=env)
        for line in p.stdout:
            out(line.rstrip())
        code = p.wait(timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        if required:
            raise RuntimeError(f'Unable to execute {args[0]}: {exc}') from exc
        out(f'[WARNING] Command unavailable: {exc}')
        return False
    if code and required:
        raise RuntimeError(f'{args[0]} returned code {code}. See logs\\setup_all_latest.log')
    return code == 0


def lookup_ollama():
    paths = [shutil.which('ollama')]
    for var, rel in [('LOCALAPPDATA', 'Programs/Ollama/ollama.exe'),
                     ('ProgramFiles', 'Ollama/ollama.exe')]:
        if os.environ.get(var):
            paths.append(str(Path(os.environ[var]) / rel))
    for path in paths:
        if path and Path(path).is_file():
            return str(Path(path))
    return None


def winget_install(package):
    binary = shutil.which('winget')
    if not binary:
        out(f'[WARNING] winget unavailable: cannot auto-install {package}.')
        return False
    return run([binary, 'install', '--exact', '--id', package, '--source', 'winget',
                '--silent', '--accept-package-agreements', '--accept-source-agreements'],
               required=False)


def ffmpeg_bin():
    # Existing portable ffmpeg is preferred, followed by PATH and WinGet locations.
    folders = [ROOT / rel for rel in ('tools', 'bin', 'ffmpeg/bin')]
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        folders.append(Path(ffmpeg).parent)
    localapp = os.environ.get('LOCALAPPDATA')
    if localapp:
        localapp = Path(localapp)
        folders.extend([localapp / 'Microsoft/WinGet/Links',
                        localapp / 'Microsoft/WinGet/Packages'])
        pkgroot = localapp / 'Microsoft/WinGet/Packages'
        if pkgroot.exists():
            for item in pkgroot.glob('Gyan.FFmpeg*'):
                # Search in Gyan package only, not in arbitrary user directories.
                folders.extend(p.parent for p in item.glob('**/bin/ffmpeg.exe'))
    for folder in folders:
        if (folder / 'ffmpeg.exe').is_file() and (folder / 'ffprobe.exe').is_file():
            return folder.resolve()
    # WinGet Links are sometimes symlinked after the Python process started.
    return None


def install_ffmpeg():
    out('\n[2/5] FFmpeg / FFprobe')
    folder = ffmpeg_bin()
    if folder is None:
        out('[FFmpeg] Not found, installing through winget...')
        if not winget_install('Gyan.FFmpeg'):
            raise RuntimeError('FFmpeg absent and winget install failed. Install Gyan.FFmpeg (or copy ffmpeg.exe + ffprobe.exe into tools) then rerun.')
        folder = ffmpeg_bin()
    if folder is None:
        raise RuntimeError('FFmpeg install was attempted but bin folder was not found. Reopen CMD and rerun, or copy both EXEs into tools.')
    (ROOT / '.ffmpeg_path.txt').write_text(str(folder), encoding='utf-8')
    os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
    out(f'[FFmpeg] OK: {folder}')


def _ollama_http(path, timeout=5):
    req = urllib.request.Request(BASE_URL + path)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def ollama_alive():
    try:
        return isinstance(_ollama_http('/api/tags'), dict)
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _download_official_ollama_installer():
    """Fallback to official signed Windows installer, never run unverified exe."""
    path = ROOT / 'logs' / 'OllamaSetup.exe'
    url = 'https://ollama.com/download/OllamaSetup.exe'
    out('[Ollama] Downloading official signed Windows installer...')
    urllib.request.urlretrieve(url, path)
    ps = shutil.which('powershell.exe') or 'powershell.exe'
    quoted = str(path).replace("'", "''")
    script = ("$s=Get-AuthenticodeSignature -LiteralPath '" + quoted + "'; "
              "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch '(^|, )O=Ollama Inc\\.(,|$)'){exit 1}")
    if not run([ps, '-NoProfile', '-Command', script], required=False):
        raise RuntimeError('Ollama installer signature not verified. Refusing to execute downloaded EXE.')
    out('[Ollama] Authenticode signature verified; silent install starting.')
    run([str(path), '/VERYSILENT', '/NORESTART', '/SUPPRESSMSGBOXES'])
    try:
        path.unlink()
    except OSError:
        pass


def install_ollama():
    out('\n[3/5] Ollama')
    found = lookup_ollama()
    if found is None:
        out('[Ollama] Not installed, installing automatically...')
        if not winget_install('Ollama.Ollama'):
            _download_official_ollama_installer()
        found = lookup_ollama()
    if found is None:
        raise RuntimeError('Ollama install returned but ollama.exe is not found. Restart CMD and rerun CAI_MOT_LAN.bat.')
    out('[Ollama] Executable: ' + found)
    if ollama_alive():
        out('[Ollama] API already running.')
        return found
    out('[Ollama] Starting local model service...')
    service_log = ROOT / 'logs' / 'ollama_service.log'
    stream = service_log.open('a', encoding='utf-8')
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = (getattr(subprocess, 'DETACHED_PROCESS', 0)
                                   | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                                   | getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    subprocess.Popen([found, 'serve'], cwd=ROOT, stdin=subprocess.DEVNULL,
                     stdout=stream, stderr=subprocess.STDOUT, **kwargs)
    stream.close()
    for _ in range(30):
        if ollama_alive():
            out('[Ollama] Local service listening on ' + BASE_URL)
            return found
        time.sleep(1)
    raise RuntimeError('Ollama executable exists but API on localhost:11434 is unavailable. Check logs\\ollama_service.log.')


def model_downloaded(name=MODEL):
    try:
        data = _ollama_http('/api/tags')
    except (urllib.error.URLError, ValueError, OSError):
        return False
    return any(x.get('name') == name for x in data.get('models', []))


def install_qwen(executable):
    out('\n[4/5] Qwen vision model')
    if model_downloaded():
        out('[Qwen] Model already downloaded: ' + MODEL)
        return
    out('[Qwen] Pulling ' + MODEL + '. This downloads multiple GB only once.')
    run([executable, 'pull', MODEL])
    if not model_downloaded():
        raise RuntimeError('Ollama pull completed but Qwen is not shown by /api/tags.')
    out('[Qwen] OK')


def prefetch_models():
    out('\n[5/5] Offline Whisper + CLIP model preparation')
    # Prefetch only, no inference or model-to-GPU launch during installation.
    from huggingface_hub import snapshot_download
    for model in ('Systran/faster-whisper-small', 'openai/clip-vit-base-patch32'):
        try:
            snapshot_download(repo_id=model, local_files_only=True)
            out('[SKIP] Model already cached: ' + model)
            continue
        except Exception:
            out('[INSTALL] Missing model files; downloading ' + model)
        snapshot_download(repo_id=model)
    out('[Model] Whisper small and CLIP weights available.')


def install_python_ai():
    out('\n[1/5] Python requirements + CUDA/CPU')
    # Use the existing project installer, always in exactly the same .venv.
    run([sys.executable, 'install_auto.py'])
    import torch
    import faster_whisper
    import ctranslate2
    import cv2
    import transformers
    import PIL
    out(f'[AI] torch={torch.__version__}; CUDA={torch.cuda.is_available()}; '
        f'faster-whisper/ctranslate2/CLIP dependencies imported OK.')


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text('=== AVI AUTO EDITOR v0.3.4 ONE-CLICK SETUP ===\n', encoding='utf-8')
    out('[INFO] Python executable: ' + sys.executable)
    out('[INFO] Existing packages/models will be checked and reused when compatible.')
    if (sys.platform != 'win32' or '.venv' not in str(Path(sys.executable)).lower()
            or sys.version_info[:2] not in ((3, 11), (3, 12))):
        raise RuntimeError('Run CAI_MOT_LAN.bat on Windows with a Python 3.11/3.12 .venv.')
    install_python_ai()
    install_ffmpeg()
    ollama = install_ollama()
    install_qwen(ollama)
    prefetch_models()
    out('\n[SUCCESS] Python, CUDA/CPU, Whisper, CLIP, FFmpeg, Ollama, and Qwen ready.')
    out('Launch CHAY_AUTO_EDIT.bat and test 10 footage clips first.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        out('\n[ERROR] ' + repr(exc))
        out('[ERROR] After correcting the issue, rerun CAI_MOT_LAN.bat. Already installed components are reused.')
        raise SystemExit(1)
