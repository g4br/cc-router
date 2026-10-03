"""Start the official Laya server on a GPU that works, or on CPU."""

import os
import sys

from laya_device import detect_device


device = detect_device()
environment = os.environ.copy()
environment.update({
    'LAYA_DEVICE': device,
    'LAYA_HOST': environment.get('LAYA_HOST', '127.0.0.1'),
    'LAYA_MODELS': environment.get('LAYA_MODELS', 'english'),
})
print(f'Laya device: {device}', flush=True)
os.execve(sys.executable, [sys.executable, '-m', 'laya.serve'], environment)
