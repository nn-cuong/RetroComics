import sys
import os
import textwrap
import traceback
import json
import re
import threading

from constants import (
    SCREEN_W, SCREEN_H,
    STATE_BROWSE, STATE_READER, STATE_QUIT_CONFIRM, STATE_PAGE_SELECT, STATE_ABOUT,
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

from covers import CoverManager, ComicThumbManager
from ui_views import (
    draw_book_icon,
    draw_browse_view,
    draw_comic_reader_view,
    draw_page_select_view
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

    cover_manager = CoverManager()

    # Reader Data
    book_pages = [] # List of image filenames
    current_filepath = ""
    current_page_idx = 0
    zoom_level = -1.0 # -1.0 means auto fit width initially
    pan_x = 0
    pan_y = 0
    pan_fx = 0.0
    pan_fy = 0.0
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

    def handle_reader_direction(dx, dy, pan_step=None):
        nonlocal pan_x, pan_y, pan_fx, pan_fy, zoom_level, img_h, img_w
        if abs(pan_fx - pan_x) > 1.0:
            pan_fx = float(pan_x)
        if abs(pan_fy - pan_y) > 1.0:
            pan_fy = float(pan_y)
        dx, dy = rotate_reader_direction(dx, dy)
        vw, vh = get_reader_view_size()
        
        if zoom_level <= 0:
            zoom_level = vw / float(img_w) if img_w > 0 else 1.0
            
        scaled_w = int(img_w * zoom_level)
        scaled_h = int(img_h * zoom_level)
        
        step = 60.0 if pan_step is None else float(pan_step)
        
        if dx != 0:
            pan_fx += float(dx) * step
        if dy != 0:
            pan_fy += float(dy) * step
            
        # Clamp pan_fx & pan_fy
        max_pan_x = float(max(0, scaled_w - vw))
        pan_fx = max(0.0, min(pan_fx, max_pan_x))
        max_pan_y = float(max(0, scaled_h - vh))
        pan_fy = max(0.0, min(pan_fy, max_pan_y))
        pan_x = int(round(pan_fx))
        pan_y = int(round(pan_fy))

    comic_thumb_manager = ComicThumbManager()
    comic_thumb_manager.cleanup_cache(keep_recent_books=3, max_age_days=5)



    def load_book(filepath):
        nonlocal book_pages, current_page_idx, pan_x, pan_y, pan_fx, pan_fy, zoom_level, current_font_size, current_filepath, loaded_page_idx, loaded_texture
        book_pages = []
        loaded_page_idx = -1
        comic_thumb_manager.clear()
        if loaded_texture:
            sdl2.SDL_DestroyTexture(loaded_texture)
            loaded_texture = None
            
        save_data = load_save(filepath)
        current_page_idx = save_data.get("scroll_y", 0)
        current_font_size = save_data.get("font_size", 34)
        zoom_level = -1.0
        pan_x = 0
        pan_y = 0
        pan_fx = 0.0
        pan_fy = 0.0
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
    last_pan_ticks = 0
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
        lx, ly, rx, ry = 0, 0, 0, 0
        for c in controllers:
            clx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTX)
            cly = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_LEFTY)
            crx = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTX)
            cry = sdl2.SDL_GameControllerGetAxis(c, sdl2.SDL_CONTROLLER_AXIS_RIGHTY)
            if abs(clx) > abs(lx): lx = clx
            if abs(cly) > abs(ly): ly = cly
            if abs(crx) > abs(rx): rx = crx
            if abs(cry) > abs(ry): ry = cry

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

        # Right Stick dedicated controls for Comic Reader
        if abs(rx) < 10000 and abs(ry) < 10000:
            right_axis_held = False
        elif state == STATE_READER:
            if not right_axis_held or (current_ticks - last_right_axis_time > 100):
                if abs(rx) >= 15000 and abs(rx) > abs(ry):
                    if rx > 0: # Right -> Next Page (like R1)
                        if book_pages and current_page_idx < len(book_pages) - 1:
                            current_page_idx += 1
                            zoom_level = -1.0
                            pan_x = 0
                            pan_y = 0
                            pan_fx = 0.0
                            pan_fy = 0.0
                            needs_redraw = True
                    else: # Left -> Prev Page (like L1)
                        if current_page_idx > 0:
                            current_page_idx -= 1
                            zoom_level = -1.0
                            pan_x = 0
                            pan_y = 0
                            pan_fx = 0.0
                            pan_fy = 0.0
                            needs_redraw = True
                    right_axis_held = True
                    last_right_axis_time = current_ticks
                elif abs(ry) >= 15000 and abs(ry) >= abs(rx):
                    state = STATE_PAGE_SELECT
                    page_select_temp = current_page_idx
                    dpad_timer = 0
                    dpad_horiz_timer = 0
                    dpad_up_held = False
                    dpad_down_held = False
                    dpad_left_held = False
                    dpad_right_held = False
                    needs_redraw = True
                    right_axis_held = True
                    last_right_axis_time = current_ticks

        # Left Stick controls pan in Comic Reader (Smooth, 60fps frame-paced analog panning)
        if state == STATE_READER:
            if abs(lx) < 12000 and abs(ly) < 12000:
                left_axis_held = False
                last_pan_ticks = 0
            else:
                dt = 0.016
                if left_axis_held and last_pan_ticks > 0:
                    elapsed_ms = current_ticks - last_pan_ticks
                    if 0 < elapsed_ms < 100:
                        dt = elapsed_ms / 1000.0
                last_pan_ticks = current_ticks
                left_axis_held = True

                old_px, old_py = pan_x, pan_y
                if abs(lx) >= 12000:
                    norm_x = min(1.0, max(0.0, (abs(lx) - 12000) / 20767.0))
                    curve_x = norm_x * norm_x
                    vel_x = 100.0 + 550.0 * curve_x
                    pdx = 1 if lx > 0 else -1
                    handle_reader_direction(pdx, 0, pan_step=min(25.0, vel_x * dt))
                if abs(ly) >= 12000:
                    norm_y = min(1.0, max(0.0, (abs(ly) - 12000) / 20767.0))
                    curve_y = norm_y * norm_y
                    vel_y = 100.0 + 550.0 * curve_y
                    pdy = 1 if ly > 0 else -1
                    handle_reader_direction(0, pdy, pan_step=min(25.0, vel_y * dt))
                if pan_x != old_px or pan_y != old_py:
                    needs_redraw = True
                    
        for event in events:
            if event.type == sdl2.SDL_CONTROLLERAXISMOTION:
                if state == STATE_READER:
                    if event.caxis.axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:
                        val = event.caxis.value
                        if val > 16000 and not l2_pressed:
                            l2_pressed = True
                            state = STATE_PAGE_SELECT
                            page_select_temp = current_page_idx
                            dpad_timer = 0
                            dpad_horiz_timer = 0
                            dpad_up_held = False
                            dpad_down_held = False
                            dpad_left_held = False
                            dpad_right_held = False
                            needs_redraw = True
                        elif val < 8000:
                            l2_pressed = False
                    elif event.caxis.axis == sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
                        val = event.caxis.value
                        if val > 16000 and not r2_pressed:
                            r2_pressed = True
                        elif val < 8000:
                            r2_pressed = False
                elif state == STATE_PAGE_SELECT:
                    if event.caxis.axis in (sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT, sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT):
                        val = event.caxis.value
                        if val > 16000 and not l2_pressed and not r2_pressed:
                            l2_pressed = True
                            r2_pressed = True
                            state = STATE_READER
                            comic_thumb_manager.cancel_pending()
                            needs_redraw = True
                        elif val < 8000:
                            l2_pressed = False
                            r2_pressed = False
            if event.type == sdl2.SDL_QUIT:
                if state in (STATE_READER, STATE_PAGE_SELECT):
                    write_save(current_filepath, current_page_idx, current_font_size)
                running = False
            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    if state in (STATE_READER, STATE_PAGE_SELECT):
                        write_save(current_filepath, current_page_idx, current_font_size)
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

                if state == STATE_QUIT_CONFIRM:
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A (Confirm)
                        if state_before_quit in (STATE_READER, STATE_PAGE_SELECT):
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
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: # L: Prev Theme
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
                                cover_manager.clear()
                                current_path = os.path.dirname(current_path)
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                _li_pw = ([{"name":"..","is_dir":True}] if current_path != base_path else []) + [{"name":f,"is_dir":True} for f in folders] + [{"name":f,"is_dir":False} for f in files]
                                cover_manager.prewarm_covers(_li_pw, current_path)
                                needs_redraw = True
                            elif item["is_dir"]:
                                cover_manager.clear()
                                current_path = os.path.join(current_path, item["name"])
                                folders, files = get_directory_contents(current_path)
                                sel_index = 0
                                scroll_y = 0
                                _li_pw = ([{"name":"..","is_dir":True}] if current_path != base_path else []) + [{"name":f,"is_dir":True} for f in folders] + [{"name":f,"is_dir":False} for f in files]
                                cover_manager.prewarm_covers(_li_pw, current_path)
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
                        pan_fx = 0.0
                        pan_fy = 0.0
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: # R1: Next Page
                        current_page_idx = min(len(book_pages) - 1, current_page_idx + 1)
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                        pan_fx = 0.0
                        pan_fy = 0.0
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y: Zoom In
                        vw, vh = get_reader_view_size()
                        if img_w > 0 and img_h > 0:
                            fit_page = min(vw / float(img_w), vh / float(img_h))
                            if zoom_level <= 0:
                                zoom_level = vw / float(img_w)
                            zoom_level = min(zoom_level * 1.25, fit_page * 8.0)
                            scaled_w = int(img_w * zoom_level)
                            scaled_h = int(img_h * zoom_level)
                            max_pan_x = max(0, scaled_w - vw)
                            max_pan_y = max(0, scaled_h - vh)
                            pan_x = max(0, min(pan_x, max_pan_x))
                            pan_y = max(0, min(pan_y, max_pan_y))
                            pan_fx = float(pan_x)
                            pan_fy = float(pan_y)
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
                            pan_fx = float(pan_x)
                            pan_fy = float(pan_y)
                            needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_Y: # Physical X: Rotate
                        reader_rotation_idx = (reader_rotation_idx + 1) % 4
                        write_reader_rotation_idx(reader_rotation_idx)
                        zoom_level = -1.0 # reset zoom
                        pan_x = 0
                        pan_y = 0
                        pan_fx = 0.0
                        pan_fy = 0.0
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT: Exit
                        write_save(current_filepath, current_page_idx, current_font_size)
                        ComicArchive.close_active()
                        comic_thumb_manager.cleanup_cache(keep_recent_books=3, max_age_days=5)
                        state = STATE_BROWSE
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Toggle HUD
                        show_hud = not show_hud
                        
                elif state == STATE_PAGE_SELECT:
                    total_p = len(book_pages) if book_pages else 1
                    if btn == sdl2.SDL_CONTROLLER_BUTTON_B: # Physical A: Confirm
                        current_page_idx = page_select_temp
                        zoom_level = -1.0
                        pan_x = 0
                        pan_y = 0
                        pan_fx = 0.0
                        pan_fy = 0.0
                        state = STATE_READER
                        comic_thumb_manager.clear()
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_A: # Physical B: Cancel
                        state = STATE_READER
                        comic_thumb_manager.clear()
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_BACK: # SELECT: Return to Library
                        write_save(current_filepath, current_page_idx, current_font_size)
                        ComicArchive.close_active()
                        comic_thumb_manager.clear()
                        comic_thumb_manager.cleanup_cache(keep_recent_books=3, max_age_days=5)
                        state = STATE_BROWSE
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_X: # Physical Y: Snap to Current Reading Page
                        page_select_temp = current_page_idx
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER:
                        page_select_temp = max(0, page_select_temp - 10)
                        needs_redraw = True
                    elif btn == sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER:
                        page_select_temp = min(total_p - 1, page_select_temp + 10)
                        needs_redraw = True
                        


        # Key repeat logic for library and comic TOC (exact Files app behavior)
        if state in (STATE_BROWSE, STATE_PAGE_SELECT):
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

        cover_manager.pump_ready(renderer)  # promote background-loaded covers to GPU textures
        comic_thumb_manager.pump_ready(renderer)  # promote background-loaded thumbnails to GPU textures
        did_render = False
        if needs_redraw:
            did_render = True
            theme = THEMES[theme_idx]
            renderer.clear(theme["bg"])
            
            if state in (STATE_QUIT_CONFIRM, STATE_ABOUT):
                render_state = state_before_quit if state == STATE_QUIT_CONFIRM else STATE_BROWSE
            else:
                render_state = state

            if render_state == STATE_BROWSE:
                marquee_active = draw_browse_view(
                    renderer, theme_idx, library_view_mode, list_items, sel_index, scroll_y,
                    files, current_path, base_path, font_large, font_small, font_ui_medium,
                    render_text, cover_manager, sel_time, current_ticks
                )
            elif render_state == STATE_READER:
                reader_w, reader_h = get_reader_view_size()
                target = ensure_reader_target(reader_w, reader_h)
                if book_pages and current_page_idx < len(book_pages):
                    if loaded_page_idx != current_page_idx:
                        if loaded_texture:
                            sdl2.SDL_DestroyTexture(loaded_texture)
                            loaded_texture = None
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
                        except Exception as e:
                            log_debug(f"Error loading comic page: {e}")
                        loaded_page_idx = current_page_idx
                        pan_x = 0
                        pan_y = 0
                        pan_fx = 0.0
                        pan_fy = 0.0

                        # Proactively prefetch adjacent pages in background for instant flipping
                        prefetch_targets = []
                        if current_page_idx + 1 < len(book_pages):
                            prefetch_targets.append(book_pages[current_page_idx + 1])
                        if current_page_idx > 0:
                            prefetch_targets.append(book_pages[current_page_idx - 1])
                        if current_page_idx + 2 < len(book_pages):
                            prefetch_targets.append(book_pages[current_page_idx + 2])
                        if prefetch_targets:
                            ComicArchive.prefetch_pages(current_filepath, prefetch_targets)
                draw_comic_reader_view(
                    renderer, theme, target, reader_w, reader_h, loaded_texture,
                    img_w, img_h, zoom_level, pan_x, pan_y, show_hud, current_filepath,
                    current_page_idx, book_pages, reader_rotation_idx, font_small, render_text
                )
            elif render_state == STATE_PAGE_SELECT:
                draw_page_select_view(
                    renderer, theme_idx, current_filepath, page_select_temp, current_page_idx,
                    book_pages, font_medium, font_small, render_text, comic_thumb_manager
                )

            if state == STATE_ABOUT:
                draw_about_dialog(renderer, theme_idx, font_medium, font_large, font_small, render_text)
            elif state == STATE_QUIT_CONFIRM:
                draw_quit_confirm_dialog(renderer, theme, font_large, font_ui_medium, render_text)

            renderer.present()
            needs_redraw = False
            if marquee_active and render_state == STATE_BROWSE:
                needs_redraw = True
            
        # Dynamic power-saving sleep: 60 FPS (16ms) during interaction/motion, 30 FPS (30ms) during static reading
        is_active = (
            did_render
            or needs_redraw
            or bool(events)
            or left_axis_held
            or right_axis_held
            or dpad_up_held
            or dpad_down_held
            or dpad_left_held
            or dpad_right_held
        )
        sdl2.SDL_Delay(16 if is_active else 30)

    cover_manager.shutdown()
    comic_thumb_manager.shutdown()
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
