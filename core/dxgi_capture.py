"""DXGI Desktop Duplication 截屏 - 纯 ctypes 调用 Windows 原生 API"""
import ctypes
import time
from ctypes import (
    c_void_p, c_uint, c_int, c_long, c_ulong, c_byte,
    c_uint32, c_int32, c_uint16, c_longlong,
    POINTER, byref, Structure, HRESULT, WINFUNCTYPE,
)
import numpy as np


S_OK = 0
DXGI_ERROR_WAIT_TIMEOUT = ctypes.c_int32(0x887A0027).value
DXGI_ERROR_ACCESS_LOST = ctypes.c_int32(0x887A0026).value
DXGI_ERROR_NOT_CURRENTLY_AVAILABLE = ctypes.c_int32(0x887A0022).value

DXGI_FORMAT_B8G8R8A8_UNORM = 87
D3D_DRIVER_TYPE_HARDWARE = 1
D3D11_SDK_VERSION = 7
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1


class GUID(Structure):
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", c_uint16),
        ("Data3", c_uint16),
        ("Data4", c_byte * 8),
    ]


def _g(d1, d2, d3, *d4):
    g = GUID()
    g.Data1 = d1
    g.Data2 = d2
    g.Data3 = d3
    for i, b in enumerate(d4):
        g.Data4[i] = ctypes.c_byte(b).value
    return g


IID_IDXGIDevice = _g(0x54ec77fa, 0x1377, 0x44e6,
                     0x8c, 0x32, 0x88, 0xfd, 0x5f, 0x44, 0xc8, 0x4c)
IID_IDXGIOutput1 = _g(0x00cddea8, 0x939b, 0x4b83,
                      0xa3, 0x40, 0xa6, 0x85, 0x22, 0x66, 0x66, 0xcc)
IID_ID3D11Texture2D = _g(0x6f15aaf2, 0xd208, 0x4e89,
                         0x9a, 0xb4, 0x48, 0x95, 0x35, 0xd3, 0x4f, 0x9c)


class LUID(Structure):
    _fields_ = [("LowPart", c_uint32), ("HighPart", c_int32)]


class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long),
                ("right", c_long), ("bottom", c_long)]


class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]


class DXGI_OUTPUT_DESC(Structure):
    _fields_ = [
        ("DeviceName", ctypes.c_wchar * 32),
        ("DesktopCoordinates", RECT),
        ("AttachedToDesktop", c_int),
        ("Rotation", c_uint),
        ("Monitor", c_void_p),
    ]


class DXGI_OUTDUPL_POINTER_POSITION(Structure):
    _fields_ = [("Position", POINT), ("Visible", c_int)]


class DXGI_OUTDUPL_FRAME_INFO(Structure):
    _fields_ = [
        ("LastPresentTime", c_longlong),
        ("LastMouseUpdateTime", c_longlong),
        ("AccumulatedFrames", c_uint),
        ("RectsCoalesced", c_int),
        ("ProtectedContentMaskedOut", c_int),
        ("PointerPosition", DXGI_OUTDUPL_POINTER_POSITION),
        ("TotalMetadataBufferSize", c_uint),
        ("PointerShapeBufferSize", c_uint),
    ]


class D3D11_BOX(Structure):
    _fields_ = [
        ("left", c_uint), ("top", c_uint), ("front", c_uint),
        ("right", c_uint), ("bottom", c_uint), ("back", c_uint),
    ]


class D3D11_TEXTURE2D_DESC(Structure):
    _fields_ = [
        ("Width", c_uint),
        ("Height", c_uint),
        ("MipLevels", c_uint),
        ("ArraySize", c_uint),
        ("Format", c_uint),
        ("SampleDesc_Count", c_uint),
        ("SampleDesc_Quality", c_uint),
        ("Usage", c_uint),
        ("BindFlags", c_uint),
        ("CPUAccessFlags", c_uint),
        ("MiscFlags", c_uint),
    ]


class D3D11_MAPPED_SUBRESOURCE(Structure):
    _fields_ = [
        ("pData", c_void_p),
        ("RowPitch", c_uint),
        ("DepthPitch", c_uint),
    ]


def _vcall(this, idx, restype, *argtypes):
    vtbl = ctypes.cast(this, POINTER(POINTER(c_void_p)))[0]
    return WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[idx])


def _release(p):
    if p:
        _vcall(p, 2, c_ulong)(p)


def _qi(this, iid):
    out = c_void_p()
    hr = _vcall(this, 0, HRESULT, POINTER(GUID), POINTER(c_void_p))(
        this, byref(iid), byref(out)
    )
    if hr != S_OK:
        raise OSError(f"QueryInterface failed: 0x{hr & 0xFFFFFFFF:08X}")
    return out.value


_d3d11 = ctypes.windll.d3d11
D3D11CreateDevice = _d3d11.D3D11CreateDevice
D3D11CreateDevice.restype = HRESULT
D3D11CreateDevice.argtypes = [
    c_void_p, c_uint, c_void_p, c_uint,
    POINTER(c_uint), c_uint, c_uint,
    POINTER(c_void_p), POINTER(c_uint), POINTER(c_void_p),
]


class DXGICapture:
    """region: (left, top, width, height) in primary-output desktop coordinates."""

    def __init__(self, region):
        self._region = region
        self._device = None
        self._ctx = None
        self._dup = None
        self._staging = None
        self._desktop_w = 0
        self._desktop_h = 0
        self._cap_x = 0
        self._cap_y = 0
        self._cap_w = 0
        self._cap_h = 0
        # 缓存每帧调用的 COM 函数指针
        self._fn_acquire = None
        self._fn_release_frame = None
        self._fn_copy = None
        self._fn_map = None
        self._fn_unmap = None
        # 复用的输出结构体与常量入参
        self._frame_info = DXGI_OUTDUPL_FRAME_INFO()
        self._mapped = D3D11_MAPPED_SUBRESOURCE()
        self._res_ptr = c_void_p()
        self._box = D3D11_BOX()
        self._init()

    def _init(self):
        device = c_void_p()
        ctx = c_void_p()
        hr = D3D11CreateDevice(
            None, D3D_DRIVER_TYPE_HARDWARE, None, 0,
            None, 0, D3D11_SDK_VERSION,
            byref(device), None, byref(ctx),
        )
        if hr != S_OK:
            raise OSError(f"D3D11CreateDevice failed: 0x{hr & 0xFFFFFFFF:08X}")
        self._device = device.value
        self._ctx = ctx.value

        dxgi_dev = _qi(self._device, IID_IDXGIDevice)
        try:
            adapter = c_void_p()
            hr = _vcall(dxgi_dev, 7, HRESULT, POINTER(c_void_p))(
                dxgi_dev, byref(adapter)
            )
            if hr != S_OK:
                raise OSError(f"GetAdapter failed: 0x{hr & 0xFFFFFFFF:08X}")
            try:
                output = c_void_p()
                hr = _vcall(adapter.value, 7, HRESULT, c_uint, POINTER(c_void_p))(
                    adapter.value, 0, byref(output)
                )
                if hr != S_OK:
                    raise OSError(f"EnumOutputs failed: 0x{hr & 0xFFFFFFFF:08X}")
                try:
                    desc = DXGI_OUTPUT_DESC()
                    hr = _vcall(output.value, 7, HRESULT, POINTER(DXGI_OUTPUT_DESC))(
                        output.value, byref(desc)
                    )
                    if hr != S_OK:
                        raise OSError(f"Output GetDesc failed: 0x{hr & 0xFFFFFFFF:08X}")
                    r = desc.DesktopCoordinates
                    self._desktop_w = r.right - r.left
                    self._desktop_h = r.bottom - r.top

                    output1 = _qi(output.value, IID_IDXGIOutput1)
                    try:
                        dup = c_void_p()
                        fn = _vcall(output1, 22, HRESULT, c_void_p, POINTER(c_void_p))
                        for _ in range(10):
                            hr = fn(output1, self._device, byref(dup))
                            if hr == S_OK:
                                break
                            if hr == DXGI_ERROR_NOT_CURRENTLY_AVAILABLE:
                                time.sleep(0.05)
                                continue
                            raise OSError(
                                f"DuplicateOutput failed: 0x{hr & 0xFFFFFFFF:08X}"
                            )
                        else:
                            raise OSError(
                                "DuplicateOutput unavailable after retries"
                            )
                        self._dup = dup.value
                    finally:
                        _release(output1)
                finally:
                    _release(output.value)
            finally:
                _release(adapter.value)
        finally:
            _release(dxgi_dev)

        self._cap_x, self._cap_y, self._cap_w, self._cap_h = self._region

        td = D3D11_TEXTURE2D_DESC(
            Width=self._cap_w, Height=self._cap_h,
            MipLevels=1, ArraySize=1, Format=DXGI_FORMAT_B8G8R8A8_UNORM,
            SampleDesc_Count=1, SampleDesc_Quality=0,
            Usage=D3D11_USAGE_STAGING, BindFlags=0,
            CPUAccessFlags=D3D11_CPU_ACCESS_READ, MiscFlags=0,
        )
        staging = c_void_p()
        hr = _vcall(
            self._device, 5, HRESULT,
            POINTER(D3D11_TEXTURE2D_DESC), c_void_p, POINTER(c_void_p),
        )(self._device, byref(td), None, byref(staging))
        if hr != S_OK:
            raise OSError(f"CreateTexture2D failed: 0x{hr & 0xFFFFFFFF:08X}")
        self._staging = staging.value

        self._fn_acquire = _vcall(
            self._dup, 8, HRESULT,
            c_uint, POINTER(DXGI_OUTDUPL_FRAME_INFO), POINTER(c_void_p),
        )
        self._fn_release_frame = _vcall(self._dup, 14, HRESULT)
        self._fn_copy = _vcall(
            self._ctx, 46, None,
            c_void_p, c_uint, c_uint, c_uint, c_uint,
            c_void_p, c_uint, POINTER(D3D11_BOX),
        )
        self._fn_map = _vcall(
            self._ctx, 14, HRESULT,
            c_void_p, c_uint, c_uint, c_uint, POINTER(D3D11_MAPPED_SUBRESOURCE),
        )
        self._fn_unmap = _vcall(self._ctx, 15, None, c_void_p, c_uint)

        self._box.left = self._cap_x
        self._box.top = self._cap_y
        self._box.front = 0
        self._box.right = self._cap_x + self._cap_w
        self._box.bottom = self._cap_y + self._cap_h
        self._box.back = 1

    def grab(self, timeout_ms=500):
        """获取一帧。返回 (H, W, 4) BGRA np.ndarray；超时返回 None。"""
        self._res_ptr.value = 0
        hr = self._fn_acquire(
            self._dup, timeout_ms, byref(self._frame_info), byref(self._res_ptr)
        )
        if hr == DXGI_ERROR_WAIT_TIMEOUT:
            return None
        if hr != S_OK:
            raise OSError(f"AcquireNextFrame failed: 0x{hr & 0xFFFFFFFF:08X}")
        try:
            tex = _qi(self._res_ptr.value, IID_ID3D11Texture2D)
            try:
                self._fn_copy(
                    self._ctx, self._staging, 0, 0, 0, 0, tex, 0, byref(self._box)
                )
                hr = self._fn_map(
                    self._ctx, self._staging, 0, D3D11_MAP_READ, 0,
                    byref(self._mapped),
                )
                if hr != S_OK:
                    raise OSError(f"Map failed: 0x{hr & 0xFFFFFFFF:08X}")
                try:
                    buf = np.empty((self._cap_h, self._cap_w, 4), dtype=np.uint8)
                    row_pitch = self._mapped.RowPitch
                    line = self._cap_w * 4
                    if row_pitch == line:
                        ctypes.memmove(buf.ctypes.data, self._mapped.pData,
                                       self._cap_h * line)
                    else:
                        for y in range(self._cap_h):
                            ctypes.memmove(
                                buf[y].ctypes.data,
                                self._mapped.pData + y * row_pitch,
                                line,
                            )
                finally:
                    self._fn_unmap(self._ctx, self._staging, 0)
                return buf
            finally:
                _release(tex)
        finally:
            _release(self._res_ptr.value)
            self._fn_release_frame(self._dup)

    @property
    def desktop_size(self):
        return self._desktop_w, self._desktop_h

    def close(self):
        if self._staging:
            _release(self._staging)
            self._staging = None
        if self._dup:
            _release(self._dup)
            self._dup = None
        if self._ctx:
            _release(self._ctx)
            self._ctx = None
        if self._device:
            _release(self._device)
            self._device = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
