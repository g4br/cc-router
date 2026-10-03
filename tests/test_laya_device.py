import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.laya_device import detect_device, probe_device


class Tensor:
    def __add__(self, other):
        return self

    def cpu(self):
        return self

    def item(self):
        return 2


class LayaDeviceTest(unittest.TestCase):
    def test_usable_gpu_is_selected_and_failed_kernel_falls_back_to_cpu(self):
        torch = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1),
            backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
            xpu=SimpleNamespace(is_available=lambda: False),
            ones=lambda *_args, **_kwargs: Tensor(),
        )
        self.assertEqual(probe_device(torch), 'cuda:0')
        torch.ones = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('no kernel image'))
        self.assertEqual(probe_device(torch), 'cpu')

    def test_subprocess_result_is_used_for_gpu_selection(self):
        with patch('scripts.laya_device.subprocess.run') as run:
            run.return_value.stdout = 'cuda:0\n'
            self.assertEqual(detect_device(), 'cuda:0')


if __name__ == '__main__':
    unittest.main()
