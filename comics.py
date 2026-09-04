import os
import sys
import re
import io
import struct
import subprocess
import zipfile
import threading
from constants import natural_sort_key

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

class ComicArchive:
    _active_filepath = None
    _active_pdf = None
    _active_zip = None
    _page_cache = {} # (filepath, page_filename) -> bytes
    _MAX_CACHE_ITEMS = 6
    _archive_lock = threading.RLock()

    @classmethod
    def close_active(cls):
        with cls._archive_lock:
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
        with cls._archive_lock:
            if cls._active_filepath == filepath and cls._active_pdf is not None:
                return cls._active_pdf
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
        with cls._archive_lock:
            if cls._active_filepath == filepath and cls._active_zip is not None:
                return cls._active_zip
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

        # 1. Native ZIP / CBZ
        if ext in ('.zip', '.cbz'):
            try:
                zf = cls.get_open_zip(filepath)
                if zf is not None:
                    for name in zf.namelist():
                        if name.lower().endswith(valid_exts) and not name.startswith('__MACOSX') and not os.path.basename(name).startswith('.'):
                            pages.append(name)
                    pages.sort(key=natural_sort_key)
                    return pages
            except Exception as e:
                log_debug(f"ZIP get_pages error: {e}")

        # 2. Native unrar CLI
        if ext in ('.rar', '.cbr') and os.path.exists(UNRAR_BIN):
            try:
                cmd = [UNRAR_BIN, "lb", filepath]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        name = line.strip()
                        if name.lower().endswith(valid_exts) and not name.startswith('__MACOSX') and not os.path.basename(name).startswith('.'):
                            pages.append(name)
                    pages.sort(key=natural_sort_key)
                    return pages
            except Exception as e:
                log_debug(f"UNRAR get_pages error: {e}")

        # 3. 7zzs CLI
        if os.path.exists(SEVEN_Z_BIN):
            try:
                cmd = [SEVEN_Z_BIN, "l", "-slt", "-ba", filepath]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if line.startswith("Path = "):
                            name = line[7:].strip()
                            if name.lower().endswith(valid_exts) and not name.startswith('__MACOSX') and not os.path.basename(name).startswith('.'):
                                pages.append(name)
                    pages.sort(key=natural_sort_key)
                    return pages
            except Exception as e:
                log_debug(f"7zz get_pages error: {e}")

        return pages

    @classmethod
    def read_image_data(cls, filepath, page_filename, is_thumb=False):
        cache_key = (filepath, page_filename)
        with cls._archive_lock:
            if not is_thumb and cache_key in cls._page_cache:
                return cls._page_cache[cache_key]

        ext = os.path.splitext(filepath)[1].lower()

        # 0. Dedicated PDF Page Render
        if ext == '.pdf':
            try:
                page_num = int(page_filename.replace("page_", ""))
            except Exception:
                try:
                    m = re.search(r'(\d+)', page_filename)
                    page_num = int(m.group(1)) if m else 1
                except Exception:
                    page_num = 1

            with cls._archive_lock:
                pdf = cls.get_open_pdf(filepath)
                if pdf is not None:
                    try:
                        page = pdf[page_num - 1]
                        pw, ph = page.get_size()
                        if is_thumb:
                            scale = min(264.0 / max(1.0, pw), 372.0 / max(1.0, ph))
                        else:
                            scale = max(1.0, min(1.4, 1024.0 / max(1.0, pw)))
                        bitmap = page.render(scale=scale, prefer_bgrx=True)
                        raw_bytes = bytes(bitmap.buffer)
                        w = bitmap.width
                        h = bitmap.height
                        bpp = bitmap.n_channels * 8
                        if raw_bytes and w > 0 and h > 0:
                            bmp_data = bitmap_to_bmp(raw_bytes, w, h, bpp)
                            if not is_thumb:
                                if len(cls._page_cache) >= cls._MAX_CACHE_ITEMS:
                                    cls._page_cache.pop(next(iter(cls._page_cache)))
                                cls._page_cache[cache_key] = bmp_data
                            return bmp_data
                    except Exception as e:
                        import traceback
                        log_debug(f"PDF render exception p{page_num}: {e}\n{traceback.format_exc()}")

        # 1. Native ZIP / CBZ
        if ext in ('.zip', '.cbz'):
            try:
                zf = cls.get_open_zip(filepath)
                if zf is not None:
                    data = zf.read(page_filename)
                    with cls._archive_lock:
                        if not is_thumb:
                            if len(cls._page_cache) >= cls._MAX_CACHE_ITEMS:
                                cls._page_cache.pop(next(iter(cls._page_cache)))
                            cls._page_cache[cache_key] = data
                    return data
            except Exception as e:
                log_debug(f"ZIP read error: {e}")

        # 2. Native unrar CLI
        if ext in ('.rar', '.cbr') and os.path.exists(UNRAR_BIN):
            try:
                cmd = [UNRAR_BIN, "p", "-inul", filepath, page_filename]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                if res.returncode == 0 and res.stdout:
                    with cls._archive_lock:
                        if not is_thumb:
                            if len(cls._page_cache) >= cls._MAX_CACHE_ITEMS:
                                cls._page_cache.pop(next(iter(cls._page_cache)))
                            cls._page_cache[cache_key] = res.stdout
                    return res.stdout
            except Exception as e:
                log_debug(f"UNRAR read error: {e}")

        # 3. 7zzs CLI
        if os.path.exists(SEVEN_Z_BIN):
            try:
                cmd = [SEVEN_Z_BIN, "e", "-so", filepath, page_filename]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                if res.returncode == 0 and res.stdout:
                    with cls._archive_lock:
                        if not is_thumb:
                            if len(cls._page_cache) >= cls._MAX_CACHE_ITEMS:
                                cls._page_cache.pop(next(iter(cls._page_cache)))
                            cls._page_cache[cache_key] = res.stdout
                    return res.stdout
            except Exception as e:
                log_debug(f"7zz read error: {e}")

        return None
