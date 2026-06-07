import contextlib
import math
import multiprocessing
import os
import queue
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import cv2
import numpy as np
import pyautogui
import win32api
import win32con
from math import sqrt
from ultralytics import YOLO

from PyQt6 import QtWidgets, uic
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFileDialog, QDialog, QVBoxLayout, QLabel
from multiprocessing import Pipe, Process, Queue, shared_memory, Event

from core.constants import (
    FIRE_MODE,
    V_ON,
    V_OFF,
    MDL_SWAP,
    CLS_SET,
    CONF_SET,
    RANGE_SET,
    DET_ON,
    DET_OFF,
    DISP_ON,
    DISP_OFF,
    AIM_TOGGLE,
    SPD_X,
    SPD_Y,
    OFF_X,
    OFF_Y,
    BIND_KEY,
    FIRE_MODE_SET,
    SCR_PX360,
    SCR_PXH,
    KF_ON,
    KF_PN,
    KF_MN,
    KF_COAST,
    KF_REINIT,
    HM_ON,
    HM_MAX,
    HM_REACT,
    HM_ALPHA,
    HM_JITTER,
    EVT_READY,
    EVT_LOG,
    EVT_ERR,
    EVT_FATAL,
    EVT_CAP_LOG,
    EVT_PROC_LOG,
    EVT_UI_LOG,
)
from core.settings import Settings, APP_ROOT
from core.log import Log
from core import input_handler
from core import hotkey
from core.kalman import KalmanTracker
from core.humanize import Humanizer
from core.dxgi_capture import DXGICapture

Settings.flush()

_det_counter = 0


@dataclass
class AimState:
    h_sens: float = 0.2
    v_sens: float = 0.0
    det_radius: float = 100
    h_comp: float = 0.0
    v_comp: float = 0.3
    act_key: int | str = 0x05
    enabled: bool = True
    yaw_px: float = 1800
    pitch_px: float = 900
    fire_mode: str = "press"
    toggle_on: bool = False
    prev_pressed: bool = False
    kf_on: bool = False
    kf_coast: int = 5
    kf_reinit_dist: float = 40.0
    valid_cx: Optional[float] = None
    valid_cy: Optional[float] = None
    box_w: float = 0.0
    box_h: float = 0.0
    hm_on: bool = True
    hm_max: float = 12.0
    hm_react: float = 80.0
    hm_alpha: float = 0.55
    hm_jitter: float = 0.4


class Messenger:
    def __init__(self):
        self._pipes = {}
        self._queues = {}

    def create_queue(self, name: str, maxsize: int = 0) -> Queue:
        q = Queue(maxsize=maxsize) if maxsize else Queue()
        self._queues[name] = q
        return q

    def create_pipe(self, name: str):
        a, b = Pipe()
        self._pipes[name] = (a, b)
        return a, b

    def q(self, name: str) -> Queue:
        return self._queues[name]

    def pipe(self, name: str, side: int = 0):
        return self._pipes[name][side]

    def broadcast(self, cmd: str, payload, *targets: str):
        for t in targets:
            self._queues[t].put((cmd, payload))


class ProcessSupervisor:
    def __init__(self, msg: Messenger):
        self._msg = msg
        self._procs: list[Process] = []

    def spawn(self, fn, args, tag: str) -> Process:
        p = Process(target=fn, args=args, daemon=True)
        p.start()
        self._msg.q("log").put((EVT_UI_LOG, f"{tag} 已启动"))
        self._procs.append(p)
        return p

    def shutdown(self):
        for p in self._procs:
            p.terminate()
            p.join(timeout=3)


class SharedBox:
    SHAPE = (1, 6)
    DTYPE = np.float32

    def __init__(self):
        size = int(np.prod(self.SHAPE) * np.dtype(self.DTYPE).itemsize)
        self.shm = shared_memory.SharedMemory(create=True, size=size)
        self.view = np.ndarray(self.SHAPE, dtype=self.DTYPE, buffer=self.shm.buf)
        self.view.fill(0)
        self.event = Event()
        self.lock = multiprocessing.Lock()

    @property
    def name(self) -> str:
        return self.shm.name

    def teardown(self):
        self.shm.close()
        self.shm.unlink()


class SignalRouter:
    DISPATCH = {
        V_ON: "start",
        V_OFF: "stop",
        EVT_READY: "status",
    }

    def __init__(self, pipe, msg: Messenger):
        self._pipe = pipe
        self._msg = msg

    def run(self):
        Log.info("信号路由进程就绪", tag="Router")
        while True:
            if not self._pipe.poll():
                continue
            try:
                raw = self._pipe.recv()
                if not isinstance(raw, tuple) or len(raw) < 2:
                    continue
                cmd, payload = raw[0], raw[1]
                Log.debug(f"收到指令 → {cmd}", tag="Router")
                self._msg.q("log").put((EVT_LOG, raw))
                target = self.DISPATCH.get(cmd)
                if target:
                    Log.debug(f"转发至 [{target}] 队列", tag="Router")
                    self._msg.q(target).put(raw)
                elif cmd == "trigger_error":
                    raise ValueError("手动触发的异常测试")
            except (BrokenPipeError, EOFError) as e:
                Log.error(f"管道连接中断: {e}", tag="Router")
                self._msg.q("log").put((EVT_ERR, str(e)))
            except Exception as e:
                Log.error(f"路由异常: {e}", tag="Router")
                self._msg.q("log").put((EVT_ERR, str(e)))


class CaptureWorker:
    def __init__(self, msg: Messenger, pipe_parent, model_path: str, box: SharedBox):
        self._msg = msg
        self._pipe = pipe_parent
        self._model_path = model_path
        self._box = box
        self._model = None
        self._yolo_on = False
        self._conf = 0.5
        self._aim_range = 20
        self._display_on = False
        self._shm = None
        self._shm_arr = None

    def run(self):
        Log.info("捕获工作进程就绪", tag="Capture")
        self._load_model()
        self._pipe.send((EVT_READY, True))

        with contextlib.suppress(KeyboardInterrupt):
            while True:
                try:
                    cmd, info = self._msg.q("start").get(timeout=1)
                    self._msg.q("log").put((EVT_CAP_LOG, (cmd, info)))
                    if cmd == V_ON:
                        Log.info("启动屏幕捕获流", tag="Capture")
                        self._stream()
                    elif cmd == MDL_SWAP:
                        self._model_path = info
                        self._load_model()
                except queue.Empty:
                    pass
                except Exception as e:
                    Log.error(f"捕获调度异常: {e}", tag="Capture")
                    self._msg.q("log").put((EVT_ERR, str(e)))

    def _load_model(self):
        try:
            if not os.path.exists(self._model_path):
                Log.warn(f"模型文件不存在: {self._model_path}", tag="Model")
            self._model = YOLO(self._model_path)
            Log.success(f"模型加载完成 → {self._model_path}", tag="Model")
        except Exception as e:
            Log.error(f"模型加载失败: {e}", tag="Model")
            self._msg.q("log").put((EVT_ERR, str(e)))
            self._model = None

    def _stream(self):
        global _det_counter
        _det_counter = 0
        self._yolo_on = False
        self._conf = 0.5
        self._aim_range = 20

        stop = self._msg.q("stop")
        while not stop.empty():
            try:
                stop.get_nowait()
            except Exception:
                break

        sw, sh = pyautogui.size()
        Log.info(f"屏幕分辨率 {sw}×{sh}, 捕获区域 320×320", tag="Capture")
        region = ((sw - 320) // 2, (sh - 320) // 2, 320, 320)

        self._shm = shared_memory.SharedMemory(name=self._box.name)
        self._shm_arr = np.ndarray((1, 6), dtype=np.float32, buffer=self._shm.buf)
        try:
            with DXGICapture(region) as cap:
                while True:
                    try:
                        if not stop.empty():
                            c, _ = stop.get()
                            if c in (V_OFF, MDL_SWAP):
                                break

                        self._drain_yolo_queue()

                        bgra = cap.grab()
                        if bgra is None:
                            continue
                        frame = bgra[..., :3]

                        if self._yolo_on and self._model is not None:
                            frame = self._infer(frame)

                        try:
                            self._msg.q("frame").put_nowait(frame)
                        except queue.Full:
                            pass
                    except Exception as e:
                        Log.warn(f"捕获流中断: {e}", tag="Capture")
                        self._msg.q("log").put((EVT_ERR, str(e)))
                        break
        finally:
            self._shm.close()
            self._shm = None
            self._shm_arr = None

    def _drain_yolo_queue(self):
        yq = self._msg.q("yolo")
        if yq.empty():
            return
        item = yq.get()
        if not isinstance(item, tuple):
            return
        c, v = item
        self._msg.q("log").put((EVT_PROC_LOG, item))
        handlers = {
            DET_ON: lambda: setattr(self, "_yolo_on", True),
            DET_OFF: lambda: setattr(self, "_yolo_on", False),
            CONF_SET: lambda: setattr(self, "_conf", v),
            RANGE_SET: lambda: setattr(self, "_aim_range", v),
            DISP_ON: lambda: setattr(self, "_display_on", True),
            DISP_OFF: lambda: setattr(self, "_display_on", False),
        }
        fn = handlers.get(c)
        if fn:
            fn()

    def _infer(self, frame):
        global _det_counter
        try:
            res = self._model.predict(
                frame,
                save=False,
                device="cuda:0",
                verbose=False,
                save_txt=False,
                half=True,
                conf=self._conf,
                classes=[0],
            )

            boxes = res[0].boxes.xyxy
            fh, fw = frame.shape[:2]
            cx, cy = fw / 2, fh / 2

            boxes_np = [b.cpu().numpy() for b in boxes]
            dists = [sqrt(((x1+x2)/2-cx)**2+((y1+y2)/2-cy)**2)
                     for x1,y1,x2,y2 in boxes_np]

            if dists:
                idx = int(np.argmin(dists))
                best = boxes_np[idx]
                best_d = float(dists[idx])
            else:
                best = None
                best_d = None

            if self._shm_arr is not None:
                with self._box.lock:
                    self._shm_arr.fill(0)
                    if best is not None:
                        _det_counter += 1
                        self._shm_arr[0, :4] = best
                        self._shm_arr[0, 4] = best_d
                        self._shm_arr[0, 5] = _det_counter
                self._box.event.set()

            if not self._display_on:
                return frame

            drawn = res[0].plot()
            cv2.circle(drawn, (int(cx), int(cy)), int(self._aim_range), (173, 216, 230), 1)

            for (x1, y1, x2, y2), d in zip(boxes_np, dists):
                bc = (int((x1+x2)/2), int((y1+y2)/2))
                cv2.rectangle(drawn, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 0), 2)
                cv2.circle(drawn, bc, 5, (0, 0, 255), -1)
                cv2.line(drawn, bc, (int(cx), int(cy)), (255, 255, 0), 2)
                cv2.putText(drawn, f"{d:.1f}px", (int(x1), int(y1)-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

            if best is not None and best_d < self._aim_range:
                x1, y1, x2, y2 = best
                bc = (int((x1+x2)/2), int((y1+y2)/2))
                cv2.rectangle(drawn, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 3)
                cv2.circle(drawn, bc, 5, (0, 255, 0), -1)
                cv2.line(drawn, bc, (int(cx), int(cy)), (255, 0, 0), 3)

            return drawn
        except Exception as e:
            Log.error(f"推理异常: {e}", tag="Capture")
            return frame


class AimWorker:
    HALF_CAP = 160

    def __init__(self, box: SharedBox, msg: Messenger):
        self._box = box
        self._msg = msg
        self._st = AimState(
            kf_on=Settings.get("kalman_filter_enabled", False),
            kf_coast=int(Settings.get("kalman_coast_max_frames", 5)),
            kf_reinit_dist=float(Settings.get("kalman_reinit_distance_threshold", 40.0)),
            hm_on=bool(Settings.get("humanize_enabled", True)),
            hm_max=float(Settings.get("humanize_max_speed", 12.0)),
            hm_react=float(Settings.get("humanize_reaction_dist", 80.0)),
            hm_alpha=float(Settings.get("humanize_alpha", 0.55)),
            hm_jitter=float(Settings.get("humanize_jitter", 0.4)),
        )
        self._kf = KalmanTracker(
            process_noise=Settings.get("kalman_process_noise", 5.0),
            measurement_noise=Settings.get("kalman_measurement_noise", 2.0),
        )
        self._hm = Humanizer(
            max_speed=Settings.get("humanize_max_speed", 12.0),
            reaction_dist=Settings.get("humanize_reaction_dist", 80.0),
            alpha=Settings.get("humanize_alpha", 0.55),
            jitter=Settings.get("humanize_jitter", 0.4),
        )
        self._last_uid = 0

    def run(self):
        shm = shared_memory.SharedMemory(name=self._box.name)
        buf = np.ndarray((1, 6), dtype=np.float32, buffer=shm.buf)
        try:
            while True:
                self._poll_commands()
                with self._box.lock:
                    snap = buf.copy()
                x1, y1, x2, y2, dist, uid = snap[0]
                if uid == self._last_uid:
                    continue
                self._last_uid = int(uid)
                if not np.all(snap[0, :5] == 0):
                    self._on_detection(x1, y1, x2, y2, dist)
                else:
                    self._on_miss()
        except KeyboardInterrupt:
            pass
        finally:
            shm.close()

    def _poll_commands(self):
        aq = self._msg.q("aim")
        if aq.empty():
            return
        item = aq.get()
        if not isinstance(item, tuple):
            return
        c, v = item
        st = self._st
        mapping = {
            AIM_TOGGLE: lambda: setattr(st, "enabled", v),
            SPD_X: lambda: setattr(st, "h_sens", v),
            SPD_Y: lambda: setattr(st, "v_sens", v),
            RANGE_SET: lambda: setattr(st, "det_radius", v),
            OFF_X: lambda: setattr(st, "h_comp", v),
            OFF_Y: lambda: setattr(st, "v_comp", v),
            BIND_KEY: lambda: setattr(st, "act_key", v),
            FIRE_MODE_SET: lambda: setattr(st, "fire_mode", v),
            SCR_PX360: lambda: setattr(st, "yaw_px", v),
            SCR_PXH: lambda: setattr(st, "pitch_px", v),
            KF_ON: lambda: self._toggle_kalman(v),
            KF_PN: lambda: self._rebuild_kf(pn=v),
            KF_MN: lambda: self._rebuild_kf(mn=v),
            KF_COAST: lambda: setattr(st, "kf_coast", int(v)),
            KF_REINIT: lambda: setattr(st, "kf_reinit_dist", float(v)),
            HM_ON: lambda: self._toggle_humanize(v),
            HM_MAX: lambda: (setattr(st, "hm_max", float(v)), self._hm.set_max_speed(v)),
            HM_REACT: lambda: (setattr(st, "hm_react", float(v)), self._hm.set_reaction_dist(v)),
            HM_ALPHA: lambda: (setattr(st, "hm_alpha", float(v)), self._hm.set_alpha(v)),
            HM_JITTER: lambda: (setattr(st, "hm_jitter", float(v)), self._hm.set_jitter(v)),
        }
        fn = mapping.get(c)
        if fn:
            fn()

    def _toggle_kalman(self, on):
        self._st.kf_on = on
        if not on:
            self._kf.reset()

    def _toggle_humanize(self, on):
        self._st.hm_on = bool(on)
        self._hm.reset()

    def _rebuild_kf(self, pn=None, mn=None):
        self._kf = KalmanTracker(
            process_noise=pn
            if pn is not None
            else Settings.get("kalman_process_noise", 5.0),
            measurement_noise=mn
            if mn is not None
            else Settings.get("kalman_measurement_noise", 2.0),
        )

    def _resolve_key(self) -> int:
        k = self._st.act_key
        if isinstance(k, str) and k.startswith("0x"):
            return int(k, 16)
        return int(k)

    def _should_fire(self, in_range: bool) -> bool:
        st = self._st
        vk = self._resolve_key()
        lk = bool(win32api.GetKeyState(vk) & 0x8000)
        sh = bool(win32api.GetKeyState(win32con.VK_SHIFT) & 0x8000)

        if st.fire_mode == "press":
            return st.enabled and in_range and lk
        if st.fire_mode == "shift+press":
            return st.enabled and in_range and (sh and lk)
        if st.fire_mode == "toggle":
            if lk and not st.prev_pressed:
                st.toggle_on = not st.toggle_on
            st.prev_pressed = lk
            return st.enabled and in_range and st.toggle_on
        return False

    def _compute_offset(self, cx, cy, bx1, by1, bx2, by2):
        st = self._st
        rx = cx - self.HALF_CAP
        ry = cy - self.HALF_CAP
        dx = (bx2 - bx1) * st.h_comp
        dy = -(cy - by1) * st.v_comp
        tx = rx + dx
        ty = ry + dy
        ppd_x = st.yaw_px / 360
        ppd_y = st.pitch_px / 180
        mx = (tx / ppd_x) * st.h_sens * 2
        my = (ty / ppd_y) * st.v_sens * 2
        return mx, my, math.sqrt(tx**2 + ty**2)

    def _fire(self, mx, my):
        if self._st.hm_on:
            sx, sy = self._hm.shape(mx, my)
        else:
            sx, sy = mx / 2, my / 2
        ix, iy = round(sx), round(sy)
        if ix != 0 or iy != 0:
            input_handler.move_mouse(ix, iy)

    def _on_detection(self, x1, y1, x2, y2, dist):
        st = self._st
        raw_cx = (x1 + x2) / 2
        raw_cy = (y1 + y2) / 2

        if st.kf_on:
            if not self._kf.is_initialized():
                self._kf.init_state(raw_cx, raw_cy)
                cx, cy = raw_cx, raw_cy
            else:
                jd = 0.0
                if st.valid_cx is not None:
                    jd = math.sqrt(
                        (raw_cx - st.valid_cx) ** 2 + (raw_cy - st.valid_cy) ** 2
                    )
                if jd > st.kf_reinit_dist:
                    self._kf.init_state(raw_cx, raw_cy)
                    cx, cy = raw_cx, raw_cy
                else:
                    p = self._kf.update(raw_cx, raw_cy)
                    cx, cy = float(p[0]), float(p[1])
            st.valid_cx, st.valid_cy = raw_cx, raw_cy
            st.box_w, st.box_h = x2 - x1, y2 - y1
        else:
            cx, cy = raw_cx, raw_cy

        mx, my, _ = self._compute_offset(cx, cy, x1, y1, x2, y2)
        if self._should_fire(dist < st.det_radius):
            self._fire(mx, my)
        else:
            self._hm.reset()

    def _on_miss(self):
        st = self._st
        if not (st.kf_on and self._kf.is_initialized()):
            self._hm.reset()
            return
        if self._kf.coast_frames < st.kf_coast:
            p = self._kf.predict()
            cx, cy = float(p[0]), float(p[1])
            hw, hh = st.box_w / 2, st.box_h / 2
            mx, my, od = self._compute_offset(
                cx, cy, cx - hw, cy - hh, cx + hw, cy + hh
            )
            if self._should_fire(od < st.det_radius):
                self._fire(mx, my)
            else:
                self._hm.reset()
        elif self._kf.coast_frames >= st.kf_coast:
            self._kf.reset()
            st.valid_cx = st.valid_cy = None
            self._hm.reset()


class LazySlider:
    def __init__(self, widget, spinbox, xform, formatter, interval=200):
        self._w = widget
        self._d = spinbox
        self._x = xform
        self._f = formatter
        self._val = None
        self._held = False
        self._syncing = False
        self._cb: Optional[Callable] = None
        self._timer = QTimer()
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self._flush)
        widget.sliderPressed.connect(self._grab)
        widget.sliderMoved.connect(self._slide)
        widget.sliderReleased.connect(self._release)
        widget.valueChanged.connect(self._change)
        spinbox.valueChanged.connect(self._on_spin)

    @property
    def value(self):
        return self._val

    def bind(self, cb: Callable):
        self._cb = cb

    def set(self, raw: int):
        self._w.setValue(raw)
        v = self._x(raw)
        self._val = v
        self._syncing = True
        self._d.setValue(v)
        self._syncing = False

    def _show(self, v):
        if self._syncing:
            return
        self._syncing = True
        self._d.setValue(v)
        self._syncing = False

    def _on_spin(self, v):
        if self._syncing:
            return
        self._syncing = True
        self._w.setValue(int(round(v / self._x(1))) if self._x(1) != 0 else int(round(v)))
        self._val = v
        self._syncing = False
        if not self._timer.isActive():
            self._timer.start()

    def _grab(self):
        self._held = True
        self._timer.start()

    def _slide(self, raw):
        v = self._x(raw)
        self._show(v)
        self._val = v

    def _release(self):
        self._held = False
        self._flush()

    def _change(self, raw):
        v = self._x(raw)
        self._show(v)
        self._val = v
        if not self._timer.isActive():
            self._timer.start()

    def _flush(self):
        if self._cb:
            self._cb()
        if not self._held:
            self._timer.stop()


class VideoPopup(QDialog):
    def __init__(self, parent=None, *, on_close: Callable = None):
        super().__init__(parent)
        self._on_close = on_close
        self.setWindowTitle("视频预览")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(320, 320)
        self.resize(512, 512)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.screen = QLabel(self)
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setStyleSheet("background-color: rgb(63, 63, 63);")
        lay.addWidget(self.screen)

    def closeEvent(self, ev):
        if self._on_close:
            self._on_close()
        super().closeEvent(ev)


SLIDER_DEFS = [
    {
        "key": "conf",
        "widget": "confSlider",
        "lcd": "confSpinBox",
        "min": 0,
        "max": 100,
        "xform": lambda v: v / 100,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["yolo"],
        "cmd": CONF_SET,
        "tip": "置信度阈值：低于此值的目标将被忽略，值越高检测越严格",
    },
    {
        "key": "sx",
        "widget": "lockSpeedXHorizontalSlider",
        "lcd": "lockSpeedXSpinBox",
        "min": 0,
        "max": 1000,
        "xform": lambda v: v / 100,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": SPD_X,
        "tip": "水平灵敏度：控制水平方向的瞄准移动速度",
    },
    {
        "key": "sy",
        "widget": "lockSpeedYHorizontalSlider",
        "lcd": "lockSpeedYSpinBox",
        "min": 0,
        "max": 1000,
        "xform": lambda v: v / 100,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": SPD_Y,
        "tip": "垂直灵敏度：控制垂直方向的瞄准移动速度",
    },
    {
        "key": "ar",
        "widget": "aimRangeHorizontalSlider",
        "lcd": "aimRangeSpinBox",
        "min": 0,
        "max": 280,
        "xform": lambda v: v,
        "fmt": lambda v: str(int(v)),
        "targets": ["aim", "yolo"],
        "cmd": RANGE_SET,
        "tip": "检测半径：以屏幕中心为圆心的搜索范围（像素）",
    },
    {
        "key": "ox",
        "widget": "offset_centerxVerticalSlider",
        "lcd": "offset_centerxSpinBox",
        "min": 0,
        "max": 100,
        "xform": lambda v: 1 - (v / 50.0),
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": OFF_X,
        "tip": "水平补偿：调整水平方向的瞄准偏移，向左或向右微调",
    },
    {
        "key": "oy",
        "widget": "offset_centeryVerticalSlider",
        "lcd": "offset_centerySpinBox",
        "min": 0,
        "max": 100,
        "xform": lambda v: v / 100.0,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": OFF_Y,
        "tip": "垂直补偿：调整垂直方向的瞄准偏移，向上或向下微调",
    },
    {
        "key": "kpn",
        "widget": "kalmanProcessNoiseSlider",
        "lcd": "kalmanProcessNoiseSpinBox",
        "min": 1,
        "max": 500,
        "xform": lambda v: v / 10,
        "fmt": lambda v: f"{v:.1f}",
        "targets": ["aim"],
        "cmd": KF_PN,
        "tip": "过程噪声：值越大预测越灵活，能更快跟上目标方向变化",
    },
    {
        "key": "kmn",
        "widget": "kalmanMeasurementNoiseSlider",
        "lcd": "kalmanMeasurementNoiseSpinBox",
        "min": 1,
        "max": 200,
        "xform": lambda v: v / 10,
        "fmt": lambda v: f"{v:.1f}",
        "targets": ["aim"],
        "cmd": KF_MN,
        "tip": "测量噪声：值越大越信任预测而非检测，可减少抖动",
    },
    {
        "key": "kcf",
        "widget": "kalmanCoastFramesSlider",
        "lcd": "kalmanCoastFramesSpinBox",
        "min": 1,
        "max": 30,
        "xform": lambda v: v,
        "fmt": lambda v: str(int(v)),
        "targets": ["aim"],
        "cmd": KF_COAST,
        "tip": "滑行帧数：目标丢失后继续预测的帧数",
    },
    {
        "key": "krd",
        "widget": "kalmanReinitDistSlider",
        "lcd": "kalmanReinitDistSpinBox",
        "min": 5,
        "max": 150,
        "xform": lambda v: v,
        "fmt": lambda v: str(int(v)),
        "targets": ["aim"],
        "cmd": KF_REINIT,
        "tip": "重初始化距离：新目标与预测位置超过此距离时重新初始化滤波器",
    },
    {
        "key": "hms",
        "widget": "humanizeMaxSpeedSlider",
        "lcd": "humanizeMaxSpeedSpinBox",
        "min": 10,
        "max": 500,
        "xform": lambda v: v / 10,
        "fmt": lambda v: f"{v:.1f}",
        "targets": ["aim"],
        "cmd": HM_MAX,
        "tip": "最大速度：限制每帧瞄准移动的最大像素数，模拟人类反应速度",
    },
    {
        "key": "hmr",
        "widget": "humanizeReactionDistSlider",
        "lcd": "humanizeReactionDistSpinBox",
        "min": 5,
        "max": 300,
        "xform": lambda v: v,
        "fmt": lambda v: str(int(v)),
        "targets": ["aim"],
        "cmd": HM_REACT,
        "tip": "反应距离：目标偏移超过此距离时才开始追踪，模拟人类反应延迟",
    },
    {
        "key": "hma",
        "widget": "humanizeAlphaSlider",
        "lcd": "humanizeAlphaSpinBox",
        "min": 5,
        "max": 100,
        "xform": lambda v: v / 100,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": HM_ALPHA,
        "tip": "平滑权重：追踪时的平滑系数，值越小移动越平滑",
    },
    {
        "key": "hmj",
        "widget": "humanizeJitterSlider",
        "lcd": "humanizeJitterSpinBox",
        "min": 0,
        "max": 300,
        "xform": lambda v: v / 100,
        "fmt": lambda v: f"{v:.2f}",
        "targets": ["aim"],
        "cmd": HM_JITTER,
        "tip": "抖动强度：添加随机微小偏移，使移动轨迹更自然",
    },
]


class App:
    def __init__(self):
        self._msg = Messenger()
        self._sliders: dict[str, LazySlider] = {}
        self._model_path: str = ""
        self._video_on = False
        self._yolo_on = False
        self._stream_on = False
        self._popup: Optional[VideoPopup] = None
        self._fps = 0.0
        self._frames = 0
        self._t0 = time.time()

        self._qt = QtWidgets.QApplication(sys.argv)
        self._qt.setStyleSheet(
            "QToolTip { color: #e0e0e0; background-color: #2d2d2d; "
            "border: 1px solid #555; padding: 4px; font-size: 12px; }"
        )
        self._ui = uic.loadUi(APP_ROOT / "ui" / "VisionAimWindow.ui")
        self._ui.setWindowTitle("VisionAim")
        self._ui.setFixedSize(772, 570)

        self._build_sliders()
        self._bind_buttons()
        self._sync_video_btn()

        self._render_ticker = QTimer()
        self._render_ticker.timeout.connect(self._paint)
        self._render_ticker.start(5)

    def _build_sliders(self):
        for d in SLIDER_DEFS:
            w = getattr(self._ui, d["widget"])
            spin = getattr(self._ui, d["lcd"])
            w.setMinimum(d["min"])
            w.setMaximum(d["max"])
            if "step" in d:
                w.setSingleStep(d["step"])
            spin.setMinimum(min(d["xform"](d["min"]), d["xform"](d["max"])))
            spin.setMaximum(max(d["xform"](d["min"]), d["xform"](d["max"])))
            x1 = d["xform"](1)
            if x1 >= 1.0:
                spin.setDecimals(0)
                spin.setSingleStep(1.0)
            elif x1 >= 0.1:
                spin.setDecimals(1)
                spin.setSingleStep(0.1)
            else:
                spin.setDecimals(2)
                spin.setSingleStep(0.01)
            s = LazySlider(w, spin, d["xform"], d["fmt"])
            if "tip" in d:
                w.setToolTip(d["tip"])
                spin.setToolTip(d["tip"])
            s.bind(
                lambda _d=d: self._msg.broadcast(
                    _d["cmd"], self._sliders[_d["key"]].value, *_d["targets"]
                )
            )
            self._sliders[d["key"]] = s

    def _bind_buttons(self):
        ui = self._ui
        ui.OpVideoButton.clicked.connect(self._flip_video)
        ui.OpYoloButton.clicked.connect(self._flip_yolo)
        ui.saveConfigButton.clicked.connect(self._save_settings)
        ui.chooseModelButton.clicked.connect(self._browse_model)
        ui.triggerMethodComboBox.currentTextChanged.connect(self._change_trigger)
        ui.HotkeyPushButton.clicked.connect(
            lambda: self._rebind_key(ui.HotkeyPushButton.text())
        )
        ui.kalmanFilterCheckBox.stateChanged.connect(
            lambda: self._msg.broadcast(
                KF_ON, ui.kalmanFilterCheckBox.isChecked(), "aim"
            )
        )
        ui.humanizeCheckBox.stateChanged.connect(
            lambda: self._msg.broadcast(
                HM_ON, ui.humanizeCheckBox.isChecked(), "aim"
            )
        )

    def _change_trigger(self, label):
        self._msg.broadcast(FIRE_MODE_SET, FIRE_MODE.get(label, "press"), "aim")

    def _rebind_key(self, fallback):
        vk = hotkey.capture_hotkey(fallback)
        name = hotkey.vk_code_to_name(vk)
        if vk != "UNKNOWN":
            self._ui.HotkeyPushButton.setText(name)
            self._msg.broadcast(BIND_KEY, vk, "aim")

    def _sync_video_btn(self):
        self._ui.OpVideoButton.setText(
            "关闭视频预览" if self._video_on else "打开视频预览"
        )

    def _sync_capture_stream(self):
        want_on = self._video_on or self._yolo_on
        if want_on and not self._stream_on:
            self._msg.pipe("ctrl", 0).send((V_ON, "screen"))
            self._stream_on = True
        elif not want_on and self._stream_on:
            self._msg.pipe("ctrl", 0).send((V_OFF, "screen"))
            self._stream_on = False

    def _flip_video(self):
        if self._video_on:
            self._ui.OpVideoButton.setText("关闭视频显示中...")
            if self._popup:
                self._popup.close()
                self._popup = None
            self._video_on = False
            self._msg.broadcast(DISP_OFF, None, "yolo")
        else:
            self._ui.OpVideoButton.setText("打开视频显示中...")
            if not self._popup:
                self._popup = VideoPopup(self._ui, on_close=self._on_popup_gone)
                self._popup.show()
            self._video_on = True
            self._msg.broadcast(DISP_ON, None, "yolo")
        self._sync_capture_stream()
        self._sync_video_btn()

    def _on_popup_gone(self):
        self._popup = None
        self._video_on = False
        self._msg.broadcast(DISP_OFF, None, "yolo")
        self._sync_capture_stream()
        self._sync_video_btn()

    def _flip_yolo(self):
        if self._yolo_on:
            self._msg.broadcast(DET_OFF, None, "yolo")
            self._ui.OpYoloButton.setText("开启 YOLO")
            self._yolo_on = False
        else:
            self._msg.broadcast(CLS_SET, "0", "yolo")
            self._msg.broadcast(CONF_SET, self._sliders["conf"].value, "yolo")
            self._msg.broadcast(RANGE_SET, self._sliders["ar"].value, "yolo")
            self._msg.broadcast(DET_ON, None, "yolo")
            self._ui.OpYoloButton.setText("关闭 YOLO")
            self._yolo_on = True
        self._sync_capture_stream()

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self._ui,
            "选择模型文件",
            "",
            "模型文件 (*.pt *.engine *.onnx);;所有文件 (*.*)",
        )
        if path:
            self._ui.modelFileLabel.setText(os.path.basename(path))
            self._model_path = path

    def _save_settings(self):
        Settings.update_many(
            {
                "neural_net_path": self._model_path,
                "threshold": self._sliders["conf"].value,
                "h_sensitivity": self._sliders["sx"].value,
                "v_sensitivity": self._sliders["sy"].value,
                "detection_radius": self._sliders["ar"].value,
                "h_compensation": self._sliders["ox"].value,
                "v_compensation": self._sliders["oy"].value,
                "activation_button": self._ui.HotkeyPushButton.text(),
                "fire_mode": self._ui.triggerMethodComboBox.currentText(),
                "kalman_filter_enabled": self._ui.kalmanFilterCheckBox.isChecked(),
                "kalman_process_noise": self._sliders["kpn"].value,
                "kalman_measurement_noise": self._sliders["kmn"].value,
                "kalman_coast_max_frames": int(self._sliders["kcf"].value),
                "kalman_reinit_distance_threshold": self._sliders["krd"].value,
                "humanize_enabled": self._ui.humanizeCheckBox.isChecked(),
                "humanize_max_speed": self._sliders["hms"].value,
                "humanize_reaction_dist": self._sliders["hmr"].value,
                "humanize_alpha": self._sliders["hma"].value,
                "humanize_jitter": self._sliders["hmj"].value,
            }
        )
        Log.success("当前配置已保存", tag="Config")
        self._msg.q("log").put((EVT_UI_LOG, "配置已保存"))

    def _paint(self):
        fq = self._msg.q("frame")
        if not self._popup:
            while not fq.empty():
                try:
                    fq.get_nowait()
                except queue.Empty:
                    break
            return
        frame = None
        if not fq.empty():
            while not fq.empty():
                frame = fq.get()
        if frame is None:
            return

        self._frames += 1
        now = time.time()
        dt = now - self._t0
        if dt >= 0.5:
            self._fps = self._frames / dt
            self._frames = 0
            self._t0 = now

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape
        qimg = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        cv2.putText(
            frame,
            f"FPS: {self._fps:.1f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 0, 0),
            2,
            cv2.LINE_AA,
        )
        px = QPixmap.fromImage(qimg).scaled(
            self._popup.screen.size(),
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
            transformMode=Qt.TransformationMode.SmoothTransformation,
        )
        self._popup.screen.setPixmap(px)

    def _hydrate(self):
        try:
            self._apply_all()
        except Exception as e:
            Log.error(f"配置加载失败: {e}", tag="Config")
            self._msg.q("log").put((EVT_UI_LOG, f"配置读取失败: {e}"))

    def _apply_all(self):
        Log.success("用户配置加载完成", tag="Config")
        self._msg.q("log").put((EVT_UI_LOG, "配置读取成功"))

        self._model_path = Settings.get("neural_net_path", "yolov11n.pt")

        self._sliders["conf"].set(int(Settings.get("threshold", 0.5) * 100))
        self._sliders["sx"].set(int(Settings.get("h_sensitivity", 0.5) * 100))
        self._sliders["sy"].set(int(Settings.get("v_sensitivity", 0.5) * 100))
        self._sliders["ar"].set(int(Settings.get("detection_radius", 100)))
        self._sliders["oy"].set(int(Settings.get("v_compensation", 0.3) * 100))
        self._sliders["ox"].set(int((1 - Settings.get("h_compensation", 0)) * 50))
        self._sliders["kpn"].set(int(Settings.get("kalman_process_noise", 5.0) * 10))
        self._sliders["kmn"].set(int(Settings.get("kalman_measurement_noise", 2.0) * 10))
        self._sliders["kcf"].set(int(Settings.get("kalman_coast_max_frames", 5)))
        self._sliders["krd"].set(int(Settings.get("kalman_reinit_distance_threshold", 40.0)))
        self._sliders["hms"].set(int(Settings.get("humanize_max_speed", 12.0) * 10))
        self._sliders["hmr"].set(int(Settings.get("humanize_reaction_dist", 80.0)))
        self._sliders["hma"].set(int(Settings.get("humanize_alpha", 0.55) * 100))
        self._sliders["hmj"].set(int(Settings.get("humanize_jitter", 0.4) * 100))

        self._msg.broadcast(AIM_TOGGLE, True, "aim")
        self._msg.broadcast(CLS_SET, "0", "yolo")

        lk = Settings.get("activation_button", "0x05")
        self._ui.HotkeyPushButton.setText(lk)
        self._msg.broadcast(BIND_KEY, hotkey.vk_name_to_code(lk), "aim")

        self._ui.triggerMethodComboBox.setCurrentText(
            Settings.get("fire_mode", "按下")
        )
        self._msg.broadcast(
            SCR_PX360, Settings.get("yaw_pixel_count", 1800), "aim"
        )
        self._msg.broadcast(SCR_PXH, Settings.get("pitch_pixel_count", 900), "aim")

        kf = Settings.get("kalman_filter_enabled", False)
        self._ui.kalmanFilterCheckBox.setChecked(kf)
        self._msg.broadcast(KF_ON, kf, "aim")

        hm = Settings.get("humanize_enabled", False)
        self._ui.humanizeCheckBox.setChecked(hm)
        self._msg.broadcast(HM_ON, hm, "aim")

    def _watch_status(self):
        t = QTimer(self._ui)
        t.timeout.connect(self._drain_status)
        t.start(500)

    def _drain_status(self):
        sq = self._msg.q("status")
        if sq.empty():
            return
        tag, body = sq.get_nowait()
        if tag == EVT_READY and body is True:
            Log.success("全部初始化完成，系统就绪", tag="UI")
        elif tag == EVT_ERR:
            Log.warning(f"运行时警告: {body}", tag="UI")
        elif tag == EVT_FATAL:
            Log.error(f"致命错误: {body}", tag="UI")

    def _watch_logs(self):
        t = QTimer(self._ui)
        t.timeout.connect(self._drain_logs)
        t.start(100)

    def _drain_logs(self):
        lq = self._msg.q("log")
        if lq.empty():
            return
        tag, body = lq.get_nowait()
        if tag == EVT_ERR:
            Log.error(
                f"子进程错误 → {body if isinstance(body, str) else str(body)}",
                tag="IPC",
            )

    def launch(self):
        self._msg.create_pipe("ctrl")
        self._msg.create_queue("start")
        self._msg.create_queue("stop")
        self._msg.create_queue("frame", maxsize=1)
        self._msg.create_queue("yolo")
        self._msg.create_queue("status")
        self._msg.create_queue("log")
        self._msg.create_queue("aim")

        self._msg.q("log").put((EVT_UI_LOG, "通信管道已就绪"))
        self._hydrate()

        box = SharedBox()
        Log.info(f"共享内存已映射 → {box.name}", tag="SHM")

        sup = ProcessSupervisor(self._msg)
        sup.spawn(
            SignalRouter(self._msg.pipe("ctrl", 1), self._msg).run,
            (),
            "信号路由",
        )
        sup.spawn(
            CaptureWorker(
                self._msg, self._msg.pipe("ctrl", 0), self._model_path, box
            ).run,
            (),
            "捕获工作进程",
        )
        sup.spawn(
            AimWorker(box, self._msg).run,
            (),
            "瞄准工作进程",
        )

        self._ui.show()
        self._watch_status()
        self._watch_logs()
        self._ui.modelFileLabel.setText(os.path.basename(self._model_path))
        self._msg.broadcast(CONF_SET, self._sliders["conf"].value, "yolo")
        Log.success("VisionAim 启动完成", tag="UI")
        sys.exit(self._qt.exec())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    App().launch()
