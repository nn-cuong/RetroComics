import os
from constants import SCREEN_W, SCREEN_H, THEMES, LIBRARY_THEMES

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlttf as sdlttf
except ImportError:
    pass

def draw_about_dialog(renderer, theme_idx, font_medium, font_large, font_small, render_text):
    lib_t = LIBRARY_THEMES[theme_idx % len(LIBRARY_THEMES)]
    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 160)
    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
    
    pop_w, pop_h = 640, 400
    pop_x, pop_y = (SCREEN_W - pop_w) // 2, (SCREEN_H - pop_h) // 2
    renderer.fill((pop_x, pop_y, pop_w, pop_h), lib_t["sel_border"])
    renderer.fill((pop_x + 2, pop_y + 2, pop_w - 4, pop_h - 4), lib_t["bg"])
    
    # Title
    tex, tw, th = render_text("APPLICATION INFO", font_medium, lib_t["accent"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 24, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    # App Name
    tex, tw, th = render_text("RetroComics v1.0", font_large, lib_t["text"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 68, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    # Subtitle
    tex, tw, th = render_text("Comic & Manga Reader for TrimUI Brick Pro", font_small, lib_t["secondary"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + 128, tw, th))
        sdl2.SDL_DestroyTexture(tex)
        
    renderer.fill((pop_x + 40, pop_y + 166, pop_w - 80, 1), lib_t["divider"])
    
    # Info lines
    lines = [
        "Author: Nguyen Ngoc Cuong",
        "Email: nn.cuong.404@gmail.com",
        "Facebook: aegony98 / Instagram: ich_heisse_cuong"
    ]
    iy = pop_y + 200
    for line in lines:
        tex, tw, th = render_text(line, font_small, lib_t["text"])
        if tex:
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + 35, iy, min(tw, pop_w - 70), th))
            sdl2.SDL_DestroyTexture(tex)
        iy += 40
        
    renderer.fill((pop_x + 40, pop_y + pop_h - 55, pop_w - 80, 1), lib_t["divider"])
    tex, tw, th = render_text("B / SELECT: Close", font_small, lib_t["secondary"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + (pop_w - tw)//2, pop_y + pop_h - 40, tw, th))
        sdl2.SDL_DestroyTexture(tex)

def draw_quit_confirm_dialog(renderer, theme, font_large, font_ui_medium, render_text):
    sdl2.SDL_SetRenderDrawBlendMode(renderer.sdlrenderer, sdl2.SDL_BLENDMODE_BLEND)
    sdl2.SDL_SetRenderDrawColor(renderer.sdlrenderer, 0, 0, 0, 150)
    sdl2.SDL_RenderFillRect(renderer.sdlrenderer, sdl2.SDL_Rect(0, 0, SCREEN_W, SCREEN_H))
    
    pop_w, pop_h = 600, 200
    pop_x, pop_y = (SCREEN_W - pop_w)//2, (SCREEN_H - pop_h)//2
    
    renderer.fill((pop_x, pop_y, pop_w, pop_h), theme["sel"])
    renderer.fill((pop_x + 2, pop_y + 2, pop_w - 4, pop_h - 4), theme["bg"])
    
    msg = "Exit RetroComics?"
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_BOLD)
    tex, tw, th = render_text(msg, font_large, theme["text"])
    sdlttf.TTF_SetFontStyle(font_large, sdlttf.TTF_STYLE_NORMAL)
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 40, tw, th))
        sdl2.SDL_DestroyTexture(tex)
    
    msg2 = "A: Confirm   B: Cancel"
    tex, tw, th = render_text(msg2, font_ui_medium, theme["text"])
    if tex:
        sdl2.SDL_RenderCopy(renderer.sdlrenderer, tex, None, sdl2.SDL_Rect(pop_x + pop_w//2 - tw//2, pop_y + 130, tw, th))
        sdl2.SDL_DestroyTexture(tex)

def draw_toast_notification(renderer, toast_msg, toast_timer, current_ticks, font_small, render_text):
    if toast_msg and (current_ticks - toast_timer < 2000):
        t_tex, tw, th = render_text(toast_msg, font_small, sdl2.SDL_Color(255, 255, 255, 255))
        if t_tex:
            pad = 16
            box_w = tw + pad * 2
            box_h = th + pad
            box_x = (SCREEN_W - box_w) // 2
            box_y = SCREEN_H - 120
            renderer.fill((box_x, box_y, box_w, box_h), sdl2.ext.Color(30, 30, 30))
            renderer.fill((box_x + 2, box_y + 2, box_w - 4, box_h - 4), sdl2.ext.Color(60, 60, 60))
            sdl2.SDL_RenderCopy(renderer.sdlrenderer, t_tex, None, sdl2.SDL_Rect(box_x + pad, box_y + pad // 2, tw, th))
            sdl2.SDL_DestroyTexture(t_tex)
        return toast_msg
    return ""
