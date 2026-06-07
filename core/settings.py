import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

APP_ROOT = Path(os.path.realpath(sys.argv[0])).parent
SETTINGS_FILE = Path(r"d:\pycharm\overwatch-yolo\settings.json")

PROFILE_KEYS = {
    "h_sensitivity", "v_sensitivity", "detection_radius",
    "h_compensation", "v_compensation",
    "kalman_filter_enabled", "kalman_process_noise", "kalman_measurement_noise",
    "kalman_coast_max_frames", "kalman_reinit_distance_threshold",
    "humanize_enabled", "humanize_max_speed", "humanize_reaction_dist",
    "humanize_alpha", "humanize_jitter",
}


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
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = cls._defaults.copy()

        if "profiles" not in data:
            data["profiles"] = {}
        data.setdefault("active_profile", "Default")

        if not data["profiles"]:
            default_data = {k: data[k] for k in PROFILE_KEYS if k in data}
            if not default_data:
                default_data = {k: v for k, v in cls._defaults.items() if k in PROFILE_KEYS}
            data["profiles"]["Default"] = default_data

        return data

    @classmethod
    def _profile_data(cls) -> dict:
        active = cls._cache.get("active_profile", "Default")
        return cls._cache.setdefault("profiles", {}).setdefault(active, {})

    @classmethod
    def get(cls, key: str, fallback: Any = None) -> Any:
        if cls._cache is None:
            cls._cache = cls._read_file()
        if key in PROFILE_KEYS:
            pd = cls._profile_data()
            if key in pd:
                return pd[key]
        if fallback is not None:
            return cls._cache.get(key, fallback)
        return cls._cache.get(key, cls._defaults.get(key))

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        if key in PROFILE_KEYS:
            cls._profile_data()[key] = value
        else:
            cls._cache[key] = value
        cls.flush()

    @classmethod
    def update_many(cls, values: dict[str, Any]) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        pd = cls._profile_data()
        for k, v in values.items():
            if k in PROFILE_KEYS:
                pd[k] = v
            else:
                cls._cache[k] = v
        cls.flush()

    @classmethod
    def remove(cls, key: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache.pop(key, None)
        cls._profile_data().pop(key, None)
        cls.flush()

    @classmethod
    def flush(cls) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cls._cache, f, ensure_ascii=False, indent=4)

    # --- Profile management ---

    @classmethod
    def list_profiles(cls) -> list[str]:
        if cls._cache is None:
            cls._cache = cls._read_file()
        return list(cls._cache.get("profiles", {}).keys())

    @classmethod
    def active_profile_name(cls) -> str:
        if cls._cache is None:
            cls._cache = cls._read_file()
        return cls._cache.get("active_profile", "Default")

    @classmethod
    def set_active_profile(cls, name: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache["active_profile"] = name
        cls.flush()

    @classmethod
    def create_profile(cls, name: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        profiles = cls._cache.setdefault("profiles", {})
        if name not in profiles:
            active = cls._cache.get("active_profile", "Default")
            src = profiles.get(active, {})
            profiles[name] = src.copy()
        cls.flush()

    @classmethod
    def delete_profile(cls, name: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        cls._cache.get("profiles", {}).pop(name, None)
        cls.flush()

    @classmethod
    def rename_profile(cls, old: str, new: str) -> None:
        if cls._cache is None:
            cls._cache = cls._read_file()
        profiles = cls._cache.get("profiles", {})
        if old in profiles:
            profiles[new] = profiles.pop(old)
        if cls._cache.get("active_profile") == old:
            cls._cache["active_profile"] = new
        cls.flush()
