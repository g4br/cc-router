"""Choose a working Laya device without leaving a failed CUDA context behind."""

import subprocess
import sys
from pathlib import Path


def probe_device(torch):
    candidates = []
    if torch.cuda.is_available():
        candidates.extend(f'cuda:{index}' for index in range(torch.cuda.device_count()))
    if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        candidates.append('mps')
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        candidates.extend(f'xpu:{index}' for index in range(torch.xpu.device_count()))

    for device in candidates:
        try:
            value = (torch.ones(1, device=device) + 1).cpu().item()
            if value == 2:
                return device
        except Exception:
            continue
    return 'cpu'


def detect_device():
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), '--probe'],
            capture_output=True, text=True, check=True, timeout=20,
        )
        device = result.stdout.strip()
        if device == 'cpu' or device == 'mps' or device.startswith(('cuda:', 'xpu:')):
            return device
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return 'cpu'


if __name__ == '__main__':
    import torch
    print(probe_device(torch))
