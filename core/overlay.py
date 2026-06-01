import ctypes
import math
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

_EnumWindows = user32.EnumWindows
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_GetWindowDC = user32.GetWindowDC
_ReleaseDC = user32.ReleaseDC
_MoveToEx = gdi32.MoveToEx
_LineTo = gdi32.LineTo
_CreatePen = gdi32.CreatePen
_SelectObject = gdi32.SelectObject
_DeleteObject = gdi32.DeleteObject
_GetWindowRect = user32.GetWindowRect
_Ellipse = gdi32.Ellipse
_Rectangle = gdi32.Rectangle

_GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_GetWindowRect.restype = wintypes.BOOL
_MoveToEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.POINTER(wintypes.POINT)]
_MoveToEx.restype = wintypes.BOOL
_LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_LineTo.restype = wintypes.BOOL
_CreatePen.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.COLORREF]
_CreatePen.restype = wintypes.HGDIOBJ
_SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_SelectObject.restype = wintypes.HGDIOBJ
_DeleteObject.argtypes = [wintypes.HGDIOBJ]
_DeleteObject.restype = wintypes.BOOL
_Ellipse.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_Ellipse.restype = wintypes.BOOL
_Rectangle.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
_Rectangle.restype = wintypes.BOOL

PS_SOLID = 0x00000000
CLR_BLUE = 0x000000FF
CLR_RED = 0x00FF0000
CLR_GREEN = 0x0000FF00
CLR_YELLOW = 0x00FFFF00
CLR_WHITE = 0x00FFFFFF


def _find_desktop_hwnd() -> wintypes.HWND:
    result = wintypes.HWND()

    def _cb(hwnd, _lparam):
        rect = wintypes.RECT()
        _GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.left == 0 and rect.top == 0:
            ctypes.cast(_lparam, ctypes.POINTER(wintypes.HWND)).contents.value = hwnd
            return False
        return True

    _EnumWindows(_EnumWindowsProc(_cb), ctypes.byref(result))
    return result


def _make_pen(color, width):
    return _CreatePen(PS_SOLID, width, color)


def draw_rect(hdc, x1, y1, x2, y2, color, width):
    pen = _make_pen(color, width)
    old = _SelectObject(hdc, pen)
    _Rectangle(hdc, x1, y1, x2, y2)
    _SelectObject(hdc, old)
    _DeleteObject(pen)


def draw_circle(hdc, cx, cy, radius, color, width):
    pen = _make_pen(color, width)
    old = _SelectObject(hdc, pen)
    _Ellipse(hdc, cx - radius, cy - radius, cx + radius, cy + radius)
    _SelectObject(hdc, old)
    _DeleteObject(pen)


def draw_line(hdc, x1, y1, x2, y2, color, width):
    pen = _make_pen(color, width)
    old = _SelectObject(hdc, pen)
    _MoveToEx(hdc, x1, y1, None)
    _LineTo(hdc, x2, y2)
    _SelectObject(hdc, old)
    _DeleteObject(pen)


def draw_text(hdc, text, x, y, color, font_size=16):
    hfont = gdi32.CreateFontA(-font_size, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 0, 0, b"Arial")
    old_font = _SelectObject(hdc, hfont)
    old_color = gdi32.SetTextColor(hdc, color)
    gdi32.TextOutA(hdc, x, y, text.encode("utf-8"), len(text))
    gdi32.SetTextColor(hdc, old_color)
    _SelectObject(hdc, old_font)
    gdi32.DeleteObject(hfont)


def render_detections(detections, frame_center, det_radius):
    hwnd = _find_desktop_hwnd()
    hdc = _GetWindowDC(hwnd)

    draw_circle(hdc, frame_center[0], frame_center[1], det_radius, CLR_WHITE, 1)

    for det in detections:
        x1, y1, x2, y2 = det
        bc = ((x1 + x2) // 2, (y1 + y2) // 2)
        draw_rect(hdc, x1, y1, x2, y2, CLR_YELLOW, 2)
        draw_circle(hdc, bc[0], bc[1], 5, CLR_RED, -1)
        draw_line(hdc, bc[0], bc[1], frame_center[0], frame_center[1], CLR_YELLOW, 2)
        dist = math.sqrt((bc[0] - frame_center[0]) ** 2 + (bc[1] - frame_center[1]) ** 2)
        draw_text(hdc, f"{dist:.1f}px", x1, y1 - 10, CLR_BLUE, 16)

    if detections:
        x1, y1, x2, y2 = detections[0]
        bc = ((x1 + x2) // 2, (y1 + y2) // 2)
        d = math.sqrt((bc[0] - frame_center[0]) ** 2 + (bc[1] - frame_center[1]) ** 2)
        if d < aim_range:
            draw_rect(hdc, x1, y1, x2, y2, CLR_GREEN, 3)
            draw_circle(hdc, bc[0], bc[1], 5, CLR_GREEN, -1)
            draw_line(hdc, bc[0], bc[1], frame_center[0], frame_center[1], CLR_RED, 3)

    _ReleaseDC(hwnd, hdc)
