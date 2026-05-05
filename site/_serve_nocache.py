#!/usr/bin/env python3
"""Local dev server with aggressive no-cache headers. Run from site/."""
from http.server import SimpleHTTPRequestHandler, HTTPServer

class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

if __name__ == '__main__':
    HTTPServer(('', 8765), NoCacheHandler).serve_forever()
