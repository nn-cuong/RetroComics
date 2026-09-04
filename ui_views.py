import os
import sys

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
except ImportError:
    pass

from constants import (
    SCREEN_W, SCREEN_H,
    LIBRARY_THEMES,
    get_book_display_metadata
)

def draw_book_icon(renderer, x, y, color, background):
    """Small pixel-friendly book glyph, deliberately free of emoji assets."""
    renderer.fill((x, y, 15, 20), color)
    renderer.fill((x + 3, y + 3, 2, 14), background)


def draw_browse_view(
    renderer, theme_idx, library_view_mode, list_items, sel_index, scroll_y,
    files, current_path, base_path, font_large, font_small, font_ui_medium,
    render_text, cover_manager, sel_time, current_ticks
):
    """Draws library browse screen in either Grid view or List view matching RetroReader."""
    library_theme = LIBRARY_THEMES[theme_idx % len(LIBRARY_THEMES)]
    renderer.clear(library_theme["bg"])
    renderer.fill((0, 0, SCREEN_W, 76), library_theme["header"])
    renderer.fill((0, 74, SCREEN_W, 2), library_theme["divider"])
    
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_BOLD)
    tex, tw, th = render_text("LIBRARY", font_large, library_theme["text"])
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_NORMAL)
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(32, 12, tw, th))
        sdl2.SDL_DestroyTexture(tex)

    mode_str = "[GRID]" if library_view_mode == "grid" else "[LIST]"
    book_count = f"{len(files)} COMIC" + ("" if len(files) == 1 else "S") + f"    {mode_str}"
    tex, tw, th = render_text(book_count, font_small, library_theme["secondary"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, 27, tw, th))
        sdl2.SDL_DestroyTexture(tex)

    sel_border = library_theme.get("sel_border", sdl2.ext.Color(102, 137, 181))
    sel_bg = library_theme.get("sel_bg", sdl2.ext.Color(229, 235, 241))
    sel_text = library_theme.get("sel_text", sdl2.SDL_Color(30, 30, 30, 255))
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
                    t_dir, dw, dh = render_text("FOLDER", font_small, library_theme["accent"])
                    if t_dir:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_dir, None, sdl2.SDL_Rect(cover_x + (cover_w - dw) // 2, fy + 20, dw, dh))
                        sdl2.SDL_DestroyTexture(t_dir)
            else:
                filepath = os.path.join(current_path, item["name"])
                ext = os.path.splitext(item["name"])[1].lower()
                c_tex, orig_w, orig_h = cover_manager.get_cover_texture(filepath)
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
                    renderer.fill((cover_x + 14, cover_y + 2, 2, cover_h - 4), library_theme["divider"])
                    draw_book_icon(renderer, cover_x + (cover_w - 15) // 2 + 5, cover_y + 65, library_theme["accent"], library_theme["header"])
                    badge_str = ext.upper().lstrip('.') if ext else "COMIC"
                    t_badge, bw, bh = render_text(f"[ {badge_str} ]", font_small, library_theme["secondary"])
                    if t_badge:
                        sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_badge, None, sdl2.SDL_Rect(cover_x + (cover_w - bw) // 2 + 5, cover_y + 115, bw, bh))
                        sdl2.SDL_DestroyTexture(t_badge)

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

        page_str = f"Page {grid_page + 1} / {max(1, (len(list_items) + 7) // 8)}"
        tex, tw, th = render_text(page_str, font_small, library_theme["secondary"])
        if tex:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(SCREEN_W - 32 - tw, SCREEN_H - 50 + (50 - th)//2, tw, th))
            sdl2.SDL_DestroyTexture(tex)

    else:
        # LIST MODE
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

    return marquee_active


def draw_comic_reader_view(
    renderer, theme, target, reader_w, reader_h, loaded_comic_texture,
    comic_img_w, comic_img_h, comic_zoom_level, comic_pan_x, comic_pan_y,
    show_comic_hud, current_filepath, current_page_idx, book_pages,
    reader_rotation_idx, font_small, render_text
):
    """Draws comic page with zoom, panning, rotation, and high-contrast HUD matching RetroReader."""
    drawing_rotated = (reader_rotation_idx != 0)
    draw_target = target if drawing_rotated else None
    sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, draw_target)
    renderer.clear(theme["bg"])

    if loaded_comic_texture:
        if comic_zoom_level <= 0:
            comic_zoom_level = reader_w / float(comic_img_w) if comic_img_w > 0 else 1.0
        scaled_w = int(comic_img_w * comic_zoom_level)
        scaled_h = int(comic_img_h * comic_zoom_level)
        max_pan_x = max(0, scaled_w - reader_w)
        max_pan_y = max(0, scaled_h - reader_h)
        comic_pan_x = max(0, min(comic_pan_x, max_pan_x))
        comic_pan_y = max(0, min(comic_pan_y, max_pan_y))
        draw_x = -comic_pan_x
        draw_y = -comic_pan_y
        if scaled_w < reader_w:
            draw_x = (reader_w - scaled_w) // 2
        if scaled_h < reader_h:
            draw_y = (reader_h - scaled_h) // 2
        dst_rect = sdl2.SDL_Rect(draw_x, draw_y, scaled_w, scaled_h)
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, loaded_comic_texture, None, dst_rect)
    
    if show_comic_hud:
        sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
        sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 15, 15, 18, 215)
        sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, reader_w, 52))
        sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 255, 255, 255, 35)
        sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 51, reader_w, 1))

        book_title, _ = get_book_display_metadata(os.path.basename(current_filepath))
        total_pages = len(book_pages) if book_pages else 1
        hud_top = f"{book_title}  •  Page {current_page_idx + 1}/{total_pages}"
        hud_text_color = sdl2.ext.Color(255, 255, 255)
        tex, tw, th = render_text(hud_top, font_small, hud_text_color)
        if tex:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(24, (52 - th) // 2, min(tw, reader_w - 48), th))
            sdl2.SDL_DestroyTexture(tex)
        
        sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 15, 15, 18, 215)
        sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, reader_h - 48, reader_w, 48))
        sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 255, 255, 255, 35)
        sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, reader_h - 48, reader_w, 1))

        footer = "L2: Page Select  |  L1/R1: Prev/Next  |  Y/B: Zoom +/-  |  X: Rotate  |  A: HUD  |  SELECT: LIB"
        tex_bot, bw, bh = render_text(footer, font_small, hud_text_color)
        if tex_bot:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_bot, None, sdl2.SDL_Rect(24, reader_h - 48 + (48 - bh) // 2, min(bw, reader_w - 48), bh))
            sdl2.SDL_DestroyTexture(tex_bot)

    if drawing_rotated:
        reader_angle = 0
        rot = reader_rotation_idx % 4
        if rot == 1: reader_angle = 90
        elif rot == 2: reader_angle = 180
        elif rot == 3: reader_angle = 270
        sdl2.SDL_SetRenderTarget(renderer.sdlrenderer, None)
        sdl2.SDL_RenderClear(renderer.sdlrenderer)
        src_rect = sdl2.SDL_Rect(0, 0, reader_w, reader_h)
        center_x, center_y = SCREEN_W // 2, SCREEN_H // 2
        dst_rect = sdl2.SDL_Rect(center_x - reader_w // 2, center_y - reader_h // 2, reader_w, reader_h)
        sdl2.SDL_RenderCopyEx(renderer.sdlrenderer, target, src_rect, dst_rect, float(reader_angle), None, sdl2.SDL_FLIP_NONE)


def draw_page_select_view(
    renderer, theme_idx, current_filepath, page_select_temp, current_page_idx,
    book_pages, font_medium, font_small, render_text, comic_thumb_manager
):
    """Draws 2x5 visual thumbnail grid for comic page selection matching RetroReader."""
    lib_t = LIBRARY_THEMES[theme_idx % len(LIBRARY_THEMES)]
    renderer.fill((0, 0, SCREEN_W, SCREEN_H), lib_t["bg"])
    
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
        
        renderer.fill((cell_x, cell_y, thumb_w, thumb_h), lib_t["header"])
        
        p_name = book_pages[p_idx] if (book_pages and p_idx < len(book_pages)) else None
        thumb_info = comic_thumb_manager.get_thumbnail(current_filepath, p_idx, p_name)
        if thumb_info:
            tex_thumb = thumb_info["tex"]
            img_w, img_h = thumb_info["w"], thumb_info["h"]
            scale = min(float(thumb_w) / max(1, img_w), float(thumb_h) / max(1, img_h))
            dw = max(1, int(img_w * scale))
            dh = max(1, int(img_h * scale))
            dx = cell_x + (thumb_w - dw) // 2
            dy = cell_y + (thumb_h - dh) // 2
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_thumb, None, sdl2.SDL_Rect(dx, dy, dw, dh))
        else:
            tex_ph, pw, ph = render_text(f"P. {p_idx + 1}", font_small, lib_t["secondary"])
            if tex_ph:
                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_ph, None, sdl2.SDL_Rect(cell_x + (thumb_w - pw)//2, cell_y + (thumb_h - ph)//2, pw, ph))
                sdl2.SDL_DestroyTexture(tex_ph)
                
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

        if is_reading:
            badge_w, badge_h = 48, 20
            renderer.fill((cell_x + 6, cell_y + 6, badge_w, badge_h), lib_t["sel_bg"])
            renderer.fill((cell_x + 6, cell_y + 6, badge_w, 1), lib_t["accent"])
            tex_rd, rw_w, rh_w = render_text("READ", font_small, lib_t["accent"])
            if tex_rd:
                sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_rd, None, sdl2.SDL_Rect(cell_x + 6 + (badge_w - rw_w)//2, cell_y + 6 + (badge_h - rh_w)//2, rw_w, rh_w))
                sdl2.SDL_DestroyTexture(tex_rd)

        lbl_color = lib_t["accent"] if is_sel else lib_t["text"]
        tex_lbl, lw, lh = render_text(f"Page {p_idx + 1}", font_small, lbl_color)
        if tex_lbl:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_lbl, None, sdl2.SDL_Rect(cell_x + (thumb_w - lw)//2, cell_y + thumb_h + 6, lw, lh))
            sdl2.SDL_DestroyTexture(tex_lbl)

    renderer.fill((0, SCREEN_H - 50, SCREEN_W, 50), lib_t["header"])
    renderer.fill((0, SCREEN_H - 50, SCREEN_W, 1), lib_t["divider"])
    
    footer_hint = "D-Pad / Sticks: Move   |   Y: Current Page   |   A: Jump to Page   |   B: Cancel"
    tex_foot, fw, fh = render_text(footer_hint, font_small, lib_t["secondary"])
    if tex_foot:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex_foot, None, sdl2.SDL_Rect((SCREEN_W - fw)//2, SCREEN_H - 50 + (50 - fh)//2, fw, fh))
        sdl2.SDL_DestroyTexture(tex_foot)
