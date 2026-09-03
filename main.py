import sys
import os
import textwrap
import traceback
import json
import re
import threading

from constants import (
    SCREEN_W, SCREEN_H,
    STATE_BROWSE, STATE_READER, STATE_TOC, STATE_QUIT_CONFIRM, STATE_PAGE_SELECT, STATE_ABOUT,
    VALID_EXTS, VALID_EXTS_SET,
    THEMES, LIBRARY_THEMES, natural_sort_key
)

from storage import (
    load_settings, write_settings,
    load_save, write_save,
    load_theme_idx, write_theme_idx,
    load_library_view, write_library_view,
    load_reader_rotation_idx, write_reader_rotation_idx
)

from comics import (
    BIN_DIR, SEVEN_Z_BIN, UNRAR_BIN,
    log_debug, bitmap_to_bmp, ComicArchive
)

from ui_dialogs import (
    draw_about_dialog,
    draw_quit_confirm_dialog,
    draw_toast_notification
)

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


def get_directory_contents(path):
    folders = []
    files = []
    valid_exts_set = {'.cbz', '.zip', '.cbr', '.rar', '.cb7', '.7z', '.cbt', '.tar', '.pdf'}
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.name.startswith('.'):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.name)
                    else:
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in valid_exts_set:
                            files.append(entry.name)
                except OSError:
                    pass
    except Exception:
        pass
    folders.sort(key=str.lower)
    files.sort(key=str.lower)
    return folders, files

def get_book_display_metadata(filename):
    """Derive library label from a filename without changing the real path."""
    stem = os.path.splitext(filename)[0]
    return stem.strip(), ""

def get_reading_header_metadata(filepath):
    """Extract clean (book_title, chapter) without author and without file extension."""
    filename = os.path.basename(filepath)
    stem = os.path.splitext(filename)[0]
    parent = os.path.basename(os.path.dirname(filepath))

    # Match chapter keywords: Chap, Chapter, Tập, Vol, Volume, Hồi...
    chap_match = re.search(r'\b(Chap(?:ter)?\.?\s*\d+|Vol(?:ume)?\.?\s*\d+|Tập\s*\d+|Hồi\s*\d+|Ch\.\s*\d+)\b', stem, re.IGNORECASE)

    parts = [p.strip() for p in stem.split(' - ') if p.strip()]

    if len(parts) >= 3:
        # e.g. "One Piece - Chap 1050 - Oda" or "Batman - Year One - Deluxe"
        return parts[0], parts[1]
    elif len(parts) == 2:
        if chap_match and chap_match.group(0) in parts[1]:
            return parts[0], parts[1]
        if parent and parent.lower() not in ['books', 'sdcard', '']:
            return parent, parts[0]
        return parts[0], ""

    if chap_match:
        chap_str = chap_match.group(0)
        title = stem.split(chap_str)[0].strip(' -_')
        if not title and parent and parent.lower() not in ['books', 'sdcard', '']:
            title = parent
        return (title if title else stem), chap_str

    return stem, ""

def draw_book_icon(renderer, x, y, color, background):
    """Comic/Manga page glyph: 16x20 with 3 comic panels (1 top wide panel, 2 bottom vertical panels)."""
    renderer.fill((x, y, 16, 20), color)
    renderer.fill((x + 1, y + 1, 14, 18), background)
    renderer.fill((x + 3, y + 3, 10, 5), color)
    renderer.fill((x + 3, y + 10, 4, 7), color)
    renderer.fill((x + 9, y + 10, 4, 7), color)



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
        
    font_large = sdlttf.TTF_OpenFont(font_path, 48)
    font_small = sdlttf.TTF_OpenFont(font_path, 24)
    font_ui_medium = sdlttf.TTF_OpenFont(font_path, 32)
    
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
    prev_sel_index = 0
    sel_time = 0
    marquee_active = False
    scroll_y = 0
    dpad_up_held = False
    dpad_down_held = False
    dpad_left_held = False
    dpad_right_held = False
    dpad_timer = 0
    dpad_horiz_timer = 0
    visible_items = 15
    theme_idx = load_theme_idx()
    reader_rotation_idx = load_reader_rotation_idx()
    library_view_mode = load_library_view() # "list" or "grid"
    cover_cache = {}  # filepath -> (SDL_Texture, w, h)

    # -----------------------------------------------------------------------
    # Fast Async Cover System: background thread + disk cache + downscaling
    # Cover cell on screen: 170x200 px. We store covers at 255x300 (1.5x for
    # crisp rendering) -- 3/4-quality downscale of the source.
    # -----------------------------------------------------------------------
    import threading, hashlib
    import queue as _queue_mod
    COVER_CACHE_DIR = "/mnt/SDCARD/.cover_cache"
    try:
        os.makedirs(COVER_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    def _cover_disk_path(fp):
        h = hashlib.sha1(fp.encode("utf-8", errors="replace")).hexdigest()[:16]
        return os.path.join(COVER_CACHE_DIR, h + ".bmp")

    def _decode_cover(img_data):
        """CPU-side: decode bytes -> SDL_Surface at full native resolution.
        No downscaling: GPU handles display scaling at render time for max sharpness."""
        rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
        src = sdlimage.IMG_Load_RW(rw, 1)
        if not src:
            return None, 0, 0
        sw, sh = src.contents.w, src.contents.h
        if sw <= 0 or sh <= 0:
            sdl2.SDL_FreeSurface(src)
            return None, 0, 0
        return src, sw, sh

    cover_pending        = set()              # guarded by _cover_q_lock
    _cover_q             = _queue_mod.Queue() # blocking FIFO for workers
    _cover_q_lock        = threading.Lock()   # guard cover_pending
    cover_ready          = {}                 # filepath -> (surf,w,h) or (None,0,0)
    cover_ready_lock     = threading.Lock()
    cover_thread_running = [True]

    def _cover_worker():
        while cover_thread_running[0]:
            try:
                filepath = _cover_q.get(timeout=0.5)
            except Exception:
                continue
            disk = _cover_disk_path(filepath)
            img_data = None
            if os.path.exists(disk):
                try:
                    with open(disk, "rb") as f:
                        img_data = f.read()
                except Exception:
                    img_data = None
            if not img_data:
                try:
                    pages = ComicArchive.get_pages(filepath)
                    if pages:
                        img_data = ComicArchive.read_image_data(filepath, pages[0])
                except Exception as e:
                    log_debug(f"cover worker error '{filepath}': {e}")
            if not img_data:
                with cover_ready_lock:
                    cover_ready[filepath] = (None, 0, 0)
                _cover_q.task_done()
                continue
            surf, dw, dh = _decode_cover(img_data)
            if surf and dw > 0:
                if not os.path.exists(disk):
                    try:
                        sdl2.SDL_SaveBMP(surf, disk.encode("utf-8"))
                    except Exception:
                        pass
                with cover_ready_lock:
                    cover_ready[filepath] = (surf, dw, dh)
            else:
                if surf:
                    sdl2.SDL_FreeSurface(surf)
                with cover_ready_lock:
                    cover_ready[filepath] = (None, 0, 0)
            _cover_q.task_done()

    # 3 parallel decode threads
    _cover_threads = []
    for _i in range(3):
        _t = threading.Thread(target=_cover_worker, daemon=True)
        _t.start()
        _cover_threads.append(_t)

    def pump_cover_ready():
        """Call once per frame: promote finished CPU surfaces -> GPU textures."""
        with cover_ready_lock:
            if not cover_ready:
                return
            batch = list(cover_ready.items())
            cover_ready.clear()
        for fp, result in batch:
            if len(result) == 3 and result[0] is not None:
                surf, dw, dh = result
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                cover_cache[fp] = (tex, dw, dh) if tex else (None, 0, 0)
            else:
                cover_cache[fp] = (None, 0, 0)

    def get_cover_texture(filepath):
        """Non-blocking: returns cached texture or queues background load."""
        if filepath in cover_cache:
            return cover_cache[filepath]
        with cover_ready_lock:
            already = filepath in cover_ready
        if not already:
            with _cover_q_lock:
                if filepath not in cover_pending:
                    cover_pending.add(filepath)
                    _cover_q.put_nowait(filepath)
        return (None, 0, 0)

    def prewarm_covers(item_list, path):
        """Pre-queue all file items immediately when entering a directory."""
        for item in item_list:
            if not item["is_dir"]:
                fp = os.path.join(path, item["name"])
                if fp not in cover_cache:
                    with cover_ready_lock:
                        already = fp in cover_ready
                    if not already:
                        with _cover_q_lock:
                            if fp not in cover_pending:
                                cover_pending.add(fp)
                                _cover_q.put_nowait(fp)

    def clear_cover_cache():
        with _cover_q_lock:
            cover_pending.clear()
        while not _cover_q.empty():
            try: _cover_q.get_nowait(); _cover_q.task_done()
            except Exception: break
        with cover_ready_lock:
            for result in cover_ready.values():
                if len(result) == 3 and result[0] is not None:
                    sdl2.SDL_FreeSurface(result[0])
            cover_ready.clear()
        for tex, _, _ in cover_cache.values():
            if tex:
                sdl2.SDL_DestroyTexture(tex)
        cover_cache.clear()

    
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

    COMIC_THUMB_CACHE_DIR = "/mnt/SDCARD/.comic_thumb_cache"
    try:
        os.makedirs(COMIC_THUMB_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    def _comic_thumb_disk_path(fp, p_idx):
        h = hashlib.sha1(f"{fp}:{p_idx}".encode("utf-8", errors="replace")).hexdigest()[:20]
        return os.path.join(COMIC_THUMB_CACHE_DIR, f"{h}.bmp")

    comic_thumb_cache = {}          # (filepath, page_idx) -> {"tex": tex, "w": w, "h": h, "last_used": cur_t}
    _comic_thumb_q = _queue_mod.PriorityQueue()
    _comic_thumb_ready = _queue_mod.Queue()
    _comic_thumb_pending = set()
    _comic_thumb_pending_lock = threading.Lock()
    _comic_seq = 0
    _comic_seq_lock = threading.Lock()
    comic_workers_running = [True]

    def _comic_thumb_worker():
        while comic_workers_running[0]:
            try:
                item = _comic_thumb_q.get(timeout=0.5)
            except Exception:
                continue
            if item is None:
                _comic_thumb_q.task_done()
                break
            try:
                prio, seq, fp, p_idx, p_name = item

                disk = _comic_thumb_disk_path(fp, p_idx)
                surf = None
                dw, dh = 0, 0

                # 1. Check disk cache first (1-2ms)
                if os.path.exists(disk):
                    try:
                        surf = sdlimage.IMG_Load(disk.encode("utf-8"))
                        if surf:
                            dw = surf.contents.w
                            dh = surf.contents.h
                            if dw <= 0 or dh <= 0:
                                sdl2.SDL_FreeSurface(surf)
                                surf = None
                    except Exception:
                        surf = None

                # 2. If not on disk, decode and render thumbnail
                if not surf and p_name:
                    try:
                        img_data = ComicArchive.read_image_data(fp, p_name, is_thumb=True)
                        if img_data:
                            rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
                            orig_surf = sdlimage.IMG_Load_RW(rw, 1)
                            if orig_surf:
                                ow = orig_surf.contents.w
                                oh = orig_surf.contents.h
                                scale = min(264.0 / max(1, ow), 372.0 / max(1, oh))
                                if scale < 1.0:
                                    tw = max(1, int(ow * scale))
                                    th = max(1, int(oh * scale))
                                    small_surf = sdl2.SDL_CreateRGBSurfaceWithFormat(0, tw, th, 32, sdl2.SDL_PIXELFORMAT_RGBA8888)
                                    if small_surf:
                                        sdl2.SDL_BlitScaled(orig_surf, None, small_surf, None)
                                        surf = small_surf
                                        dw, dh = tw, th
                                    else:
                                        surf = orig_surf
                                        dw, dh = ow, oh
                                    if small_surf:
                                        sdl2.SDL_FreeSurface(orig_surf)
                                else:
                                    surf = orig_surf
                                    dw, dh = ow, oh

                                if surf and not os.path.exists(disk):
                                    try:
                                        sdl2.SDL_SaveBMP(surf, disk.encode("utf-8"))
                                    except Exception:
                                        pass
                    except Exception as e:
                        log_debug(f"comic_thumb worker error: {e}")

                with _comic_thumb_pending_lock:
                    _comic_thumb_pending.discard((fp, p_idx))

                if surf and dw > 0 and dh > 0:
                    _comic_thumb_ready.put((fp, p_idx, surf, dw, dh))
            except Exception as e:
                log_debug(f"worker exception: {e}")
            finally:
                _comic_thumb_q.task_done()

    _comic_thumb_threads = []
    for _i in range(2):
        _t = threading.Thread(target=_comic_thumb_worker, daemon=True)
        _t.start()
        _comic_thumb_threads.append(_t)

    def cancel_pending_comic_thumbs():
        with _comic_thumb_pending_lock:
            _comic_thumb_pending.clear()
        while not _comic_thumb_q.empty():
            try:
                _comic_thumb_q.get_nowait()
                _comic_thumb_q.task_done()
            except Exception:
                break

    def queue_comic_thumbnail(fp, p_idx, priority=0):
        nonlocal _comic_seq
        if not book_pages or p_idx < 0 or p_idx >= len(book_pages):
            return
        cache_key = (fp, p_idx)
        if cache_key in comic_thumb_cache:
            return
        with _comic_thumb_pending_lock:
            if cache_key in _comic_thumb_pending:
                return
            _comic_thumb_pending.add(cache_key)
        with _comic_seq_lock:
            _comic_seq += 1
            seq = _comic_seq
        p_name = book_pages[p_idx]
        _comic_thumb_q.put((priority, seq, fp, p_idx, p_name))

    def pump_comic_thumb_ready():
        nonlocal comic_thumb_cache, needs_redraw
        cur_t = sdl2.SDL_GetTicks()
        promoted = 0
        while not _comic_thumb_ready.empty():
            try:
                fp, p_idx, surf, dw, dh = _comic_thumb_ready.get_nowait()
            except Exception:
                break
            try:
                cache_key = (fp, p_idx)
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                if tex:
                    if len(comic_thumb_cache) >= 80:
                        current_screen_start = (page_select_temp // 10) * 10
                        keep_range = set(range(max(0, current_screen_start - 10), min(len(book_pages), current_screen_start + 50)))
                        candidates = [k for k in comic_thumb_cache.keys() if k[1] not in keep_range]
                        if not candidates:
                            candidates = list(comic_thumb_cache.keys())
                        if candidates:
                            oldest_key = min(candidates, key=lambda k: comic_thumb_cache[k].get("last_used", 0))
                            try:
                                sdl2.SDL_DestroyTexture(comic_thumb_cache[oldest_key]["tex"])
                            except Exception:
                                pass
                            del comic_thumb_cache[oldest_key]

                    comic_thumb_cache[cache_key] = {"tex": tex, "w": dw, "h": dh, "last_used": cur_t}
                    needs_redraw = True
                    promoted += 1
            except Exception as e:
                pass
        return promoted

    def clear_comic_thumb_cache():
        nonlocal comic_thumb_cache
        cancel_pending_comic_thumbs()
        for k in list(comic_thumb_cache.keys()):
            try:
                sdl2.SDL_DestroyTexture(comic_thumb_cache[k]["tex"])
            except Exception:
                pass
        comic_thumb_cache.clear()

    def get_comic_thumbnail(filepath, page_idx):
        nonlocal comic_thumb_cache
        if not book_pages or page_idx < 0 or page_idx >= len(book_pages):
            return None
        cache_key = (filepath, page_idx)
        if cache_key in comic_thumb_cache:
            comic_thumb_cache[cache_key]["last_used"] = sdl2.SDL_GetTicks()
            return comic_thumb_cache[cache_key]
        queue_comic_thumbnail(filepath, page_idx, priority=0)
        return None

    def load_book(filepath):
        nonlocal book_pages, current_page_idx, pan_x, pan_y, zoom_level, current_font_size, current_filepath, loaded_page_idx, loaded_texture
        book_pages = []
        loaded_page_idx = -1
        clear_comic_thumb_cache()
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
    last_right_axis_time = 0
    right_axis_held = False
    last_left_axis_time = 0
    left_axis_held = False
    show_hud = True
    
    while running:
        events = sdl2.ext.get_events()
        if len(events) > 0:
            needs_redraw = True
            
        current_ticks = sdl2.SDL_GetTicks()
        axis_up = False
        axis_down = False
        axis_left = False
        axis_right = False
        for c in controllers:
            lx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
            ly = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
            rx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
            ry = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTY)
            ax = lx if abs(lx) >= abs(rx) else rx
            ay = ly if abs(ly) >= abs(ry) else ry
            if ay < -15000:
                axis_up = True
            elif ay > 15000:
                axis_down = True
            if ax < -15000:
                axis_left = True
            elif ax > 15000:
                axis_right = True

            # Right Stick dedicated controls for Comic Reader & Page Select
            if abs(rx) < 10000 and abs(ry) < 10000:
                right_axis_held = False
            elif state in (STATE_READER, STATE_PAGE_SELECT):
                if not right_axis_held or (current_ticks - last_right_axis_time > 100):
                    if abs(rx) >= 15000 and abs(rx) > abs(ry):
                        if state == STATE_READER:
                            if rx > 0: # Right -> Next Page (like R1)
                                if book_pages and current_page_idx < len(book_pages) - 1:
                                    current_page_idx += 1
                                    zoom_level = -1.0
                                    pan_x = 0
                                    pan_y = 0
                                    needs_redraw = True
                            else: # Left -> Prev Page (like L1)
                                if current_page_idx > 0:
                                    current_page_idx -= 1
                                    zoom_level = -1.0
                                    pan_x = 0
                                    pan_y = 0
                                    needs_redraw = True
                        elif state == STATE_PAGE_SELECT:
                            total_p = len(book_pages) if book_pages else 1
                            if rx > 0: # Right -> +1
                                page_select_temp = min(total_p - 1, page_select_temp + 1)
                                needs_redraw = True
                            else: # Left -> -1
                                page_select_temp = max(0, page_select_temp - 1)
                                needs_redraw = True
                        right_axis_held = True
                        last_right_axis_time = current_ticks
                        break
                    elif abs(ry) >= 15000 and abs(ry) >= abs(rx):
                        if state == STATE_READER:
                            state = STATE_PAGE_SELECT
                            page_select_temp = current_page_idx
                            needs_redraw = True
                        elif state == STATE_PAGE_SELECT:
                            total_p = len(book_pages) if book_pages else 1
                            if ry < 0: # Up -> Row Up (-5)
                                page_select_temp = max(0, page_select_temp - 5)
                                needs_redraw = True
                            else: # Down -> Row Down (+5)
                                page_select_temp = min(total_p - 1, page_select_temp + 5)
                                needs_redraw = True
                        right_axis_held = True
                        last_right_axis_time = current_ticks
                        break

            # Left Stick controls pan in Comic Reader, or adjust page in Page Select
            if abs(lx) < 10000 and abs(ly) < 10000:
                left_axis_held = False
            if state == STATE_READER and (current_ticks - last_axis_scroll > 100):
                if abs(lx) >= 15000 or abs(ly) >= 15000:
                    if abs(lx) > abs(ly):
                        handle_reader_direction(1 if lx > 0 else -1, 0)
                    else:
                        handle_reader_direction(0, 1 if ly > 0 else -1)
                    last_axis_scroll = current_ticks
                    needs_redraw = True
                    break
            elif state == STATE_PAGE_SELECT:
                total_p = len(book_pages) if book_pages else 1
                if not left_axis_held or (current_ticks - last_left_axis_time > 100):
                    if abs(ly) >= 15000 and abs(ly) >= abs(lx):
                        if ly < 0: # Up -> Row Up (-5)
                            page_select_temp = max(0, page_select_temp - 5)
                            needs_redraw = True
                        else: # Down -> Row Down (+5)
                            page_select_temp = min(total_p - 1, page_select_temp + 5)
                            needs_redraw = True
                        left_axis_held = True
                        last_left_axis_time = current_ticks
                        break
                    elif abs(lx) >= 15000 and abs(lx) > abs(ly):
                        if lx > 0: # Right -> +1
                            page_select_temp = min(total_p - 1, page_select_temp + 1)
                            needs_redraw = True
                        else: # Left -> -1
                            page_select_temp = max(0, page_select_temp - 1)
                            needs_redraw = True
                        left_axis_held = True
                        last_left_axis_time = current_ticks
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
                            needs_redraw = True
                        elif val < 8000:
                            l2_pressed = False
                    elif event.caxis.axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                        val = event.caxis.value
                        if val > 16000 and not r2_pressed:
                            r2_pressed = True
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
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                    dpad_left_held = False
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                    dpad_right_held = False
            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                btn = event.cbutton.button
                if state == STATE_QUIT_CONFIRM:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A (Confirm)
                        if state_before_quit in (STATE_READER, STATE_TOC):
                            write_save(current_filepath, current_page_idx, current_font_size)
                        running = False
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B (Cancel)
                        state = state_before_quit
                elif btn == sdl2.SDL_CONTROLLER_BUTTON_START:
                    state_before_quit = state
                    state = STATE_QUIT_CONFIRM
                    
                elif state == STATE_BROWSE:
                    list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
                    list_items += [{"name": f, "is_dir": True} for f in folders]
                    list_items += [{"name": f, "is_dir": False} for f in files]
                    
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        dpad_up_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        dpad_down_held = True
                        dpad_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        dpad_left_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        dpad_right_held = True
                        dpad_horiz_timer = 0
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # L: Prev Theme
                        theme_idx = (theme_idx - 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # R: Next Theme
                        theme_idx = (theme_idx + 1) % len(THEMES)
                        write_theme_idx(theme_idx)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A - Enter
                        if len(list_items) > 0:
                            item = list_items[sel_index]
                            if item["name"] == "..":
                                clear_cover_cache()
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                _li_pw = ([{"name":"..","is_dir":True}] if current_path != base_path else []) + [{"name":f,"is_dir":True} for f in folders] + [{"name":f,"is_dir":False} for f in files]
                                prewarm_covers(_li_pw, current_path)
                                needs_redraw = True
                            elif item["is_dir"]:
                                clear_cover_cache()
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                _li_pw = ([{"name":"..","is_dir":True}] if current_path != base_path else []) + [{"name":f,"is_dir":True} for f in folders] + [{"name":f,"is_dir":False} for f in files]
                                prewarm_covers(_li_pw, current_path)
                                needs_redraw = True
                            else:
                                filepath = os.path.join(current_path, item["name"])
                                if load_book(filepath):
                                    state = STATE_READER
                                    needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B - Toggle View Mode
                        library_view_mode = "grid" if library_view_mode == "list" else "list"
                        write_library_view(library_view_mode)
                        if library_view_mode == "grid":
                            scroll_y = (sel_index // 8) * 8
                        else:
                            if sel_index >= scroll_y + 8:
                                scroll_y = max(0, sel_index - 7)
                            elif sel_index < scroll_y:
                                scroll_y = sel_index
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT - Author Info
                        state = STATE_ABOUT
                        needs_redraw = True

                elif state == STATE_ABOUT:
                    if btn in (sdl2.SDL_CONTROLLER_BUTTON_A, sdl2.SDL_CONTROLLER_BUTTON_B, sdl2.SDL_CONTROLLER_BUTTON_BACK):
                        state = STATE_BROWSE
                        needs_redraw = True

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
                            fit_page = min(vw / float(img_w), vh / float(img_h))
                            if zoom_level <= 0:
                                zoom_level = vw / float(img_w)
                            zoom_level = min(zoom_level * 1.25, fit_page * 8.0)
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B: Zoom Out (until fit 2 edges)
                        vw, vh = get_reader_view_size()
                        if img_w > 0 and img_h > 0:
                            fit_page = min(vw / float(img_w), vh / float(img_h))
                            if zoom_level <= 0:
                                zoom_level = vw / float(img_w)
                            zoom_level = max(zoom_level / 1.25, fit_page)
                            scaled_w = int(img_w * zoom_level)
                            scaled_h = int(img_h * zoom_level)
                            max_pan_x = max(0, scaled_w - vw)
                            max_pan_y = max(0, scaled_h - vh)
                            pan_x = max(0, min(pan_x, max_pan_x))
                            pan_y = max(0, min(pan_y, max_pan_y))
                            needs_redraw = True
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
                    total_p = len(book_pages) if book_pages else 1
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Confirm
                        current_page_idx = page_select_temp
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                        state = STATE_READER
                        cancel_pending_comic_thumbs()
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B: Cancel
                        state = STATE_READER
                        cancel_pending_comic_thumbs()
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT: Return to Library
                        write_save(current_filepath, current_page_idx, current_font_size)
                        ComicArchive.close_active()
                        clear_comic_thumb_cache()
                        state = STATE_BROWSE
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:
                        page_select_temp = max(0, page_select_temp - 1)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:
                        page_select_temp = min(total_p - 1, page_select_temp + 1)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:
                        page_select_temp = max(0, page_select_temp - 5)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                        page_select_temp = min(total_p - 1, page_select_temp + 5)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y: Snap to Current Reading Page
                        page_select_temp = current_page_idx
                        needs_redraw = True
                        
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

        # Key repeat logic for library (exact Files app behavior)
        if state == STATE_BROWSE:
            is_up = dpad_up_held or axis_up
            is_down = dpad_down_held or axis_down
            is_left = dpad_left_held or axis_left
            is_right = dpad_right_held or axis_right
        else:
            is_up = dpad_up_held
            is_down = dpad_down_held
            is_left = dpad_left_held
            is_right = dpad_right_held
        
        if state == STATE_BROWSE:
            list_items = [{"name": "..", "is_dir": True}] if current_path != base_path else []
            list_items += [{"name": f, "is_dir": True} for f in folders]
            list_items += [{"name": f, "is_dir": False} for f in files]
            library_visible_items = 8
            
            if library_view_mode == "grid":
                grid_cols = 4
                if is_up:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(list_items) > 0:
                            if sel_index >= grid_cols:
                                sel_index -= grid_cols
                            else:
                                sel_index = 0
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_timer += 1
                elif is_down:
                    if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                        if len(list_items) > 0:
                            if sel_index + grid_cols < len(list_items):
                                sel_index += grid_cols
                            else:
                                sel_index = len(list_items) - 1
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_timer += 1
                else:
                    dpad_timer = 0

                if is_left:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(list_items) > 0:
                            sel_index = max(0, sel_index - 1)
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif is_right:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        if len(list_items) > 0:
                            sel_index = min(len(list_items) - 1, sel_index + 1)
                            scroll_y = (sel_index // 8) * 8
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0
            else:
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

                if is_left:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        sel_index = max(0, sel_index - library_visible_items)
                        scroll_y = max(0, scroll_y - library_visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                elif is_right:
                    if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 4 == 0):
                        sel_index = min(len(list_items) - 1, sel_index + library_visible_items)
                        scroll_y = min(max(0, len(list_items) - library_visible_items), scroll_y + library_visible_items)
                        needs_redraw = True
                    dpad_horiz_timer += 1
                else:
                    dpad_horiz_timer = 0

            if prev_sel_index != sel_index:
                sel_time = current_ticks
                prev_sel_index = sel_index

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
            total_p = len(book_pages) if book_pages else 1
            if is_up:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    page_select_temp = max(0, page_select_temp - 5)
                    needs_redraw = True
                dpad_timer += 1
            elif is_down:
                if dpad_timer == 0 or (dpad_timer > 15 and dpad_timer % 3 == 0):
                    page_select_temp = min(total_p - 1, page_select_temp + 5)
                    needs_redraw = True
                dpad_timer += 1
            else:
                dpad_timer = 0
            if is_left:
                if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 3 == 0):
                    page_select_temp = max(0, page_select_temp - 1)
                    needs_redraw = True
                dpad_horiz_timer += 1
            elif is_right:
                if dpad_horiz_timer == 0 or (dpad_horiz_timer > 15 and dpad_horiz_timer % 3 == 0):
                    page_select_temp = min(total_p - 1, page_select_temp + 1)
                    needs_redraw = True
                dpad_horiz_timer += 1
            else:
                dpad_horiz_timer = 0
        elif state != STATE_READER:
            dpad_up_held = False
            dpad_down_held = False
            dpad_left_held = False
            dpad_right_held = False
            dpad_timer = 0
            dpad_horiz_timer = 0

        pump_cover_ready()  # promote background-loaded covers to GPU textures
        pump_comic_thumb_ready()  # promote background-loaded thumbnails to GPU textures
        if needs_redraw:
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            if state in (STATE_QUIT_CONFIRM, STATE_ABOUT):
                render_state = state_before_quit if state == STATE_QUIT_CONFIRM else STATE_BROWSE
            else:
                render_state = state

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

                mode_str = "[GRID]" if library_view_mode == "grid" else "[LIST]"
                book_count = f"{len(files)} BOOK" + ("" if len(files) == 1 else "S") + f"    {mode_str}"
                tex, tw, th = render_text(book_count, font_small, library_theme["secondary"])
                if tex:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, 27, tw, th))
                    sdl2.SDL_DestroyTexture(tex)

                sel_border = library_theme.get("sel_border", sdl2.ext.Color(102, 137, 181))
                sel_bg = library_theme.get("sel_bg", sdl2.ext.Color(229, 235, 241))
                sel_text = library_theme.get("sel_text", sdl2.SDL_Color(30, 30, 30, 255))
                sel_sec = library_theme.get("sel_sec", sdl2.SDL_Color(80, 80, 80, 255))
                marquee_active = False

                if library_view_mode == "grid":
                    grid_page = sel_index // 8
                    start_idx = grid_page * 8
                    end_idx = min(len(list_items), start_idx + 8)

                    col_w = 232
                    row_h = 286
                    start_x = 24
                    start_y = 96
                    gap_x = 16
                    gap_y = 16

                    for idx in range(start_idx, end_idx):
                        rel_i = idx - start_idx
                        col = rel_i % 4
                        row = rel_i // 4
                        cx = start_x + col * (col_w + gap_x)
                        cy = start_y + row * (row_h + gap_y)

                        item = list_items[idx]
                        is_sel = (idx == sel_index)

                        if is_sel:
                            renderer.fill((cx, cy, col_w, row_h), sel_border)
                            renderer.fill((cx + 2, cy + 2, col_w - 4, row_h - 4), sel_bg)
                            card_text_col = sel_text
                        else:
                            renderer.fill((cx, cy, col_w, row_h), library_theme["divider"])
                            renderer.fill((cx + 1, cy + 1, col_w - 2, row_h - 2), library_theme["header"])
                            card_text_col = library_theme["text"]

                        cover_w, cover_h = 170, 200
                        cover_x = cx + (col_w - cover_w) // 2
                        cover_y = cy + 14

                        if item["is_dir"]:
                            renderer.fill((cover_x, cover_y, cover_w, cover_h), library_theme["bg"])
                            if item["name"] == "..":
                                renderer.fill((cover_x + 50, cover_y + 80, 70, 40), library_theme["accent"])
                                renderer.fill((cover_x + 52, cover_y + 82, 66, 36), library_theme["bg"])
                                t_back, bw, bh = render_text("BACK", font_small, library_theme["accent"])
                                if t_back:
                                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_back, None, sdl2.SDL_Rect(cover_x + (cover_w - bw) // 2, cover_y + 90, bw, bh))
                                    sdl2.SDL_DestroyTexture(t_back)
                            else:
                                fx = cover_x + (cover_w - 90) // 2
                                fy = cover_y + 60
                                renderer.fill((fx, fy - 12, 45, 14), library_theme["accent"])
                                renderer.fill((fx, fy, 90, 65), library_theme["accent"])
                                renderer.fill((fx + 3, fy + 3, 84, 59), library_theme["bg"])
                                t_dir, dw, dh = render_text("DIR", font_small, library_theme["accent"])
                                if t_dir:
                                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_dir, None, sdl2.SDL_Rect(cover_x + (cover_w - dw) // 2, fy + 20, dw, dh))
                                    sdl2.SDL_DestroyTexture(t_dir)
                        else:
                            filepath = os.path.join(current_path, item["name"])
                            c_tex, orig_w, orig_h = get_cover_texture(filepath)
                            if c_tex and orig_w > 0 and orig_h > 0:
                                scale = min(cover_w / float(orig_w), cover_h / float(orig_h))
                                dw = int(orig_w * scale)
                                dh = int(orig_h * scale)
                                tx = cover_x + (cover_w - dw) // 2
                                ty = cover_y + (cover_h - dh) // 2
                                renderer.fill((tx - 1, ty - 1, dw + 2, dh + 2), library_theme["divider"])
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, c_tex, None, sdl2.SDL_Rect(tx, ty, dw, dh))
                            else:
                                renderer.fill((cover_x, cover_y, cover_w, cover_h), library_theme["bg"])
                                renderer.fill((cover_x + 2, cover_y + 2, cover_w - 4, cover_h - 4), library_theme["header"])
                                draw_book_icon(renderer, cover_x + (cover_w - 16) // 2, cover_y + (cover_h - 20) // 2, library_theme["accent"], library_theme["bg"])

                        title, _ = get_book_display_metadata(item["name"]) if not item["is_dir"] else (item["name"], "")
                        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_BOLD if is_sel else sdlttf.TTF_STYLE_NORMAL)
                        tex_title, tw, th = render_text(title, font_small, card_text_col)
                        sdlttf.TTF_SetFontStyle(font_small, sdlttf.TTF_STYLE_NORMAL)
                        if tex_title:
                            title_y = cy + 236
                            max_title_w = col_w - 16
                            if tw > max_title_w and is_sel:
                                marquee_active = True
                                overflow = tw - max_title_w
                                dt = current_ticks - sel_time
                                pause_start = 1200
                                speed = 0.04
                                scroll_time = int(overflow / speed)
                                pause_end = 1200
                                total_cycle = pause_start + scroll_time + pause_end + scroll_time
                                cycle_pos = dt % total_cycle
                                if cycle_pos < pause_start:
                                    offset = 0
                                elif cycle_pos < pause_start + scroll_time:
                                    offset = int((cycle_pos - pause_start) * speed)
                                elif cycle_pos < pause_start + scroll_time + pause_end:
                                    offset = overflow
                                else:
                                    back_t = cycle_pos - (pause_start + scroll_time + pause_end)
                                    offset = overflow - int(back_t * speed)
                                offset = max(0, min(overflow, offset))
                                src = sdl2.SDL_Rect(offset, 0, max_title_w, th)
                                dst = sdl2.SDL_Rect(cx + 8, title_y, max_title_w, th)
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, src, dst)
                            else:
                                dw = min(tw, max_title_w)
                                tx = cx + (col_w - dw) // 2
                                src = sdl2.SDL_Rect(0, 0, dw, th)
                                dst = sdl2.SDL_Rect(tx, title_y, dw, th)
                                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, src, dst)
                            sdl2.SDL_DestroyTexture(tex_title)
                else:
                    library_visible_items = 8
                    start_idx = scroll_y
                    end_idx = min(len(list_items), start_idx + library_visible_items)

                    def draw_label(tex, tw, th, y_pos, is_sel):
                        nonlocal marquee_active
                        max_w = SCREEN_W - 110
                        overflow = tw - max_w
                        if overflow > 0 and is_sel:
                            marquee_active = True
                            dt = current_ticks - sel_time
                            pause_start = 1200
                            speed = 0.04
                            scroll_time = int(overflow / speed)
                            pause_end = 1200
                            total_cycle = pause_start + scroll_time + pause_end + scroll_time
                            cycle_pos = dt % total_cycle
                            if cycle_pos < pause_start:
                                offset = 0
                            elif cycle_pos < pause_start + scroll_time:
                                offset = int((cycle_pos - pause_start) * speed)
                            elif cycle_pos < pause_start + scroll_time + pause_end:
                                offset = overflow
                            else:
                                back_t = cycle_pos - (pause_start + scroll_time + pause_end)
                                offset = overflow - int(back_t * speed)
                            offset = max(0, min(overflow, offset))
                            src = sdl2.SDL_Rect(offset, 0, max_w, th)
                            dst = sdl2.SDL_Rect(78, y_pos, max_w, th)
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, src, dst)
                        else:
                            draw_w = min(tw, max_w)
                            src = sdl2.SDL_Rect(0, 0, draw_w, th)
                            dst = sdl2.SDL_Rect(78, y_pos, draw_w, th)
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, src, dst)

                    y_start = 86
                    row_h = 74
                    for i in range(start_idx, end_idx):
                        item = list_items[i]
                        iy = y_start + (i - start_idx) * row_h
                        
                        text_col = sel_text if i == sel_index else library_theme["text"]
                        
                        if i == sel_index:
                            sel_x, sel_y, sel_w, sel_h = 20, iy, SCREEN_W - 40, 68
                            renderer.fill((sel_x, sel_y, sel_w, sel_h), sel_border)
                            renderer.fill((sel_x + 2, sel_y + 2, sel_w - 4, sel_h - 4), sel_bg)

                        if item["is_dir"]:
                            renderer.fill((44, iy + 21, 9, 4), library_theme["accent"])
                            renderer.fill((42, iy + 24, 18, 14), library_theme["accent"])
                            tex, tw, th = render_text(item["name"], font_ui_medium, text_col)
                            if tex:
                                title_y = iy + 16
                                draw_label(tex, tw, th, title_y, i == sel_index)
                                sdl2.SDL_DestroyTexture(tex)
                        else:
                            title, _ = get_book_display_metadata(item["name"])
                            icon_bg = sel_bg if i == sel_index else library_theme["bg"]
                            draw_book_icon(renderer, 42, iy + 23, library_theme["accent"], icon_bg)
                            sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_BOLD)
                            tex, tw, th = render_text(title, font_ui_medium, text_col)
                            sdlttf.TTF_SetFontStyle(font_ui_medium, sdlttf.TTF_STYLE_NORMAL)
                            if tex:
                                title_y = iy + 16
                                draw_label(tex, tw, th, title_y, i == sel_index)
                                sdl2.SDL_DestroyTexture(tex)

                renderer.fill((0, SCREEN_H - 58, SCREEN_W, 1), library_theme["divider"])
                footer = f"A: Open   B: {'List' if library_view_mode == 'grid' else 'Grid'}   L/R: Theme   SELECT: Info   [START] Exit"
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
                        pan_x = 0
                        pan_y = 0
                
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
                    # Fixed high-contrast dark glassmorphic Top Header Bar (100% visible on both white and black pages)
                    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
                    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 15, 15, 18, 215)
                    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, reader_w, 52))
                    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 255, 255, 255, 35)
                    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 51, reader_w, 1))

                    # Top HUD: Title - Page
                    book_title, _ = get_book_display_metadata(os.path.basename(current_filepath))
                    total_pages = len(book_pages)
                    hud_top = f"{book_title}  •  Page {current_page_idx + 1}/{total_pages}"
                    hud_text_color = sdl2.ext.Color(255, 255, 255)
                    tex, tw, th = render_text(hud_top, font_small, hud_text_color)
                    if tex:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(24, (52 - th) // 2, min(tw, reader_w - 48), th))
                        sdl2.SDL_DestroyTexture(tex)
                    
                    # Fixed high-contrast dark glassmorphic Bottom Footer Bar
                    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 15, 15, 18, 215)
                    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, reader_h - 48, reader_w, 48))
                    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 255, 255, 255, 35)
                    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, reader_h - 48, reader_w, 1))

                    # Bottom HUD Text
                    footer = f"L2: Page Select  |  L1/R1: Prev/Next  |  Y: Zoom In  |  B: Zoom Out  |  X: Rotate  |  A: HUD  |  SELECT: LIB"
                    tex_bot, bw, bh = render_text(footer, font_small, hud_text_color)
                    if tex_bot:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_bot, None, sdl2.SDL_Rect(24, reader_h - 48 + (48 - bh) // 2, min(bw, reader_w - 48), bh))
                        sdl2.SDL_DestroyTexture(tex_bot)

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
                lib_t = LIBRARY_THEMES[theme_idx]
                renderer.fill((0, 0, SCREEN_W, SCREEN_H), lib_t["bg"])
                
                # Top Header Bar
                renderer.fill((0, 0, SCREEN_W, 60), lib_t["header"])
                renderer.fill((0, 59, SCREEN_W, 1), lib_t["divider"])
                
                tex_title, tw, th = render_text("CONTENTS", font_medium, lib_t["accent"])
                if tex_title:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_title, None, sdl2.SDL_Rect(32, (60 - th) // 2, tw, th))
                    sdl2.SDL_DestroyTexture(tex_title)
                    
                total_p = len(book_pages) if book_pages else 1
                curr_info = f"Page {page_select_temp + 1} / {total_p}"
                tex_info, iw, ih = render_text(curr_info, font_small, lib_t["secondary"])
                if tex_info:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_info, None, sdl2.SDL_Rect(SCREEN_W - iw - 32, (60 - ih) // 2, iw, ih))
                    sdl2.SDL_DestroyTexture(tex_info)
                    
                # 2 Rows x 5 Columns Grid (10 Pages per screen)
                start_page = (page_select_temp // 10) * 10
                end_page = min(total_p, start_page + 10)
                
                thumb_w = 176
                thumb_h = 248
                col_gap = 20
                margin_x = 32
                
                for p_idx in range(start_page, end_page):
                    rel_idx = p_idx - start_page
                    col = rel_idx % 5
                    row = rel_idx // 5
                    
                    cell_x = margin_x + col * (thumb_w + col_gap)
                    cell_y = 78 if row == 0 else 380
                    
                    is_sel = (p_idx == page_select_temp)
                    is_reading = (p_idx == current_page_idx)
                    
                    # Background card
                    renderer.fill((cell_x, cell_y, thumb_w, thumb_h), lib_t["header"])
                    
                    # Thumbnail Image (Aspect-Ratio Fitted)
                    thumb_info = get_comic_thumbnail(current_filepath, p_idx)
                    if thumb_info:
                        tex_thumb = thumb_info["tex"]
                        img_w_t, img_h_t = thumb_info["w"], thumb_info["h"]
                        scale = min(float(thumb_w) / max(1, img_w_t), float(thumb_h) / max(1, img_h_t))
                        dw = max(1, int(img_w_t * scale))
                        dh = max(1, int(img_h_t * scale))
                        dx = cell_x + (thumb_w - dw) // 2
                        dy = cell_y + (thumb_h - dh) // 2
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_thumb, None, sdl2.SDL_Rect(dx, dy, dw, dh))
                    else:
                        tex_ph, pw, ph = render_text(f"P. {p_idx + 1}", font_small, lib_t["secondary"])
                        if tex_ph:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_ph, None, sdl2.SDL_Rect(cell_x + (thumb_w - pw)//2, cell_y + (thumb_h - ph)//2, pw, ph))
                            sdl2.SDL_DestroyTexture(tex_ph)
                            
                    # Selection highlight border (3px thick)
                    if is_sel:
                        renderer.fill((cell_x - 3, cell_y - 3, thumb_w + 6, 3), lib_t["accent"])
                        renderer.fill((cell_x - 3, cell_y + thumb_h, thumb_w + 6, 3), lib_t["accent"])
                        renderer.fill((cell_x - 3, cell_y, 3, thumb_h), lib_t["accent"])
                        renderer.fill((cell_x + thumb_w, cell_y, 3, thumb_h), lib_t["accent"])
                    else:
                        renderer.fill((cell_x - 1, cell_y - 1, thumb_w + 2, 1), lib_t["divider"])
                        renderer.fill((cell_x - 1, cell_y + thumb_h, thumb_w + 2, 1), lib_t["divider"])
                        renderer.fill((cell_x - 1, cell_y, 1, thumb_h), lib_t["divider"])
                        renderer.fill((cell_x + thumb_w, cell_y, 1, thumb_h), lib_t["divider"])

                    # Reading Badge
                    if is_reading:
                        badge_w, badge_h = 48, 20
                        renderer.fill((cell_x + 6, cell_y + 6, badge_w, badge_h), lib_t["sel_bg"])
                        renderer.fill((cell_x + 6, cell_y + 6, badge_w, 1), lib_t["accent"])
                        tex_rd, rw_w, rh_w = render_text("READ", font_small, lib_t["accent"])
                        if tex_rd:
                            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_rd, None, sdl2.SDL_Rect(cell_x + 6 + (badge_w - rw_w)//2, cell_y + 6 + (badge_h - rh_w)//2, rw_w, rh_w))
                            sdl2.SDL_DestroyTexture(tex_rd)

                    # Label below thumbnail
                    lbl_color = lib_t["accent"] if is_sel else lib_t["text"]
                    tex_lbl, lw, lh = render_text(f"Page {p_idx + 1}", font_small, lbl_color)
                    if tex_lbl:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_lbl, None, sdl2.SDL_Rect(cell_x + (thumb_w - lw)//2, cell_y + thumb_h + 6, lw, lh))
                        sdl2.SDL_DestroyTexture(tex_lbl)

                # Bottom Footer Bar
                renderer.fill((0, SCREEN_H - 50, SCREEN_W, 50), lib_t["header"])
                renderer.fill((0, SCREEN_H - 50, SCREEN_W, 1), lib_t["divider"])
                
                footer_hint = "D-Pad / Sticks: Move   |   Y: Current Page   |   A: Jump to Page   |   B: Cancel"
                tex_foot, fw, fh = render_text(footer_hint, font_small, lib_t["secondary"])
                if tex_foot:
                    sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_foot, None, sdl2.SDL_Rect((SCREEN_W - fw)//2, SCREEN_H - 50 + (50 - fh)//2, fw, fh))
                    sdl2.SDL_DestroyTexture(tex_foot)

                # Preload 40 pages ahead and 10 pages behind (non-blocking)
                for p in range(end_page, min(total_p, end_page + 40)):
                    if (current_filepath, p) not in comic_thumb_cache:
                        queue_comic_thumbnail(current_filepath, p, priority=1)
                for p in range(max(0, start_page - 10), start_page):
                    if (current_filepath, p) not in comic_thumb_cache:
                        queue_comic_thumbnail(current_filepath, p, priority=1)
                    
            elif render_state == STATE_TOC:
                renderer.fill((0, 0, SCREEN_W, 60), theme["header"])
                tex, tw, th = render_text("CONTENTS", font_medium, theme["text"])
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

            if state == STATE_ABOUT:
                draw_about_dialog(renderer, theme_idx, font_medium, font_large, font_small, render_text)
            elif state == STATE_QUIT_CONFIRM:
                draw_quit_confirm_dialog(renderer, theme, font_large, font_ui_medium, render_text)

            renderer.present()
            needs_redraw = False
            if marquee_active and render_state == STATE_BROWSE:
                needs_redraw = True
            
        sdl2.SDL_Delay(16)

    cover_thread_running[0] = False
    comic_workers_running[0] = False
    for _t in _cover_threads: _t.join(timeout=0.3)
    for _t in _comic_thumb_threads: _t.join(timeout=0.3)
    clear_comic_thumb_cache()
    clear_cover_cache()
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
