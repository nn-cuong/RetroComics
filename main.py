import sys
import os
import textwrap
import traceback
import json
import re

SAVES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comic_saves.json")
SETTINGS_KEY = "__retrocomics_settings__"

def load_save(filepath):
    try:
        with open(SAVES_FILE, 'r') as f:
            saves = json.load(f)
        return saves.get(filepath, {"scroll_y": 0, "font_size": 34, "view_mode": 0})
    except:
        return {"scroll_y": 0, "font_size": 34, "view_mode": 0}

def write_save(filepath, scroll_y, font_size, view_mode=0):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r') as f:
                saves = json.load(f)
        saves[filepath] = {"scroll_y": scroll_y, "font_size": font_size, "view_mode": view_mode}
        with open(SAVES_FILE, 'w') as f:
            json.dump(saves, f)
    except:
        pass

# Add local bundled vendor
VENDOR_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if os.path.exists(VENDOR_PATH):
    sys.path.insert(0, VENDOR_PATH)

os.environ["PYSDL2_DLL_PATH"] = "/usr/trimui/lib"

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
    import sdl2.sdlimage as sdlimage
except ImportError as e:
    sys.stderr.write("Cannot load SDL2. Error: " + str(e))
    sys.exit(1)

FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf")

SCREEN_W = 1024
SCREEN_H = 768

# Themes
THEMES = [
    {
        "name": "Night Mode",
        "bg": sdl2.ext.Color(23, 25, 28),         # 17191C
        "text": sdl2.SDL_Color(232, 229, 221, 255), # E8E5DD
        "header": sdl2.ext.Color(15, 17, 19),
        "sel": sdl2.ext.Color(60, 60, 60)
    },
    {
        "name": "Light Mode",
        "bg": sdl2.ext.Color(245, 241, 230),      # F5F1E6
        "text": sdl2.SDL_Color(51, 48, 43, 255),  # 33302B
        "header": sdl2.ext.Color(230, 225, 210),
        "sel": sdl2.ext.Color(118, 107, 90)
    }
]

# Library-only palette.  The reader keeps its existing themes and rendering.
LIBRARY_THEMES = [
    {
        "bg": sdl2.ext.Color(20, 20, 20), "header": sdl2.ext.Color(10, 10, 10),
        "text": sdl2.SDL_Color(212, 212, 212, 255), "secondary": sdl2.SDL_Color(154, 154, 154, 255),
        "accent": sdl2.ext.Color(184, 168, 216), "selected": sdl2.ext.Color(60, 60, 60),
        "border": sdl2.ext.Color(136, 156, 192), "divider": sdl2.ext.Color(52, 52, 52),
    },
    {
        "bg": sdl2.ext.Color(244, 236, 216), "header": sdl2.ext.Color(220, 210, 190),
        "text": sdl2.SDL_Color(59, 52, 40, 255), "secondary": sdl2.SDL_Color(118, 107, 90, 255),
        "accent": sdl2.ext.Color(107, 91, 149), "selected": sdl2.ext.Color(229, 235, 241),
        "border": sdl2.ext.Color(102, 137, 181), "divider": sdl2.ext.Color(204, 193, 171),
    }
]

def load_theme_idx():
    settings = load_settings()
    try:
        return int(settings.get("theme_idx", 0)) % len(THEMES)
    except:
        return 0

def write_theme_idx(theme_idx):
    write_settings({"theme_idx": theme_idx % len(THEMES)})

def load_reader_rotation_idx():
    settings = load_settings()
    try:
        return int(settings.get("reader_rotation_idx", 0)) % 4
    except:
        return 0

def write_reader_rotation_idx(rotation_idx):
    write_settings({"reader_rotation_idx": rotation_idx % 4})

def load_settings():
    try:
        with open(SAVES_FILE, 'r') as f:
            saves = json.load(f)
        return saves.get(SETTINGS_KEY, {})
    except:
        return {}

def write_settings(settings_update):
    try:
        saves = {}
        if os.path.exists(SAVES_FILE):
            with open(SAVES_FILE, 'r') as f:
                saves = json.load(f)
        settings = saves.get(SETTINGS_KEY, {})
        settings.update(settings_update)
        saves[SETTINGS_KEY] = settings
        with open(SAVES_FILE, 'w') as f:
            json.dump(saves, f)
    except:
        pass

STATE_BROWSE = 0
STATE_READER = 1
STATE_TOC = 2
STATE_QUIT_CONFIRM = 3
STATE_PAGE_SELECT = 4

def get_directory_contents(path):
    try:
        items = os.listdir(path)
        folders = []
        files = []
        valid_exts = ['.cbz', '.zip', '.cbr', '.rar', '.cb7', '.7z', '.cbt', '.tar', '.pdf']
        for item in items:
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                folders.append(item)
            else:
                ext = os.path.splitext(item)[1].lower()
                if ext in valid_exts:
                    files.append(item)
        folders.sort(key=str.lower)
        files.sort(key=str.lower)
        return folders, files
    except Exception as e:
        return [], []

def get_book_display_metadata(filename):
    """Derive library labels from a filename without changing the real path."""
    stem = os.path.splitext(filename)[0]
    title, separator, author = stem.rpartition(" - ")
    if not separator:
        return stem, ""
    # Keep common initials readable in the small secondary line; discard only
    # the existing display suffix used by the bundled naming convention.
    author = re.sub(r"\b([A-Z])\.([A-Z])\.", r"\1. \2.", author.strip())
    author = re.sub(r"\s+AU$", "", author)
    return title.strip(), author

def draw_book_icon(renderer, x, y, color, background):
    renderer.fill((x, y, 28, 36), color)
    renderer.fill((x + 6, y + 5, 4, 26), background)

import zipfile
import io
import re
import struct
import subprocess

BIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
SEVEN_Z_BIN = "/tmp/7zzs" if os.path.exists("/tmp/7zzs") else (
    os.path.join(BIN_DIR, "7zzs") if os.path.exists(os.path.join(BIN_DIR, "7zzs")) else os.path.join(BIN_DIR, "7zz")
)
UNRAR_BIN = "/tmp/unrar" if os.path.exists("/tmp/unrar") else os.path.join(BIN_DIR, "unrar")

def log_debug(msg):
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass

def bitmap_to_bmp(raw_bytes, width, height, bpp=32):
    file_size = 54 + len(raw_bytes)
    bmp_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
    dib_header = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, bpp, 0, len(raw_bytes), 2835, 2835, 0, 0)
    return bmp_header + dib_header + raw_bytes

def natural_sort_key(s, _nsre=re.compile('([0-9]+)')):
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(s)]

class ComicArchive:
    _active_filepath = None
    _active_pdf = None
    _active_zip = None
    _page_cache = {} # (filepath, page_filename) -> bytes
    _MAX_CACHE_ITEMS = 6

    @classmethod
    def close_active(cls):
        if cls._active_pdf:
            try:
                cls._active_pdf.close()
            except Exception:
                pass
            cls._active_pdf = None
        if cls._active_zip:
            try:
                cls._active_zip.close()
            except Exception:
                pass
            cls._active_zip = None
        cls._active_filepath = None
        cls._page_cache.clear()

    @classmethod
    def get_open_pdf(cls, filepath):
        if cls._active_filepath == filepath and cls._active_pdf is not None:
            return cls._active_pdf
        cls.close_active()
        try:
            import pypdfium2 as pdfium
            cls._active_pdf = pdfium.PdfDocument(filepath)
            cls._active_filepath = filepath
            return cls._active_pdf
        except Exception as e:
            log_debug(f"get_open_pdf error: {e}")
            return None

    @classmethod
    def get_open_zip(cls, filepath):
        if cls._active_filepath == filepath and cls._active_zip is not None:
            return cls._active_zip
        cls.close_active()
        try:
            cls._active_zip = zipfile.ZipFile(filepath, 'r')
            cls._active_filepath = filepath
            return cls._active_zip
        except Exception as e:
            log_debug(f"get_open_zip error: {e}")
            return None

    @classmethod
    def get_pages(cls, filepath):
        pages = []
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
        ext = os.path.splitext(filepath)[1].lower()
        
        # 0. Dedicated PDF Handler
        if ext == '.pdf':
            pdf = cls.get_open_pdf(filepath)
            if pdf is not None:
                try:
                    count = len(pdf)
                    if count > 0:
                        return [f"page_{i+1}" for i in range(count)]
                except Exception as e:
                    log_debug(f"PDF get_pages pypdfium2 error: {e}")
            # Option B: Scan PDF metadata
            try:
                with open(filepath, 'rb') as f:
                    content = f.read(2 * 1024 * 1024)
                    match = re.findall(rb'/Count\s+(\d+)', content)
                    if match:
                        count = max(int(m) for m in match)
                        if count > 0:
                            return [f"page_{i+1}" for i in range(count)]
            except Exception as e:
                log_debug(f"PDF get_pages scan error: {e}")
            return ["page_1"]

        # 1. Built-in zipfile (Universal ZIP / CBZ)
        zf = cls.get_open_zip(filepath)
        if zf is not None:
            try:
                for info in zf.infolist():
                    name = info.filename
                    if name.endswith('/') or name.endswith('\\'):
                        continue
                    if '__MACOSX' in name or '/.' in name or name.startswith('.'):
                        continue
                    if name.lower().endswith(valid_exts):
                        pages.append(name)
            except Exception as e:
                log_debug(f"zipfile get_pages error: {e}")
        
        if pages:
            pages.sort(key=natural_sort_key)
            return pages

        # 2. Universal 7-Zip (7zzs) for CBR, CB7, RAR, 7Z, TAR, etc.
        if os.path.exists(SEVEN_Z_BIN):
            try:
                try:
                    os.chmod(SEVEN_Z_BIN, 0o755)
                except Exception:
                    pass
                p = subprocess.Popen([SEVEN_Z_BIN, 'l', '-ba', '-slt', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, _ = p.communicate()
                current_path = None
                is_dir = False
                for line in stdout.splitlines():
                    line = line.strip()
                    if line.startswith('Path = '):
                        current_path = line[7:].strip()
                    elif line.startswith('Folder = +'):
                        is_dir = True
                    elif line.startswith('Attributes = D'):
                        is_dir = True
                    elif line == '':
                        if current_path and not is_dir:
                            if not ('__MACOSX' in current_path or '/.' in current_path or current_path.startswith('.')):
                                if current_path.lower().endswith(valid_exts):
                                    pages.append(current_path)
                        current_path = None
                        is_dir = False
                if current_path and not is_dir:
                    if not ('__MACOSX' in current_path or '/.' in current_path or current_path.startswith('.')):
                        if current_path.lower().endswith(valid_exts):
                            pages.append(current_path)
            except Exception as e:
                log_debug(f"7zzs get_pages error: {e}")
                
        if pages:
            pages.sort(key=natural_sort_key)
            return pages

        # 3. Dedicated unrar binary fallback for CBR / RAR
        if os.path.exists(UNRAR_BIN):
            try:
                try:
                    os.chmod(UNRAR_BIN, 0o755)
                except Exception:
                    pass
                p = subprocess.Popen([UNRAR_BIN, 'vb', filepath], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, _ = p.communicate()
                for line in stdout.splitlines():
                    name = line.strip()
                    if name and not ('__MACOSX' in name or '/.' in name or name.startswith('.')):
                        if name.lower().endswith(valid_exts):
                            pages.append(name)
            except Exception as e:
                log_debug(f"unrar get_pages error: {e}")

        pages.sort(key=natural_sort_key)
        return pages

    @classmethod
    def read_image_data(cls, filepath, page_filename):
        cache_key = (filepath, page_filename)
        if cache_key in cls._page_cache:
            return cls._page_cache[cache_key]

        ext = os.path.splitext(filepath)[1].lower()
        img_data = None
        
        # 0. Dedicated PDF Page Renderer (Ultra Fast Screen-fit Rasterizer)
        if ext == '.pdf':
            try:
                page_num = int(page_filename.replace("page_", ""))
            except Exception:
                page_num = 1
                
            pdf = cls.get_open_pdf(filepath)
            if pdf is not None:
                try:
                    page = pdf[page_num - 1]
                    pw, ph = page.get_size()
                    # Calculate crisp 1:1 scale for 1024x768 screen (max scale 1.4 for peak sharpness without wasting CPU)
                    scale = max(1.0, min(1.4, 1024.0 / max(1.0, pw)))
                    bitmap = page.render(scale=scale, prefer_bgrx=True)
                    raw_bytes = bytes(bitmap.buffer)
                    w = bitmap.width
                    h = bitmap.height
                    bpp = bitmap.n_channels * 8
                    if raw_bytes and w > 0 and h > 0:
                        img_data = bitmap_to_bmp(raw_bytes, w, h, bpp)
                except Exception as e:
                    import traceback
                    log_debug(f"PDF render exception p{page_num}: {e}\n{traceback.format_exc()}")

        # 1. Built-in zipfile (Universal ZIP / CBZ)
        if not img_data and ext in ('.cbz', '.zip'):
            zf = cls.get_open_zip(filepath)
            if zf is not None:
                try:
                    img_data = zf.read(page_filename)
                except Exception:
                    pass
        
        # 2. Universal 7-Zip stream (7zzs)
        if not img_data and os.path.exists(SEVEN_Z_BIN):
            try:
                p = subprocess.Popen([SEVEN_Z_BIN, 'e', '-so', filepath, page_filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, _ = p.communicate()
                if stdout:
                    img_data = stdout
            except Exception as e:
                log_debug(f"7zzs extract error: {e}")

        # 3. Dedicated unrar stream
        if not img_data and os.path.exists(UNRAR_BIN):
            try:
                p = subprocess.Popen([UNRAR_BIN, 'p', '-inul', '-idq', filepath, page_filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, _ = p.communicate()
                if stdout:
                    img_data = stdout
            except Exception as e:
                log_debug(f"unrar extract error: {e}")

        if img_data:
            if len(cls._page_cache) >= cls._MAX_CACHE_ITEMS:
                oldest_k = next(iter(cls._page_cache))
                del cls._page_cache[oldest_k]
            cls._page_cache[cache_key] = img_data

        return img_data

def main():
    sdl2.SDL_Init(sdl2.SDL_INIT_VIDEO | sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER)
    sdlttf.TTF_Init()

    controllers = []
    for i in range(sdl2.SDL_NumJoysticks()):
        if sdl2.SDL_IsGameController(i):
            controllers.append(sdl2.SDL_GameControllerOpen(i))

    window = sdl2.ext.Window("RetroComics", size=(SCREEN_W, SCREEN_H), flags=sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP)
    window.show()
    renderer = sdl2.ext.Renderer(window, flags=sdl2.SDL_RENDERER_ACCELERATED | sdl2.SDL_RENDERER_PRESENTVSYNC)
    reader_target = None
    reader_target_w = 0
    reader_target_h = 0

    font_path = FONT_PATH.encode('utf-8')
    reading_font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reading_font.ttf")
    if os.path.exists(reading_font_path):
        reading_font_bytes = reading_font_path.encode('utf-8')
    else:
        reading_font_bytes = font_path

    if not os.path.exists(FONT_PATH):
        sys.exit(1)
        
    font_large = sdlttf.TTF_OpenFont(font_path, 40)
    font_small = sdlttf.TTF_OpenFont(font_path, 24)
    font_ui_medium = sdlttf.TTF_OpenFont(font_path, 36)
    
    current_font_size = 34
    font_medium = sdlttf.TTF_OpenFont(reading_font_bytes, current_font_size)

    def render_text(text, font, color):
        if not text.strip(): return None, 0, 0
        if isinstance(color, sdl2.ext.Color):
            color = sdl2.SDL_Color(color.r, color.g, color.b, color.a)
        elif isinstance(color, tuple):
            color = sdl2.SDL_Color(color[0], color[1], color[2], color[3] if len(color)>3 else 255)
        tsurf = sdlttf.TTF_RenderUTF8_Blended(font, text.encode('utf-8'), color)
        if tsurf:
            ttex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, tsurf)
            w, h = tsurf.contents.w, tsurf.contents.h
            sdl2.SDL_FreeSurface(tsurf)
            return ttex, w, h
        return None, 0, 0

    base_path = "/mnt/SDCARD/Books"
    if not os.path.exists(base_path):
        os.makedirs(base_path, exist_ok=True)
    
    current_path = base_path
    folders, files = get_directory_contents(current_path)
    
    state = STATE_BROWSE
    sel_index = 0
    scroll_y = 0
    dpad_up_held = False
    dpad_down_held = False
    dpad_timer = 0
    visible_items = 15
    theme_idx = load_theme_idx()
    reader_rotation_idx = load_reader_rotation_idx()
    
    # Reader Data
    book_pages = [] # List of image filenames
    current_filepath = ""
    current_page_idx = 0
    zoom_level = -1.0 # -1.0 means auto fit width initially
    pan_x = 0
    pan_y = 0
    loaded_texture = None
    loaded_page_idx = -1
    img_w = 0
    img_h = 0
    page_select_temp = 0
    l2_pressed = False
    r2_pressed = False
    
    state_before_quit = STATE_BROWSE
    
    def get_reader_view_size():
        if reader_rotation_idx % 2 == 1:
            return SCREEN_H, SCREEN_W
        return SCREEN_W, SCREEN_H

    def ensure_reader_target(target_w, target_h):
        nonlocal reader_target, reader_target_w, reader_target_h
        if reader_target and reader_target_w == target_w and reader_target_h == target_h:
            return reader_target
        if reader_target:
            sdl2.SDL_DestroyTexture(reader_target)
        reader_target = sdl2.SDL_CreateTexture(
            renderer.sdlrenderer,
            sdl2.SDL_PIXELFORMAT_RGBA8888,
            sdl2.SDL_TEXTUREACCESS_TARGET,
            target_w,
            target_h
        )
        reader_target_w = target_w
        reader_target_h = target_h
        return reader_target

    def rotate_reader_direction(dx, dy):
        rot = reader_rotation_idx % 4
        if rot == 1:
            return -dy, dx
        elif rot == 2:
            return -dx, -dy
        elif rot == 3:
            return dy, -dx
        return dx, dy

    def handle_reader_direction(dx, dy):
        nonlocal pan_x, pan_y, zoom_level, img_h, img_w
        dx, dy = rotate_reader_direction(dx, dy)
        vw, vh = get_reader_view_size()
        
        if zoom_level <= 0:
            zoom_level = vw / float(img_w) if img_w > 0 else 1.0
            
        scaled_w = int(img_w * zoom_level)
        scaled_h = int(img_h * zoom_level)
        
        pan_step = 150 # pixels per dpad press
        
        if dx != 0:
            pan_x += dx * pan_step
        if dy != 0:
            pan_y += dy * pan_step
            
        # Clamp pan_x
        max_pan_x = max(0, scaled_w - vw)
        pan_x = max(0, min(pan_x, max_pan_x))
        # Clamp pan_y
        max_pan_y = max(0, scaled_h - vh)
        pan_y = max(0, min(pan_y, max_pan_y))

    def load_book(filepath):
        nonlocal book_pages, current_page_idx, pan_x, pan_y, zoom_level, current_font_size, current_filepath, loaded_page_idx, loaded_texture
        book_pages = []
        loaded_page_idx = -1
        if loaded_texture:
            sdl2.SDL_DestroyTexture(loaded_texture)
            loaded_texture = None
            
        save_data = load_save(filepath)
        current_page_idx = save_data.get("scroll_y", 0)
        current_font_size = save_data.get("font_size", 34)
        zoom_level = -1.0
        pan_x = 0
        pan_y = 0
        current_filepath = filepath
        
        try:
            pages = ComicArchive.get_pages(filepath)
            log_debug(f"load_book '{filepath}': found {len(pages) if pages else 0} pages")
            if not pages:
                return False
                
            book_pages = pages
            current_page_idx = max(0, min(current_page_idx, len(book_pages) - 1))
            return True
        except Exception as e:
            import traceback
            log_debug(f"load_book exception '{filepath}': {e}\n{traceback.format_exc()}")
            return False

    running = True
    needs_redraw = True
    last_axis_scroll = 0
    show_hud = True
    
    while running:
        events = sdl2.ext.get_events()
        if len(events) > 0:
            needs_redraw = True
            
        current_ticks = sdl2.SDL_GetTicks()
        axis_up = False
        axis_down = False
        for c in controllers:
            lx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
            ly = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
            rx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
            ry = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTY)
            ax = lx if abs(lx) >= abs(rx) else rx
            ay = ly if abs(ly) >= abs(ry) else ry
            if ay < -16000:
                axis_up = True
            elif ay > 16000:
                axis_down = True
            if state == STATE_READER and (current_ticks - last_axis_scroll > 100):
                if abs(ax) >= 16000 or abs(ay) >= 16000:
                    if abs(ax) > abs(ay):
                        handle_reader_direction(1 if ax > 0 else -1, 0)
                    else:
                        handle_reader_direction(0, 1 if ay > 0 else -1)
                    last_axis_scroll = current_ticks
                    needs_redraw = True
                    break
                    
        for event in events:
            if event.type == sdl2.SDL_CONTROLLERAXISMOTION:
                if state == STATE_READER:
                    if event.caxis.axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                        val = event.caxis.value
                        if val > 16000 and not l2_pressed:
                            l2_pressed = True
                            state = STATE_PAGE_SELECT
                            page_select_temp = current_page_idx
                        elif val < 8000:
                            l2_pressed = False
                    elif event.caxis.axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                        val = event.caxis.value
                        if val > 16000 and not r2_pressed:
                            r2_pressed = True
                            state = STATE_PAGE_SELECT
                            page_select_temp = current_page_idx
                        elif val < 8000:
                            r2_pressed = False
            if event.type == sdl2.SDL_QUIT:
                if state in (STATE_READER, STATE_TOC):
                    write_save(current_filepath, current_page_idx, current_font_size)
                running = False
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    if state in (STATE_READER, STATE_TOC):
                        write_save(current_filepath, reader_scroll_y, current_font_size)
                    running = False
                    
            elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
                btn = event.cbutton.button
                if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                    dpad_up_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                    dpad_down_held = False
            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                btn = event.cbutton.button
                if btn == sdl2.SDL_CONTROLLER_BUTTON_START:
                    state_before_quit = state
                    state = STATE_QUIT_CONFIRM
                    
                if state == STATE_BROWSE:
                    list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                    list_items += [{"name": f, "is_dir": True} for f in folders]
                    list_items += [{"name": f, "is_dir": False} for f in files]
                    
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # Page Up
                        visible_items = 8
                        sel_index = max(0, sel_index - visible_items)
                        scroll_y = max(0, scroll_y - visible_items)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # Page Down
                        visible_items = 8
                        sel_index = min(len(list_items) - 1, sel_index + visible_items)
                        scroll_y = min(max(0, len(list_items) - visible_items), scroll_y + visible_items)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y - Theme Toggle
                        theme_idx = (theme_idx + 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Enter
                        if len(list_items) > 0:
                            item = list_items[sel_index]
                            if item["name"] == "..":
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                            elif item["is_dir"]:
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                            else:
                                filepath = os.path.join(current_path, item["name"])
                                if load_book(filepath):
                                    state = STATE_READER
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Back
                        if current_path != base_path:
                            current_path = os.path.dirname(current_path)
                            folders, files = get_directory_contents(current_path)
                            sel_index = 0
                            scroll_y = 0
                        
                elif state == STATE_READER:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        handle_reader_direction(0, -1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        handle_reader_direction(0, 1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        handle_reader_direction(-1, 0)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        handle_reader_direction(1, 0)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # L1: Prev Page
                        current_page_idx = max(0, current_page_idx - 1)
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # R1: Next Page
                        current_page_idx = min(len(book_pages) - 1, current_page_idx + 1)
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y: Zoom In
                        vw, vh = get_reader_view_size()
                        if img_w > 0 and img_h > 0:
                            min_zoom = min(vw / float(img_w), vh / float(img_h))
                            if zoom_level <= 0:
                                zoom_level = vw / float(img_w)
                            zoom_level = min(zoom_level * 1.2, min_zoom * 8.0)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B: Zoom Out
                        vw, vh = get_reader_view_size()
                        if img_w > 0 and img_h > 0:
                            min_zoom = min(vw / float(img_w), vh / float(img_h))
                            if zoom_level <= 0:
                                zoom_level = vw / float(img_w)
                            zoom_level = max(zoom_level / 1.2, min_zoom)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_Y: # Physical X: Rotate
                        reader_rotation_idx = (reader_rotation_idx + 1) % 4
                        write_reader_rotation_idx(reader_rotation_idx)
                        zoom_level = -1.0 # reset zoom
                        pan_x = 0
                        pan_y = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT: Exit
                        write_save(current_filepath, current_page_idx, current_font_size)
                        state = STATE_BROWSE
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Toggle HUD
                        show_hud = not show_hud
                        
                elif state == STATE_PAGE_SELECT:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP or btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        page_select_temp = min(len(book_pages) - 1, page_select_temp + 1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN or btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        page_select_temp = max(0, page_select_temp - 1)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                        page_select_temp = max(0, page_select_temp - 10)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                        page_select_temp = min(len(book_pages) - 1, page_select_temp + 10)
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Confirm
                        current_page_idx = page_select_temp
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                        state = STATE_READER
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B: Cancel
                        state = STATE_READER
                        
                elif state == STATE_TOC:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Select chapter
                        if len(chapter_offsets) > 0:
                            reader_scroll_y = chapter_offsets[toc_sel_index][1]
                        state = STATE_READER
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A or btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # Physical B or Select - Back to Reader
                        state = STATE_READER
                        
                elif state == STATE_QUIT_CONFIRM:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A (Confirm)
                        if state_before_quit in (STATE_READER, STATE_TOC):
                            write_save(current_filepath, current_page_idx, current_font_size)
                        running = False
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B (Cancel)
                        state = state_before_quit

        # Key repeat logic for library (exact Files app behavior)
        is_up = dpad_up_held or axis_up
        is_down = dpad_down_held or axis_down
        
        if state == STATE_BROWSE:
            list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
            list_items += [{"name": f, "is_dir": True} for f in folders]
            list_items += [{"name": f, "is_dir": False} for f in files]
            library_visible_items = 8
            
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(list_items) > 0:
                        if sel_index == 0:
                            sel_index = len(list_items) - 1
                            scroll_y = max(0, len(list_items) - library_visible_items)
                        else:
                            sel_index -= 1
                            if sel_index < scroll_y:
                                scroll_y = sel_index
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(list_items) > 0:
                        if sel_index == len(list_items) - 1:
                            sel_index = 0
                            scroll_y = 0
                        else:
                            sel_index += 1
                            if sel_index >= scroll_y + library_visible_items:
                                scroll_y = sel_index - library_visible_items + 1
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
        elif state == STATE_TOC:
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(chapter_offsets) > 0:
                        toc_sel_index = (toc_sel_index - 1) % len(chapter_offsets)
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    if len(chapter_offsets) > 0:
                        toc_sel_index = (toc_sel_index + 1) % len(chapter_offsets)
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
        elif state == STATE_PAGE_SELECT:
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    page_select_temp = min(len(book_pages) - 1, page_select_temp + 1)
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    page_select_temp = max(0, page_select_temp - 1)
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
        elif state != STATE_READER:
            dpad_up_held = False
            dpad_down_held = False
            dpad_timer = 0

        if needs_redraw:
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            render_state = state_before_quit if state == STATE_QUIT_CONFIRM else state

            if render_state == STATE_BROWSE:
                library_theme = LIBRARY_THEMES[theme_idx]
                renderer.clear(library_theme["bg"])
                renderer.fill((0, 0, SCREEN_W, 76), library_theme["header"])
                renderer.fill((0, 74, SCREEN_W, 2), library_theme["divider"])
                sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_BOLD)
                tex, tw, th = render_text("LIBRARY", font_large, library_theme["text"])
                sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_NORMAL)
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(32, 12, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                list_items += [{"name": f, "is_dir": True} for f in folders]
                list_items += [{"name": f, "is_dir": False} for f in files]

                library_visible_items = 8
                book_count = f"{len(files)} BOOK" + ("" if len(files) == 1 else "S")
                tex, tw, th = render_text(book_count, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, 27, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                start_idx = scroll_y
                end_idx = min(len(list_items), start_idx + library_visible_items)
                
                y_start = 86
                row_h = 74
                for i in range(start_idx, end_idx):
                    item = list_items[i]
                    iy = y_start + (i - start_idx) * row_h
                    
                    text_col = sdl2.SDL_Color(30, 30, 30, 255) if i == sel_index else library_theme["text"]
                    sec_col = sdl2.SDL_Color(80, 80, 80, 255) if i == sel_index else library_theme["secondary"]
                    
                    if i == sel_index:
                        sel_x, sel_y, sel_w, sel_h = 20, iy, SCREEN_W - 40, 68
                        renderer.fill((sel_x, sel_y, sel_w, sel_h), sdl2.ext.Color(102, 137, 181))
                        renderer.fill((sel_x + 2, sel_y + 2, sel_w - 4, sel_h - 4), sdl2.ext.Color(229, 235, 241))

                    if item["is_dir"]:
                        renderer.fill((42, iy + 18, 18, 14), library_theme["accent"])
                        renderer.fill((44, iy + 15, 9, 4), library_theme["accent"])
                        tex, tw, th = render_text(item["name"], font_ui_medium, text_col)
                        if tex:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 13, min(tw, SCREEN_W - 110), th))
                            sdl2.SDL_DestroyTexture(tex)
                    else:
                        title, author = get_book_display_metadata(item["name"])
                        icon_bg = sdl2.ext.Color(229, 235, 241) if i == sel_index else library_theme["bg"]
                        draw_book_icon(renderer, 42, iy + 16, library_theme["accent"], icon_bg)
                        sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_BOLD)
                        tex, tw, th = render_text(title, font_ui_medium, text_col)
                        sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_NORMAL)
                        if tex:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 4, min(tw, SCREEN_W - 110), th))
                            sdl2.SDL_DestroyTexture(tex)
                        if author:
                            tex, tw, th = render_text(author, font_small, sec_col)
                            if tex:
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(78, iy + 37, min(tw, SCREEN_W - 110), th))
                                sdl2.SDL_DestroyTexture(tex)
                        
                renderer.fill((0, SCREEN_H - 58, SCREEN_W, 1), library_theme["divider"])
                footer = "A: Open    B: Back    Y: Theme    [START] Exit"
                tex, tw, th = render_text(footer, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(32, SCREEN_H - 38, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            elif render_state == STATE_READER:
                reader_w, reader_h = get_reader_view_size()
                
                target = ensure_reader_target(reader_w, reader_h)
                sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, target)
                renderer.clear(theme["bg"])
                
                if book_pages and current_page_idx < len(book_pages):
                    if loaded_page_idx != current_page_idx:
                        if loaded_texture:
                            sdl2.SDL_DestroyTexture(loaded_texture)
                            loaded_texture = None
                            
                        # Load new image
                        try:
                            img_data = ComicArchive.read_image_data(current_filepath, book_pages[current_page_idx])
                            if img_data:
                                rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
                                surf = sdlimage.IMG_Load_RW(rw, 1)
                                if surf:
                                    img_w = surf.contents.w
                                    img_h = surf.contents.h
                                    loaded_texture = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                                    sdl2.SDL_FreeSurface(surf)
                        except Exception:
                            pass
                        loaded_page_idx = current_page_idx
                
                if loaded_texture:
                    if zoom_level <= 0:
                        zoom_level = reader_w / float(img_w) if img_w > 0 else 1.0
                        
                    scaled_w = int(img_w * zoom_level)
                    scaled_h = int(img_h * zoom_level)
                    
                    # Clamp pan
                    max_pan_x = max(0, scaled_w - reader_w)
                    max_pan_y = max(0, scaled_h - reader_h)
                    pan_x = max(0, min(pan_x, max_pan_x))
                    pan_y = max(0, min(pan_y, max_pan_y))
                    
                    # If image is smaller than screen, center it
                    draw_x = -pan_x
                    draw_y = -pan_y
                    if scaled_w < reader_w:
                        draw_x = (reader_w - scaled_w) // 2
                    if scaled_h < reader_h:
                        draw_y = (reader_h - scaled_h) // 2
                        
                    dst_rect = sdl2.SDL_Rect(draw_x, draw_y, scaled_w, scaled_h)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, loaded_texture, None, dst_rect)
                
                if show_hud:
                    # Top HUD
                    book_name = os.path.basename(current_filepath)
                    total_pages = len(book_pages)
                    hud_top = f"{book_name} - Page {current_page_idx + 1}/{total_pages}"
                    tex, tw, th = render_text(hud_top, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, 15, min(tw, reader_w-40), th))
                        sdl2.SDL_DestroyTexture(tex)
                    
                    # Bottom HUD
                    footer = f"L2/R2: Page Jump | L/R: Turn | Y: Zoom In | B: Zoom Out | X: Rotate | A: HUD | [SELECT] Exit"
                    tex, tw, th = render_text(footer, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, reader_h - 45, min(tw, reader_w-40), th))
                        sdl2.SDL_DestroyTexture(tex)

                drawing_rotated = (reader_rotation_idx != 0)
                if drawing_rotated:
                    reader_angle = 0
                    if reader_rotation_idx == 1: reader_angle = 270
                    elif reader_rotation_idx == 2: reader_angle = 180
                    elif reader_rotation_idx == 3: reader_angle = 90
                    
                    sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, None)
                    renderer.clear(theme["bg"])
                    src_rect = sdl2.SDL_Rect(0, 0, reader_w, reader_h)
                    dst_rect = sdl2.SDL_Rect((SCREEN_W - reader_w) // 2, (SCREEN_H - reader_h) // 2, reader_w, reader_h)
                    sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, target, src_rect, dst_rect, reader_angle, None, sdl2.SDL_FLIP_NONE)
                else:
                    sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, None)
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, target, None, None)
                    
            elif render_state == STATE_PAGE_SELECT:
                # First draw the reader state behind it (slightly dimmed or just as is)
                # But since we are in a single frame, we don't have the last frame. 
                # Let's just draw a simple overlay.
                # Actually, STATE_PAGE_SELECT is a separate state. We should redraw the reader background first.
                # To keep it simple, just clear screen and draw big popup.
                renderer.clear(theme["bg"])
                
                # Draw Box
                box_w = 400
                box_h = 200
                box_x = (SCREEN_W - box_w) // 2
                box_y = (SCREEN_H - box_h) // 2
                renderer.fill((box_x, box_y, box_w, box_h), theme["text"])
                renderer.fill((box_x+2, box_y+2, box_w-4, box_h-4), theme["bg"])
                
                title_str = "JUMP TO PAGE"
                tex, tw, th = render_text(title_str, font_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(box_x + (box_w - tw)//2, box_y + 30, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                    
                page_str = f"{page_select_temp + 1} / {len(book_pages)}"
                tex, tw, th = render_text(page_str, font_large, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(box_x + (box_w - tw)//2, box_y + 80, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                    
                hint_str = "A: Jump | B: Cancel"
                tex, tw, th = render_text(hint_str, font_small, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(box_x + (box_w - tw)//2, box_y + 150, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                    
            elif render_state == STATE_TOC:
                renderer.fill((0, 0, SCREEN_W, 60), theme["header"])
                tex, tw, th = render_text("TABLE OF CONTENTS", font_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W//2 - tw//2, 10, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                    
                start_idx = max(0, toc_sel_index - visible_items // 2)
                end_idx = min(len(chapter_offsets), start_idx + visible_items)
                
                y_start = 80
                for i in range(start_idx, end_idx):
                    ch_title, ch_line = chapter_offsets[i]
                    iy = y_start + (i - start_idx) * 40
                    
                    if i == toc_sel_index:
                        renderer.fill((0, iy, SCREEN_W, 40), theme["sel"])
                        
                    tex, tw, th = render_text(ch_title, font_small, theme["text"])
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(40, iy + 5, min(tw, SCREEN_W-80), th))
                        sdl2.SDL_DestroyTexture(tex)
                        
                footer = "A: Jump | B: Cancel"
                tex, tw, th = render_text(footer, font_small, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(20, SCREEN_H - 40, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            if state == STATE_QUIT_CONFIRM:
                sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
                sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 150)
                sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
                
                pop_w, pop_h = 600, 200
                pop_x, pop_y = (SCREEN_W - pop_w)//2, (SCREEN_H - pop_h)//2
                
                renderer.fill((pop_x, pop_y, pop_w, pop_h), theme["bg"])
                renderer.fill((pop_x+2, pop_y+2, pop_w-4, pop_h-4), theme["header"])
                
                msg = "Exit RetroComics?"
                tex, tw, th = render_text(msg, font_large, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 40, tw, th))
                    sdl2.SDL_DestroyTexture(tex)
                
                msg2 = "A: Confirm   B: Cancel"
                tex, tw, th = render_text(msg2, font_ui_medium, theme["text"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 130, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

            renderer.present()
            needs_redraw = False
            
        sdl2.SDL_Delay(16)

    if font_medium:
        sdlttf.TTF_CloseFont(font_medium)
    if loaded_texture:
        sdl2.SDL_DestroyTexture(loaded_texture)
    if reader_target:
        sdl2.SDL_DestroyTexture(reader_target)
    sdlttf.TTF_CloseFont(font_large)
    sdlttf.TTF_CloseFont(font_small)
    sdlttf.TTF_CloseFont(font_ui_medium)
    sdlttf.TTF_Quit()
    sdl2.SDL_Quit()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        with open("crash_python.log", "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
