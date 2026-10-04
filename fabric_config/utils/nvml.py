"""
A minimal ctypes binding to NVIDIA's NVML, for GPU temperature, load and memory.

Reading NVML in-process costs microseconds; running `nvidia-smi` costs a whole
process (and a driver init) each time. On NixOS the library lives in
/run/opengl-driver/lib, which isn't on the default search path.
"""

import ctypes
from dataclasses import dataclass

from loguru import logger

_PATHS = ("/run/opengl-driver/lib/libnvidia-ml.so.1", "libnvidia-ml.so.1")
_TEMPERATURE_GPU = 0


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Memory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


@dataclass
class GpuSample:
    name: str
    temperature: int
    load: int  # percent
    memory_used: int  # bytes
    memory_total: int


class Nvml:
    def __init__(self):
        self._lib: ctypes.CDLL | None = None
        self._handle = ctypes.c_void_p()
        self.name = "GPU"
        for path in _PATHS:
            try:
                lib = ctypes.CDLL(path)
            except OSError:
                continue
            if lib.nvmlInit_v2() != 0:
                continue
            if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._handle)) != 0:
                continue
            buffer = ctypes.create_string_buffer(96)
            if lib.nvmlDeviceGetName(self._handle, buffer, 96) == 0:
                self.name = buffer.value.decode(errors="replace").removeprefix(
                    "NVIDIA "
                )
            self._lib = lib
            logger.info(f"[NVML] Reading {self.name}")
            return

    @property
    def available(self) -> bool:
        return self._lib is not None

    def sample(self) -> GpuSample | None:
        lib = self._lib
        if lib is None:
            return None
        temperature = ctypes.c_uint()
        utilization = _Utilization()
        memory = _Memory()
        if (
            lib.nvmlDeviceGetTemperature(
                self._handle, _TEMPERATURE_GPU, ctypes.byref(temperature)
            )
            or lib.nvmlDeviceGetUtilizationRates(
                self._handle, ctypes.byref(utilization)
            )
            or lib.nvmlDeviceGetMemoryInfo(self._handle, ctypes.byref(memory))
        ):
            return None
        return GpuSample(
            self.name,
            temperature.value,
            utilization.gpu,
            memory.used,
            memory.total,
        )
