"""Platform diagnostics and optional CUDA DLL-path setup (never executes external models)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_DLL_HANDLES = []  # Windows must retain handles returned by os.add_dll_directory.


def _smi_binary():
    found = shutil.which('nvidia-smi')
    if found:
        return found
    if sys.platform == 'win32':
        for candidate in (r'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe',
                          r'C:\Windows\System32\nvidia-smi.exe'):
            if Path(candidate).is_file():
                return candidate
    return None


def scan_gpu():
    """Read NVIDIA GPU name/VRAM/driver via nvidia-smi, if available."""
    exe = _smi_binary()
    if not exe:
        return []
    try:
        proc = subprocess.run([exe, '--query-gpu=name,memory.total,driver_version',
                              '--format=csv,noheader,nounits'], capture_output=True,
                              text=True, timeout=8, check=True)
    except (OSError, subprocess.SubprocessError):
        return []
    results = []
    for row in proc.stdout.splitlines():
        parts = [p.strip() for p in row.split(',')]
        if len(parts) >= 3:
            results.append({'name': parts[0], 'vram_mb': parts[1], 'driver': parts[2]})
    return results


def configure_cuda_dll_paths():
    """Expose NVIDIA pip wheel DLL folders to CTranslate2 on Windows.

    Does not download libraries or alter global Windows environment variables.
    """
    if os.name != 'nt':
        return []
    from importlib.util import find_spec
    from site import getsitepackages, getusersitepackages
    roots = [Path(v) for v in getsitepackages()] + [Path(getusersitepackages())]
    folders = []
    for root in roots:
        nvidia = root / 'nvidia'
        if not nvidia.is_dir():
            continue
        # Prefer wheels installed into this program's own Python environment.
        for current, _dirs, names in os.walk(nvidia):
            if any(n.lower().endswith('.dll') for n in names):
                folders.append(str(Path(current)))
    # Existing PyTorch CUDA wheels may also provide the dependencies.
    try:
        spec = find_spec('torch')
        if spec and spec.submodule_search_locations:
            lib = Path(next(iter(spec.submodule_search_locations))) / 'lib'
            if lib.is_dir():
                folders.append(str(lib))
    except (ImportError, AttributeError, ValueError):
        pass
    registered = []
    for folder in dict.fromkeys(folders):
        if folder not in os.environ.get('PATH', '').split(os.pathsep):
            os.environ['PATH'] = folder + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            try:
                _DLL_HANDLES.append(os.add_dll_directory(folder))
                registered.append(folder)
            except OSError:
                pass
    return registered


def probe_cuda():
    """Check real backend readiness, not just whether an NVIDIA card exists."""
    configure_cuda_dll_paths()
    result = {'os': platform.platform(), 'python': platform.python_version(),
              'gpus': scan_gpu(), 'torch_cuda': False, 'whisper_cuda': False,
              'torch_version': None, 'torch_cuda_version': None, 'notes': []}
    try:
        import torch
        result['torch_version'] = torch.__version__
        result['torch_cuda_version'] = torch.version.cuda
        if torch.cuda.is_available():
            # Allocate a real tensor to catch missing drivers/runtime/unsupported devices.
            x = torch.ones(1, device='cuda')
            result['torch_cuda'] = bool((x + 1).item() == 2)
            del x
        if not result['torch_cuda']:
            result['notes'].append('PyTorch CUDA khong san sang; CLIP se chay CPU.')
    except (ImportError, OSError, RuntimeError, AssertionError) as exc:
        result['notes'].append('Torch CUDA: ' + str(exc)[:240])
    try:
        import ctranslate2
        types = ctranslate2.get_supported_compute_types('cuda')
        result['whisper_cuda'] = bool(types)
        if not types:
            result['notes'].append('CTranslate2 khong co CUDA; Whisper se chay CPU.')
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        result['notes'].append('CTranslate2 CUDA: ' + str(exc)[:240])
    return result


def describe_hardware(result):
    cards = ', '.join(f"{x['name']} ({x['vram_mb']} MiB)" for x in result['gpus']) or 'Khong xac dinh qua nvidia-smi'
    return (f"GPU: {cards} | PyTorch/CLIP: {'CUDA' if result['torch_cuda'] else 'CPU'} | "
            f"CTranslate2/Whisper: {'CUDA' if result['whisper_cuda'] else 'CPU'}")


def select_device(preference: str, *, backend: str, capabilities: dict):
    """Per-backend selection: CUDA when usable, CPU otherwise in auto mode."""
    if preference not in ('auto', 'cpu', 'cuda'):
        raise ValueError('Device phai la auto/cpu/cuda')
    if backend not in ('clip', 'whisper'):
        raise ValueError('Backend phai la clip hoac whisper')
    if preference == 'cpu':
        return 'cpu'
    available = capabilities['torch_cuda'] if backend == 'clip' else capabilities['whisper_cuda']
    if preference == 'cuda' and not available:
        raise RuntimeError(f'{backend}: che do CUDA bat buoc nhung backend chua san sang. Chon AUTO de fallback CPU.')
    return 'cuda' if available else 'cpu'
