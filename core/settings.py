import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

APP_ROOT = Path(os.path.realpath(sys.argv[0])).parent
SETTINGS_FILE = Path(r"d:\pycharm\overwatch-yolo\settings.json")


class Settings:
    _defaults: dict = {
        "verbosity": "debug",
        "detection_radius": 150,
        "threshold": 0.6,
        "h_sensitivity": 2.0,
        "v_sensitivity": 1.8,
        "neural_net_path": "best.pt",
        "activation_button": "VK_XBUTTON1",
        "fire_mode": "按下",
        "v_compensation": 0.75,
        "h_compensation": 0.0,
        "yaw_pixel_count": 6550,
        "pitch_pixel_count": 3220,
        "kalman_filter_enabled": False,
        "kalman_process_noise": 5.0,
        "kalman_measurement_noise": 2.0,
        "kalman_coast_max_frames": 5,
        "kalman_reinit_distance_threshold": 40.0,
    }
    _cache: Optional[dict] = None

    @classmethod
    def _read_file(cls) -> dict:
        filepath = SETTINGS_FILE
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return cls._defaults.copy()

    @classmethod
    def get(cls, key: str, fallback: Any = None) -> Any:
        if cls._cache is None:
            cls._cache = cls._read_file()
        if fallback is not None:
            return cls._cache.get(key, fallback)
        return cls._cache.get(key, cls._defaults.get(key))

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache[key] = value
        cls.flush()

    @classmethod
    def update_many(cls, values: dict[str, Any]) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache.update(values)
        cls.flush()

    @classmethod
    def remove(cls, key: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache.pop(key, None)
        cls.flush()

    @classmethod
    def flush(cls) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        filepath = SETTINGS_FILE
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(cls._cache, f, ensure_ascii=False, indent=4)
