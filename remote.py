#!/usr/bin/env python3
"""Pilot na telefon: osobny serwer w sieci lokalnej (port 8766), parowanie kodem PIN.
Wstrzykuje klawisze/mysz przez ydotool (działa na Waylandzie)."""
import hmac, json, os, secrets, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

IS_WIN = os.name == 'nt'
NOWIN = 0x08000000 if IS_WIN else 0   # CREATE_NO_WINDOW
PORT = 8766
ROOT = os.path.dirname(os.path.realpath(__file__))
STATE = os.path.join(ROOT, 'remote.json')
_lock = threading.Lock()


def _save(d):
    tmp = STATE + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(d, f)
    os.replace(tmp, STATE)


def new_state():
    return {'pin': '%06d' % secrets.randbelow(10 ** 6), 'tokens': []}


def load():
    with _lock:
        try:
            with open(STATE) as f:
                d = json.load(f)
            if isinstance(d.get('pin'), str) and isinstance(d.get('tokens'), list):
                return d
        except Exception:
            pass
        d = new_state()
        _save(d)
        return d


def reset():
    with _lock:
        d = new_state()
        _save(d)
        return d


def add_token():
    with _lock:
        try:
            with open(STATE) as f:
                d = json.load(f)
        except Exception:
            d = new_state()
        t = secrets.token_urlsafe(24)
        d['tokens'] = (d.get('tokens') or [])[-9:] + [t]
        _save(d)
        return t


# ---------- wstrzykiwanie wejścia ----------
# Linux/Wayland: ydotool (kody klawiszy evdev). Windows: SendInput (ctypes).
KEYS = {
    'up': [103], 'down': [108], 'left': [105], 'right': [106], 'ok': [28], 'enter': [28],
    'back': [1],                 # Esc
    'home': [56, 102],           # Alt+Home -> rozszerzenie wraca do launchera
    'play': [164], 'next': [163], 'prev': [165],
    'vup': [115], 'vdown': [114], 'mute': [113],
    'backspace': [14], 'tab': [15], 'space': [57],
}
# Windows: (kod VK, czy klawisz rozszerzony)
WKEYS = {
    'up': [(0x26, 1)], 'down': [(0x28, 1)], 'left': [(0x25, 1)], 'right': [(0x27, 1)],
    'ok': [(0x0D, 0)], 'enter': [(0x0D, 0)], 'back': [(0x1B, 0)],
    'home': [(0x12, 0), (0x24, 1)],
    'play': [(0xB3, 0)], 'next': [(0xB0, 0)], 'prev': [(0xB1, 0)],
    'vup': [(0xAF, 0)], 'vdown': [(0xAE, 0)], 'mute': [(0xAD, 0)],
    'backspace': [(0x08, 0)], 'tab': [(0x09, 0)], 'space': [(0x20, 0)],
}
ACTIONS = ('suspend', 'reboot', 'poweroff')


def yd(args):
    env = dict(os.environ)
    rt = env.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    socks = [env.get('YDOTOOL_SOCKET'), os.path.join(rt, '.ydotool_socket'), '/tmp/.ydotool_socket']
    for sk in [x for x in socks if x and os.path.exists(x)] or [None]:
        e = dict(env)
        if sk:
            e['YDOTOOL_SOCKET'] = sk
        try:
            if subprocess.run(['ydotool'] + args, capture_output=True, timeout=5, env=e).returncode == 0:
                return True
        except Exception:
            pass
    return False


if IS_WIN:
    import ctypes
    from ctypes import wintypes
    _PUL = ctypes.POINTER(ctypes.c_ulong)

    class _KI(ctypes.Structure):
        _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                    ('time', wintypes.DWORD), ('dwExtraInfo', _PUL)]

    class _MI(ctypes.Structure):
        _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                    ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', _PUL)]

    class _IU(ctypes.Union):
        _fields_ = [('ki', _KI), ('mi', _MI)]

    class _INPUT(ctypes.Structure):
        _fields_ = [('type', wintypes.DWORD), ('u', _IU)]

    def _send(items):
        arr = (_INPUT * len(items))(*items)
        return ctypes.windll.user32.SendInput(len(items), arr, ctypes.sizeof(_INPUT)) == len(items)

    def _kb(vk=0, scan=0, flags=0):
        i = _INPUT(); i.type = 1
        i.u.ki = _KI(vk, scan, flags, 0, None)
        return i

    def _ms(dx=0, dy=0, data=0, flags=0):
        i = _INPUT(); i.type = 0
        i.u.mi = _MI(dx, dy, data & 0xFFFFFFFF, flags, 0, None)
        return i


def press(name):
    """Naciśnij i puść klawisz (lub kombinację) o nazwie z KEYS."""
    if IS_WIN:
        seq = WKEYS.get(name)
        if not seq:
            return False
        ext = lambda e: 0x0001 if e else 0
        down = [_kb(vk, 0, ext(e)) for vk, e in seq]
        up = [_kb(vk, 0, ext(e) | 0x0002) for vk, e in reversed(seq)]
        return _send(down + up)
    codes = KEYS.get(name)
    if not codes:
        return False
    return yd(['key'] + [f'{c}:1' for c in codes] + [f'{c}:0' for c in reversed(codes)])


def mouse_move(dx, dy):
    if IS_WIN:
        return _send([_ms(dx, dy, 0, 0x0001)])
    return yd(['mousemove', '-x', str(dx), '-y', str(dy)])


def mouse_click(right=False):
    if IS_WIN:
        d, u = (0x0008, 0x0010) if right else (0x0002, 0x0004)
        return _send([_ms(0, 0, 0, d), _ms(0, 0, 0, u)])
    return yd(['click', '0xC1' if right else '0xC0'])


def mouse_scroll(n):
    if IS_WIN:
        return _send([_ms(0, 0, n * 120, 0x0800)])
    return yd(['mousemove', '-w', '-x', '0', '-y', str(n)])


def wl_env():
    e = dict(os.environ)
    rt = e.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
    e['XDG_RUNTIME_DIR'] = rt
    if 'WAYLAND_DISPLAY' not in e:
        try:
            for n in sorted(os.listdir(rt)):
                if n.startswith('wayland-') and not n.endswith('.lock'):
                    e['WAYLAND_DISPLAY'] = n
                    break
        except Exception:
            pass
    return e


def send_text(t):
    t = t[:500]
    if not t:
        return True
    if IS_WIN:   # znaki Unicode (w tym polskie) wprost, bez schowka
        units = t.encode('utf-16-le')
        items = []
        for i in range(0, len(units), 2):
            u = int.from_bytes(units[i:i + 2], 'little')
            items += [_kb(0, u, 0x0004), _kb(0, u, 0x0004 | 0x0002)]
        return _send(items)
    if t.isascii():
        return yd(['type', '--', t])
    # polskie znaki: schowek + Ctrl+V (wymaga wl-clipboard); awaryjnie ydotool type
    try:
        p = subprocess.run(['wl-copy', '--', t], env=wl_env(), stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        if p.returncode == 0:
            time.sleep(0.15)
            return yd(['key', '29:1', '47:1', '47:0', '29:0'])
    except Exception:
        pass
    return yd(['type', '--', t])


def power(action):
    if action not in ACTIONS:
        return {'ok': False, 'msg': 'Nieznana akcja'}
    if IS_WIN:
        cmd = {'poweroff': ['shutdown', '/s', '/t', '0'], 'reboot': ['shutdown', '/r', '/t', '0'],
               'suspend': ['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0']}[action]
        try:
            subprocess.Popen(cmd, creationflags=NOWIN)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'msg': str(e)}
    err = ''
    for cmd in (['/usr/bin/systemctl', '--no-ask-password', action], ['sudo', '-n', '/usr/bin/systemctl', action]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                return {'ok': True}
            err = (p.stderr or p.stdout).strip()
        except Exception as e:
            err = str(e)
    return {'ok': False, 'msg': err or 'Brak uprawnień'}


def clamp(v, lim):
    return max(-lim, min(lim, int(v)))


# ---------- serwer ----------
_fails = {}   # ip -> (liczba błędów, blokada do)


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    disable_nagle_algorithm = True

    def log_message(self, *a):
        pass

    def out(self, code, body, ctype='application/json', headers=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit=2000):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('za duże')
        return json.loads(self.rfile.read(n) or b'{}')

    def authed(self):
        ck = self.headers.get('Cookie') or ''
        tok = ''
        for part in ck.split(';'):
            k, _, v = part.strip().partition('=')
            if k == 'tvr':
                tok = v
        return bool(tok) and any(hmac.compare_digest(tok, t) for t in load()['tokens'])

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            with open(os.path.join(ROOT, 'remote.html'), 'rb') as f:
                return self.out(200, f.read(), 'text/html; charset=utf-8')
        if path == '/api/me':
            return self.out(200, {'ok': self.authed()})
        self.out(404, {'error': 'brak'})

    def do_POST(self):
        if self.headers.get('X-TV') != '1':
            return self.out(403, {'error': 'zabronione'})
        o = self.headers.get('Origin')
        if o is not None and o != 'http://' + (self.headers.get('Host') or ''):
            return self.out(403, {'error': 'origin'})
        path = urlparse(self.path).path
        try:
            d = self.body()
            if path == '/auth':
                ip = self.client_address[0]
                n, until = _fails.get(ip, (0, 0))
                if time.time() < until:
                    return self.out(429, {'ok': False, 'msg': 'Za dużo prób. Poczekaj chwilę.'})
                if hmac.compare_digest(str(d.get('pin', '')), load()['pin']):
                    _fails.pop(ip, None)
                    tok = add_token()
                    return self.out(200, {'ok': True}, headers={
                        'Set-Cookie': f'tvr={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000'})
                n += 1
                _fails[ip] = (n, time.time() + (60 if n >= 5 else 0))
                return self.out(403, {'ok': False, 'msg': 'Zły PIN'})
            if not self.authed():
                return self.out(401, {'ok': False, 'msg': 'Wymagane parowanie'})
            if path == '/api/key':
                return self.out(200, {'ok': press(str(d.get('k')))})
            if path == '/api/move':
                return self.out(200, {'ok': mouse_move(clamp(d.get('dx', 0), 600), clamp(d.get('dy', 0), 600))})
            if path == '/api/click':
                return self.out(200, {'ok': mouse_click(d.get('b') == 'r')})
            if path == '/api/scroll':
                return self.out(200, {'ok': mouse_scroll(clamp(d.get('dy', 0), 20))})
            if path == '/api/text':
                return self.out(200, {'ok': send_text(str(d.get('t', '')))})
            if path == '/api/power':
                return self.out(200, power(d.get('action')))
        except Exception as e:
            return self.out(400, {'ok': False, 'msg': str(e)})
        self.out(404, {'error': 'brak'})


class Srv(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not IS_WIN


def make_server(host, port, handler, tries=40):
    """Po restarcie (aktualizacja) stary proces może jeszcze chwilę trzymać port - ponawiamy."""
    for i in range(tries):
        try:
            return Srv((host, port), handler)
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(0.5)


def serve():
    load()
    make_server('0.0.0.0', PORT, H).serve_forever()


if __name__ == '__main__':
    serve()
