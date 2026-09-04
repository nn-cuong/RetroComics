import os
import sys
import threading
import queue as _queue_mod
import hashlib

try:
    import sdl2
    import sdl2.ext
    import sdl2.sdlimage as sdlimage
except ImportError:
    pass

from comics import ComicArchive, log_debug


class CoverManager:
    """Fast Async Comic Cover System: background worker threads + disk cache."""
    def __init__(self, cache_dir="/mnt/SDCARD/.cover_cache", num_threads=3):
        self.cache_dir = cache_dir
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        self.cover_cache = {}          # filepath -> (SDL_Texture, w, h)
        self.cover_pending = set()
        self._cover_q = _queue_mod.Queue()
        self._cover_q_lock = threading.Lock()
        self.cover_ready = {}          # filepath -> (surf, w, h) or (None, 0, 0)
        self.cover_ready_lock = threading.Lock()
        self.running = [True]
        self._threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._threads.append(t)

    def _disk_path(self, fp):
        h = hashlib.sha1(fp.encode("utf-8", errors="replace")).hexdigest()[:16]
        return os.path.join(self.cache_dir, h + ".bmp")

    def _decode_cover(self, img_data):
        if "sdl2" not in sys.modules:
            return None, 0, 0
        rw = sdl2.SDL_RWFromConstMem(img_data, len(img_data))
        src = sdlimage.IMG_Load_RW(rw, 1)
        if not src:
            return None, 0, 0
        sw, sh = src.contents.w, src.contents.h
        if sw <= 0 or sh <= 0:
            sdl2.SDL_FreeSurface(src)
            return None, 0, 0
        return src, sw, sh

    def _worker(self):
        while self.running[0]:
            try:
                filepath = self._cover_q.get(timeout=0.5)
            except Exception:
                continue
            disk = self._disk_path(filepath)
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
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (None, 0, 0)
                self._cover_q.task_done()
                continue
            surf, dw, dh = self._decode_cover(img_data)
            if surf and dw > 0:
                if not os.path.exists(disk):
                    try:
                        sdl2.SDL_SaveBMP(surf, disk.encode("utf-8"))
                    except Exception:
                        pass
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (surf, dw, dh)
            else:
                if surf:
                    sdl2.SDL_FreeSurface(surf)
                with self.cover_ready_lock:
                    self.cover_ready[filepath] = (None, 0, 0)
            self._cover_q.task_done()

    def pump_ready(self, renderer):
        """Promote finished CPU surfaces -> GPU textures."""
        with self.cover_ready_lock:
            if not self.cover_ready:
                return
            batch = list(self.cover_ready.items())
            self.cover_ready.clear()
        for fp, result in batch:
            if len(result) == 3 and result[0] is not None:
                surf, dw, dh = result
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                self.cover_cache[fp] = (tex, dw, dh) if tex else (None, 0, 0)
            else:
                self.cover_cache[fp] = (None, 0, 0)

    def get_cover_texture(self, filepath):
        """Non-blocking: returns cached texture or queues background load."""
        if filepath in self.cover_cache:
            return self.cover_cache[filepath]
        with self.cover_ready_lock:
            already = filepath in self.cover_ready
        if not already:
            with self._cover_q_lock:
                if filepath not in self.cover_pending:
                    self.cover_pending.add(filepath)
                    self._cover_q.put_nowait(filepath)
        return (None, 0, 0)

    def prewarm_covers(self, item_list, path):
        """Pre-queue all file items immediately when entering a directory."""
        for item in item_list:
            if not item["is_dir"]:
                fp = os.path.join(path, item["name"])
                if fp not in self.cover_cache:
                    with self.cover_ready_lock:
                        already = fp in self.cover_ready
                    if not already:
                        with self._cover_q_lock:
                            if fp not in self.cover_pending:
                                self.cover_pending.add(fp)
                                self._cover_q.put_nowait(fp)

    get_texture = get_cover_texture
    prewarm = prewarm_covers

    def clear(self):
        with self._cover_q_lock:
            self.cover_pending.clear()
        while not self._cover_q.empty():
            try:
                self._cover_q.get_nowait()
                self._cover_q.task_done()
            except Exception:
                break
        with self.cover_ready_lock:
            for result in self.cover_ready.values():
                if len(result) == 3 and result[0] is not None:
                    try:
                        sdl2.SDL_FreeSurface(result[0])
                    except Exception:
                        pass
            self.cover_ready.clear()
        for tex, _, _ in self.cover_cache.values():
            if tex:
                try:
                    sdl2.SDL_DestroyTexture(tex)
                except Exception:
                    pass
        self.cover_cache.clear()
        ComicArchive.close_active()

    def shutdown(self):
        self.running[0] = False
        for t in self._threads:
            t.join(timeout=0.3)
        self.clear()


class ComicThumbManager:
    """Manages multithreaded priority thumbnails for comic pages with disk caching and LRU."""
    def __init__(self, cache_dir="/mnt/SDCARD/.comic_thumb_cache", num_threads=2):
        self.cache_dir = cache_dir
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception:
            pass
        self.comic_thumb_cache = {} # (filepath, p_idx) -> {"tex": tex, "w": w, "h": h, "last_used": t}
        self._q = _queue_mod.PriorityQueue()
        self._ready = _queue_mod.Queue()
        self._pending = set()
        self._pending_lock = threading.Lock()
        self._seq = 0
        self._seq_lock = threading.Lock()
        self.running = [True]
        self._threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._threads.append(t)

    def _disk_path(self, fp, p_idx):
        h = hashlib.sha1(f"{fp}:{p_idx}".encode("utf-8", errors="replace")).hexdigest()[:20]
        return os.path.join(self.cache_dir, f"{h}.bmp")

    def _worker(self):
        while self.running[0]:
            try:
                item = self._q.get(timeout=0.5)
            except Exception:
                continue
            if item is None:
                self._q.task_done()
                break
            try:
                prio, seq, fp, p_idx, p_name = item
                disk = self._disk_path(fp, p_idx)
                surf = None
                dw, dh = 0, 0

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

                with self._pending_lock:
                    self._pending.discard((fp, p_idx))

                if surf and dw > 0 and dh > 0:
                    self._ready.put((fp, p_idx, surf, dw, dh))
            except Exception as e:
                log_debug(f"Worker exception: {e}")
            finally:
                self._q.task_done()

    def pump_ready(self, renderer):
        """Promote finished thumbnail surfaces to GPU textures and evict LRU."""
        while not self._ready.empty():
            try:
                fp, p_idx, surf, dw, dh = self._ready.get_nowait()
            except Exception:
                break
            key = (fp, p_idx)
            if key not in self.comic_thumb_cache:
                tex = sdl2.SDL_CreateTextureFromSurface(renderer.sdlrenderer, surf)
                sdl2.SDL_FreeSurface(surf)
                if tex:
                    cur_t = sdl2.SDL_GetTicks() if "sdl2" in sys.modules else 0
                    if len(self.comic_thumb_cache) >= 80:
                        oldest_k = min(self.comic_thumb_cache.keys(), key=lambda k: self.comic_thumb_cache[k].get("last_used", 0))
                        try:
                            sdl2.SDL_DestroyTexture(self.comic_thumb_cache[oldest_k]["tex"])
                        except Exception:
                            pass
                        del self.comic_thumb_cache[oldest_k]
                    self.comic_thumb_cache[key] = {"tex": tex, "w": dw, "h": dh, "last_used": cur_t}
            else:
                sdl2.SDL_FreeSurface(surf)
            self._ready.task_done()

    def get_thumbnail(self, filepath, page_idx, page_name, priority=0):
        key = (filepath, page_idx)
        if key in self.comic_thumb_cache:
            item = self.comic_thumb_cache[key]
            if "sdl2" in sys.modules:
                item["last_used"] = sdl2.SDL_GetTicks()
            return item
        with self._pending_lock:
            if key not in self._pending:
                self._pending.add(key)
                with self._seq_lock:
                    self._seq += 1
                    s = self._seq
                self._q.put((priority, s, filepath, page_idx, page_name))
        return None

    def clear(self):
        with self._pending_lock:
            self._pending.clear()
        while not self._q.empty():
            try:
                self._q.get_nowait()
                self._q.task_done()
            except Exception:
                break
        while not self._ready.empty():
            try:
                _, _, surf, _, _ = self._ready.get_nowait()
                if surf:
                    try:
                        sdl2.SDL_FreeSurface(surf)
                    except Exception:
                        pass
                self._ready.task_done()
            except Exception:
                break
        for item in self.comic_thumb_cache.values():
            if item.get("tex"):
                try:
                    sdl2.SDL_DestroyTexture(item["tex"])
                except Exception:
                    pass
        self.comic_thumb_cache.clear()

    def shutdown(self):
        self.running[0] = False
        for t in self._threads:
            t.join(timeout=0.3)
        self.clear()
