"""Send RGB frames to the official DroidCam Video driver on Windows.

Interoperability protocol: dev47apps/droidcam-obs-virtual-output, src/structs.h.
The consumer owns the header; the producer only writes the YUY2 pixel payload.
"""
import ctypes
import mmap
import struct
import time


def consumer_size(header):
    _, control, checksum, width, height, interval, _ = struct.unpack('<7i', header)
    if (control != 0x02020101 or checksum != (width ^ height ^ interval)
            or not 0 < width <= 3860 or width % 2 or not 0 < height <= 2160
            or interval <= 0):
        return None
    return width, height


def yuy2(frame, width, height):
    import cv2
    import numpy as np
    sh, sw = frame.shape[:2]
    if (sw, sh) != (width, height):
        scale = min(width / sw, height / sh)
        dw, dh = max(2, int(sw * scale) // 2 * 2), max(1, int(sh * scale))
        canvas = np.zeros((height, width, 3), dtype=np.uint8)
        x, y = (width - dw) // 2, (height - dh) // 2
        canvas[y:y + dh, x:x + dw] = cv2.resize(frame, (dw, dh))
        frame = canvas
    return cv2.cvtColor(frame, cv2.COLOR_RGB2YUV_YUY2).tobytes()



class DroidCamCamera:
    def __init__(self, fps=24):
        self.memory = mmap.mmap(-1, 1024 + 3860 * 2160 * 3, tagname='DroidCamOBS_VideoOut1')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateEventW.restype = ctypes.c_void_p
        for method in ('SetEvent', 'ResetEvent', 'CloseHandle'):
            getattr(self.kernel, method).argtypes = [ctypes.c_void_p]
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.writer = self.kernel.CreateEventW(None, True, True, 'DroidCamOBS_VideoWr1')
        self.reader = self.kernel.CreateEventW(None, True, True, 'DroidCamOBS_VideoRd1')
        if not self.writer or not self.reader:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self.period, self.deadline = 1 / fps, time.monotonic()
        self.consumer_active = False

    def send(self, frame):
        size = consumer_size(self.memory[:28])
        self.consumer_active = size is not None
        if size is None:
            return
        pixels = yuy2(frame, *size)
        self.kernel.ResetEvent(self.writer)
        try:
            if self.kernel.WaitForSingleObject(self.reader, 5) == 0:
                # The consumer may renegotiate while conversion is running.
                if consumer_size(self.memory[:28]) == size:
                    self.memory[1024:1024 + len(pixels)] = pixels
        finally:
            self.kernel.SetEvent(self.writer)

    def sleep_until_next_frame(self):
        self.deadline += self.period
        delay = self.deadline - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        else:
            self.deadline = time.monotonic()

    def close(self):
        self.memory.close()
        for handle in (self.writer, self.reader):
            if handle:
                self.kernel.CloseHandle(handle)
