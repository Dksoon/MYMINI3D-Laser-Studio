import os
import json
from pathlib import Path

APP_NAME = "MYMINI3D"
APP_VERSION = "1.0.0"

def get_app_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_library_dir() -> Path:
    d = get_app_data_dir() / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_product_folder(category: str, product_name: str) -> Path:
    """Create and return the folder for a specific product."""
    # Sanitise names for use as folder names
    def _safe(s: str) -> str:
        for c in r'\/:*?"<>|':
            s = s.replace(c, "_")
        return s.strip()
    d = get_library_dir() / _safe(category) / _safe(product_name)
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_all_categories() -> list:
    """Return list of category folder names that exist in the library."""
    lib = get_library_dir()
    return sorted([
        d.name for d in lib.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])

def get_thumbnails_dir() -> Path:
    d = get_app_data_dir() / "thumbnails"
    d.mkdir(parents=True, exist_ok=True)
    return d

CONFIG_FILE = get_app_data_dir() / "config.json"

_defaults = {
    "telegram_token": "",
    "telegram_chat_id": "",
    "telegram_enabled": False,
    "gdrive_enabled": False,
    "gdrive_folder_id": "",
    "gdrive_credentials_path": "",
    "update_url": "",
    "update_check_on_start": True,
    "laser_bed_width_mm": 400,
    "laser_bed_height_mm": 400,
    "theme": "dark",
    "language": "en",
    "auto_deduct_on_cut":       True,
    "default_speed_cut":        8.0,
    "default_speed_vector":     20.0,
    "default_speed_raster":     200.0,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            for k, v in _defaults.items():
                data.setdefault(k, v)
            # Clear old wrong update URL so update_service uses the correct hardcoded one
            if "MYMINI3D/releases" in data.get("update_url", ""):
                data["update_url"] = ""
            return data
        except Exception:
            pass
    return dict(_defaults)


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
