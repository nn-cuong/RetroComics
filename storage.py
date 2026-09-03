import os
import json
from constants import THEMES

SAVES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comic_saves.json")
SETTINGS_KEY = "__retrocomics_settings__"

def load_save(filepath):
    try:
        with open(SAVES_FILE, 'r', encoding='utf-8') as f:
            saves = json.load(f)
        return saves.get(filepath, {"scroll_y": 0, "font_size": 34, "view_mode": 0})
    except Exception:
        return {"scroll_y": 0, "font_size": 34, "view_mode": 0}

def write_save(filepath, scroll_y, font_size=34, view_mode=0):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
        saves[filepath] = {"scroll_y": scroll_y, "font_size": font_size, "view_mode": view_mode}
        with open(SAVES_FILE, 'w', encoding='utf-8') as f:
            json.dump(saves, f)
    except Exception:
        pass

def load_settings():
    try:
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
            return saves.get(SETTINGS_KEY, {})
    except Exception:
        pass
    return {}

def write_settings(new_settings):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r', encoding='utf-8') as f:
                saves = json.load(f)
        current = saves.get(SETTINGS_KEY, {})
        current.update(new_settings)
        saves[SETTINGS_KEY] = current
        with open(SAVES_FILE, 'w', encoding='utf-8') as f:
            json.dump(saves, f)
    except Exception:
        pass

def load_theme_idx():
    settings = load_settings()
    try:
        return int(settings.get("theme_idx", 0)) % len(THEMES)
    except Exception:
        return 0

def write_theme_idx(theme_idx):
    write_settings({"theme_idx": theme_idx % len(THEMES)})

def load_library_view():
    settings = load_settings()
    return settings.get("library_view", "list")

def write_library_view(view_mode):
    write_settings({"library_view": view_mode})

def load_reader_rotation_idx():
    settings = load_settings()
    try:
        return int(settings.get("reader_rotation_idx", 0)) % 4
    except Exception:
        return 0

def write_reader_rotation_idx(rotation_idx):
    write_settings({"reader_rotation_idx": rotation_idx % 4})
