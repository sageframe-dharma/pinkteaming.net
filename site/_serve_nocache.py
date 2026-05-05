#!/usr/bin/env python3
"""Local dev server with no-cache headers AND HTTP Range support.

Python's stock SimpleHTTPRequestHandler doesn't support Range requests, which
means audio.currentTime = X triggers a full re-download from byte 0 — and the
browser plays from 0 while waiting. Production (Cloudflare Pages) supports
ranges natively. This serves the same way locally.
"""
import os
import re
from http.server import SimpleHTTPRequestHandler, HTTPServer

class NoCacheRangeHandler(SimpleHTTPRequestHandler):

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            file_size = fs.st_size
            ctype = self.guess_type(path)
            range_header = self.headers.get('Range')

            if range_header:
                m = re.match(r'bytes=(\d+)-(\d*)$', range_header)
                if m:
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else file_size - 1
                    if start >= file_size:
                        self.send_error(416, 'Range Not Satisfiable')
                        f.close()
                        return None
                    end = min(end, file_size - 1)
                    length = end - start + 1
                    self.send_response(206)
                    self.send_header('Content-Type', ctype)
                    self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                    self.send_header('Content-Length', str(length))
                    self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
                    self.end_headers()
                    f.seek(start)
                    # Return a partial file wrapper
                    return _PartialFile(f, length)

            # No Range — full file
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise


class _PartialFile:
    """File-like wrapper that only yields up to `length` bytes."""
    def __init__(self, f, length):
        self.f = f
        self.remaining = length
    def read(self, size=-1):
        if self.remaining <= 0:
            return b''
        if size is None or size < 0 or size > self.remaining:
            size = self.remaining
        data = self.f.read(size)
        self.remaining -= len(data)
        return data
    def close(self):
        self.f.close()


if __name__ == '__main__':
    HTTPServer(('', 8765), NoCacheRangeHandler).serve_forever()
