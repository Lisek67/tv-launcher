#!/usr/bin/env python3
import io, json, os, re, shutil, subprocess, sys, time, hashlib, mimetypes, zipfile
import urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import remote
from remote import make_server, power   # power(): Linux (systemctl) i Windows (shutdown)

IS_WIN = os.name == 'nt'

PORT = 8765
ROOT = os.path.dirname(os.path.realpath(__file__))
IMG = os.path.join(ROOT, 'img')
CUSTOM = os.path.join(IMG, 'custom')
CONF = os.path.join(ROOT, 'config.json')
CONF_DEFAULT = os.path.join(ROOT, 'config.default.json')
HOSTS = {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}
ORIGINS = {f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'}
EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/svg+xml': 'svg'}
TD = '/usr/bin/timedatectl'
os.makedirs(CUSTOM, exist_ok=True)

def td(args, sudo=False):
    if IS_WIN:
        return False, 'niedostępne w Windows'
    cmd = (['sudo', '-n'] if sudo else []) + [TD] + args
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return p.returncode == 0, (p.stdout if p.returncode == 0 else (p.stderr or p.stdout)).strip()

_tz = []
def timezones():
    global _tz
    if not _tz:
        ok, out = td(['list-timezones'])
        _tz = out.split('\n') if ok else []
    return _tz

def park_cursor():
    """Przenosi kursor myszy w lewy dolny róg ekranu (nie ukrywa go). X11: xdotool, Wayland: ydotool."""
    if IS_WIN:
        try:
            import ctypes
            u = ctypes.windll.user32
            return bool(u.SetCursorPos(0, u.GetSystemMetrics(1) - 1))
        except Exception:
            return False
    env = dict(os.environ)
    env.setdefault('DISPLAY', ':0')
    if 'XAUTHORITY' not in env:
        xa = os.path.expanduser('~/.Xauthority')
        if os.path.exists(xa):
            env['XAUTHORITY'] = xa
    def run(cmd):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5, env=env)
    try:
        g = run(['xdotool', 'getdisplaygeometry'])
        if g.returncode == 0:
            w, h = g.stdout.split()
            if run(['xdotool', 'mousemove', '0', str(int(h) - 1)]).returncode == 0:
                return True
    except Exception:
        pass
    # Wayland: ydotool (ydotoold musi działać). Gniazdo na Archu: /run/user/UID/.ydotool_socket
    socks = [env.get('YDOTOOL_SOCKET'), os.path.join(env.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}', '.ydotool_socket'), '/tmp/.ydotool_socket']
    for sk in [x for x in socks if x and os.path.exists(x)] or [None]:
        try:
            e2 = dict(env)
            if sk:
                e2['YDOTOOL_SOCKET'] = sk
            ok = True
            for _ in range(3):  # kilka dużych ruchów względnych w lewo-dół; kursor zatrzyma się na rogu
                p = subprocess.run(['ydotool', 'mousemove', '-x', '-10000', '-y', '10000'], capture_output=True, timeout=5, env=e2)
                ok = ok and p.returncode == 0
            if ok:
                return True
        except Exception:
            pass
    return False

# ---------- ekran: rozdzielczość (GNOME / Mutter przez DBus) ----------
import threading
_disp_lock = threading.Lock()
_disp_timer = None
_disp_prev = None
REVERT_AFTER = 20

def _mutter():
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    px = Gio.DBusProxy.new_sync(bus, Gio.DBusProxyFlags.NONE, None, 'org.gnome.Mutter.DisplayConfig',
                                '/org/gnome/Mutter/DisplayConfig', 'org.gnome.Mutter.DisplayConfig', None)
    return px, GLib

def _state():
    px, GLib = _mutter()
    return px.call_sync('GetCurrentState', None, 0, 5000, None).unpack(), px, GLib

def _pick(monitors):
    for m in monitors:
        if m[0][0].startswith('HDMI'):
            return m
    return monitors[0]

def display_info(state):
    serial, monitors, lms, props = state
    if not monitors:
        raise ValueError('Nie wykryto monitora')
    m = _pick(monitors)
    modes, cur = [], None
    for (mid, w, h, rate, ps, scales, mp) in m[1]:
        d = {'id': mid, 'w': w, 'h': h, 'rate': round(rate, 2),
             'current': bool(mp.get('is-current')), 'preferred': bool(mp.get('is-preferred'))}
        modes.append(d)
        if d['current']:
            cur = d['id']
    return {'ok': True, 'connector': m[0][0], 'modes': modes, 'current': cur}

def plan_config(state, mode_id):
    """Zwraca (serial, logical_monitors) do ApplyMonitorsConfig: zmienia tryb tylko wybranego monitora."""
    serial, monitors, lms, props = state
    target = _pick(monitors)
    tconn = target[0][0]
    tmode = next((x for x in target[1] if x[0] == mode_id), None)
    if tmode is None:
        raise ValueError('Nieznany tryb ekranu')
    curmode = {}
    for m in monitors:
        cm = next((x for x in m[1] if x[6].get('is-current')), None)
        curmode[m[0][0]] = cm[0] if cm else None
    out = []
    for (x, y, scale, transform, primary, mons, lprops) in lms:
        conns = []
        for mon in mons:
            mid = mode_id if mon[0] == tconn else curmode.get(mon[0])
            if mid is not None:
                conns.append((mon[0], mid, {}))
        if not conns:
            continue
        if any(mon[0] == tconn for mon in mons) and not any(abs(scale - s) < 1e-6 for s in tmode[5]):
            scale = tmode[4]
        out.append((x, y, scale, transform, primary, conns))
    return serial, out

def apply_mode(mode_id, method):
    state, px, GLib = _state()
    serial, lms = plan_config(state, mode_id)
    v = GLib.Variant('(uua(iiduba(ssa{sv}))a{sv})', (serial, method, lms, {}))
    px.call_sync('ApplyMonitorsConfig', v, 0, 10000, None)

def _cancel_timer():
    global _disp_timer
    if _disp_timer:
        _disp_timer.cancel()
        _disp_timer = None

def _revert():
    global _disp_prev
    with _disp_lock:
        _cancel_timer()
        prev, _disp_prev = _disp_prev, None
        if prev:
            try:
                apply_mode(prev, 1)
            except Exception:
                pass

def _disp(fn):
    try:
        return fn()
    except ImportError:
        return {'ok': False, 'msg': 'Brak pakietu python-gobject (sudo pacman -S python-gobject)'}
    except Exception as e:
        return {'ok': False, 'msg': str(e)}

def display_get():
    def f():
        return display_info(_state()[0])
    return _disp(f)

def display_set(d):
    def f():
        global _disp_timer, _disp_prev
        mid = d.get('mode')
        with _disp_lock:
            info = display_info(_state()[0])
            if _disp_prev is None:
                _disp_prev = info['current']
            apply_mode(mid, 1)  # tymczasowo; zapis dopiero po potwierdzeniu
            _cancel_timer()
            _disp_timer = threading.Timer(REVERT_AFTER, _revert)
            _disp_timer.daemon = True
            _disp_timer.start()
        return {'ok': True, 'timeout': REVERT_AFTER}
    return _disp(f)

def display_confirm():
    def f():
        global _disp_prev
        with _disp_lock:
            _cancel_timer()
            _disp_prev = None
            apply_mode(display_info(_state()[0])['current'], 2)  # zapis na stałe
        return {'ok': True}
    return _disp(f)

def display_revert():
    _revert()
    return {'ok': True}

# ---------- wersja i aktualizacje (GitHub Releases) ----------
API = os.environ.get('TV_UPDATE_API', 'https://api.github.com')
PROTECT = {'config.json', 'remote.json'}        # dane użytkownika - aktualizacja ich nie rusza
SKIP_PREFIX = ('.git', 'backup/', '__pycache__/')
_upd = {'t': 0, 'data': None}

def version_info():
    try:
        with open(os.path.join(ROOT, 'version.json'), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'name': 'TV Launcher', 'version': '0.0.0', 'repo': '', 'creator': 'lissszek'}

def vtuple(v):
    nums = [int(x) for x in re.findall(r'\d+', re.split(r'[-+]', str(v).strip().lstrip('vV'))[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums)))

def http_get(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent': 'tv-launcher-updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Pobierany plik jest za duży')
    return data

def update_check(force=False):
    vi = version_info()
    cur, repo = str(vi.get('version', '0.0.0')), str(vi.get('repo', ''))
    out = {'current': cur, 'repo': repo, 'available': False}
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        out['error'] = 'Brak poprawnego repozytorium w version.json'
        return out
    if not force and _upd['data'] and _upd['data'].get('current') == cur and time.time() - _upd['t'] < 1800:
        return _upd['data']
    try:
        rel = json.loads(http_get(f'{API}/repos/{repo}/releases/latest', 2_000_000))
        tag = str(rel.get('tag_name', ''))
        out.update(latest=tag.lstrip('vV'), tag=tag, notes=(rel.get('body') or '').strip()[:6000],
                   url=rel.get('html_url', ''), available=vtuple(tag) > vtuple(cur))
    except urllib.error.HTTPError as e:
        out['error'] = 'Repozytorium nie ma jeszcze wydań' if e.code == 404 else f'GitHub zwrócił błąd {e.code}'
    except Exception:
        out['error'] = 'Brak połączenia z GitHub'
    _upd['t'], _upd['data'] = time.time(), out
    return out

def update_apply():
    info = update_check(force=True)
    if not info.get('available'):
        return {'ok': False, 'msg': info.get('error') or 'Masz już najnowszą wersję'}
    cur, repo, tag = info['current'], info['repo'], info['tag']
    data = http_get(f'{API}/repos/{repo}/zipball/{tag}', 60_000_000)
    z = zipfile.ZipFile(io.BytesIO(data))
    names = [n for n in z.namelist() if not n.endswith('/')]
    if not names:
        raise ValueError('Puste archiwum')
    top = names[0].split('/')[0] + '/'
    files = []
    for n in names:
        rel = n[len(top):] if n.startswith(top) else None
        parts = (rel or '').split('/')
        if not rel or rel.startswith('/') or '\\' in rel or '..' in parts or ':' in parts[0]:
            raise ValueError('Archiwum zawiera niedozwoloną ścieżkę')
        files.append((n, rel))
    rels = {r for _, r in files}
    for need in ('server.py', 'remote.py', 'app.html', 'version.json'):
        if need not in rels:
            raise ValueError(f'W archiwum brakuje pliku {need}')
    if vtuple(json.loads(z.read(top + 'version.json')).get('version', '0')) != vtuple(info['latest']):
        raise ValueError('Wersja w pliku version.json nie zgadza się z wydaniem')
    for n, rel in files:                       # zepsuty kod nie może zastąpić działającego
        if rel.endswith('.py'):
            compile(z.read(n), rel, 'exec')
    root = os.path.realpath(ROOT)
    staged = []
    for n, rel in files:
        if rel in PROTECT or rel.startswith(SKIP_PREFIX) or '/__pycache__/' in rel:
            continue
        dest = os.path.realpath(os.path.join(ROOT, rel))
        if not dest.startswith(root + os.sep):
            raise ValueError('Archiwum zawiera niedozwoloną ścieżkę')
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + '.new'
        with open(tmp, 'wb') as f:
            f.write(z.read(n))
        if os.path.exists(dest):
            bk = os.path.join(ROOT, 'backup', cur, rel)
            os.makedirs(os.path.dirname(bk), exist_ok=True)
            shutil.copy2(dest, bk)
            shutil.copymode(dest, tmp)
        elif rel.endswith('.sh'):
            os.chmod(tmp, 0o755)
        staged.append((tmp, dest))
    for tmp, dest in staged:
        os.replace(tmp, dest)
    return {'ok': True, 'version': info['latest']}

def restart_soon():
    def go():
        time.sleep(1.2)
        os.environ['TV_RESTARTED'] = '1'
        argv = [sys.executable, os.path.join(ROOT, 'server.py')] + sys.argv[1:]
        try:
            if IS_WIN:
                subprocess.Popen(argv, creationflags=0x00000008 | 0x00000200 | 0x08000000, cwd=ROOT)
                os._exit(0)
            os.execv(sys.executable, argv)
        except Exception:
            os._exit(0)      # nadzorca (systemd) uruchomi ponownie
    import threading
    threading.Thread(target=go, daemon=True).start()

def load_cfg():
    for p in (CONF, CONF_DEFAULT):
        try:
            with open(p, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _after_launch(tile):
    """Opcjonalnie: po uruchomieniu aplikacji natywnej naciśnij F11 (pełny ekran) po kilku sekundach."""
    if not (tile or {}).get('fullscreen'):
        return
    try:
        delay = max(1.0, min(30.0, float(tile.get('fsDelay', 5))))
    except (TypeError, ValueError):
        delay = 5.0
    import threading
    threading.Thread(target=lambda: (time.sleep(delay), remote.press('f11')), daemon=True).start()

def launch_app(tile_id):
    """Uruchamia zainstalowaną aplikację dla kafelka z polem 'cmd'. Polecenie pochodzi z zapisanej konfiguracji,
    nigdy z samego żądania, więc przez sieć nie da się uruchomić czegokolwiek innego."""
    tile = next((t for row in (load_cfg().get('rows') or []) for t in row if t.get('id') == tile_id), None)
    cmd = (tile or {}).get('cmd')
    if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 500:
        return {'ok': False, 'msg': 'Ten kafelek nie ma polecenia.'}
    try:
        if IS_WIN:
            p = subprocess.Popen(cmd, shell=True, cwd=os.path.expanduser('~'), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x00000008 | 0x00000200 | 0x08000000)
        else:
            env = remote.wl_env()
            env.setdefault('DISPLAY', ':0')
            p = subprocess.Popen(cmd, shell=True, env=env, cwd=os.path.expanduser('~'), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        return {'ok': False, 'msg': str(e)}
    try:
        code = p.wait(timeout=1.5)          # jeśli proces od razu się kończy, to zwykle błąd polecenia
    except subprocess.TimeoutExpired:
        _after_launch(tile)
        return {'ok': True}
    if code == 0:
        _after_launch(tile)
        return {'ok': True}
    return {'ok': False, 'msg': 'Nie znaleziono polecenia.' if code == 127 else f'Polecenie zakończyło się błędem (kod {code}).'}

def info_data():
    vi = version_info()
    return {'name': vi.get('name', 'TV Launcher'), 'version': vi.get('version', '0.0.0'), 'creator': vi.get('creator', 'lissszek'),
            'repo': vi.get('repo', ''), 'os': 'windows' if IS_WIN else 'linux', 'display': not IS_WIN, 'time': not IS_WIN,
            'ext_dir': os.path.join(ROOT, 'tv-ua'), 'home_key': 'Alt+Home'}

def _win_is_fullscreen(exe_name):
    """Windows: True/False, czy okno na wierzchu (jeśli to nasza przeglądarka) zajmuje cały monitor.
    None = na wierzchu jest coś innego (jeszcze nie wiadomo)."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    buf, n = ctypes.create_unicode_buffer(1040), wintypes.DWORD(1040)
    ok = k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n))
    k.CloseHandle(h)
    if not ok or os.path.basename(buf.value).lower() != exe_name.lower():
        return None
    class MONITORINFO(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
    rect = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    u.GetMonitorInfoW(u.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    m = mi.rcMonitor
    return rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom

def ensure_fullscreen(check, press, sleep=time.sleep, delays=(3, 3, 4, 5, 5, 5, 5)):
    """--start-fullscreen bywa ignorowane (np. przeglądarka już działa). F11 naciskamy tylko wtedy,
    gdy okno przeglądarki na pewno NIE jest pełnoekranowe, i najwyżej dwa razy (żeby go nie cofnąć)."""
    presses = 0
    for d in delays:
        sleep(d)
        st = check()
        if st is True:
            return True
        if st is False and presses < 2:
            press('f11')
            presses += 1
    return False

def open_browser():
    """Uruchamia przeglądarkę na pełnym ekranie z launcherem (opcja --browser, używana w autostarcie Windows)."""
    if os.environ.get('TV_RESTARTED'):
        return
    url = f'http://127.0.0.1:{PORT}/'
    exe = None
    if IS_WIN:
        pf, pf86, la = (os.environ.get(k, '') for k in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'))
        for p in (r'BraveSoftware\Brave-Browser\Application\brave.exe', r'Google\Chrome\Application\chrome.exe', r'Microsoft\Edge\Application\msedge.exe'):
            for base in (pf, pf86, la):
                if base and os.path.exists(os.path.join(base, p)):
                    exe = os.path.join(base, p)
                    break
            if exe:
                break
    else:
        for b in ('brave', 'brave-browser', 'chromium', 'google-chrome-stable', 'microsoft-edge-stable'):
            exe = shutil.which(b)
            if exe:
                break
    if exe:
        subprocess.Popen([exe, '--start-fullscreen', '--load-extension=' + os.path.join(ROOT, 'tv-ua'), url])
        if IS_WIN:
            name = os.path.basename(exe)
            ensure_fullscreen(lambda: _win_is_fullscreen(name), remote.press)

def lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except Exception:
        return ''
    finally:
        s.close()

def remote_info():
    import socket
    d = remote.load()
    up = False
    try:
        socket.create_connection(('127.0.0.1', remote.PORT), timeout=1).close()
        up = True
    except Exception:
        pass
    ip = lan_ip()
    return {'pin': d['pin'], 'devices': len(d['tokens']), 'up': up,
            'url': f'http://{ip or "IP-KOMPUTERA"}:{remote.PORT}'}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def out(self, code, body, ctype='application/json'):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def body(self, limit):
        n = int(self.headers.get('Content-Length') or 0)
        if n > limit:
            raise ValueError('Plik jest za duży')
        return self.rfile.read(n)

    def do_GET(self):
        if self.headers.get('Host') not in HOSTS:
            return self.out(403, {'error': 'host'})
        path = urlparse(self.path).path
        if path == '/ping':
            return self.out(200, b'ok', 'text/plain')
        if path in ('/', '/index.html'):
            with open(os.path.join(ROOT, 'app.html'), 'rb') as f:
                return self.out(200, f.read(), 'text/html; charset=utf-8')
        if path.startswith('/img/'):
            full = os.path.realpath(os.path.join(ROOT, path.lstrip('/')))
            if full.startswith(os.path.realpath(IMG) + os.sep) and os.path.isfile(full):
                with open(full, 'rb') as f:
                    return self.out(200, f.read(), mimetypes.guess_type(full)[0] or 'application/octet-stream')
            return self.out(404, {'error': 'brak'})
        if path == '/api/config':
            for p in (CONF, CONF_DEFAULT):
                try:
                    with open(p, encoding='utf-8') as f:
                        return self.out(200, json.load(f))
                except Exception:
                    pass
            return self.out(200, {})
        if path == '/api/info':
            return self.out(200, info_data())
        if path == '/api/update/check':
            force = parse_qs(urlparse(self.path).query).get('force') == ['1']
            return self.out(200, update_check(force))
        if path == '/api/remote':
            return self.out(200, remote_info())
        if path == '/api/display':
            return self.out(200, display_get())
        if path == '/api/time':
            if IS_WIN:
                return self.out(200, {})
            ok, out = td(['show', '-p', 'Timezone', '-p', 'NTP'])
            info = dict(l.split('=', 1) for l in out.split('\n') if '=' in l) if ok else {}
            now = subprocess.run(['date', '+%Y-%m-%dT%H:%M'], capture_output=True, text=True).stdout.strip()
            return self.out(200, {'timezone': info.get('Timezone', ''), 'ntp': info.get('NTP') == 'yes',
                                  'now': now, 'timezones': timezones()})
        self.out(404, {'error': 'brak'})

    def set_time(self, d):
        msgs, all_ok = [], True
        tz = d.get('timezone')
        if tz:
            if tz not in timezones():
                return {'ok': False, 'msg': 'Nieznana strefa czasowa'}
            ok, m = td(['set-timezone', tz], True)
            all_ok = all_ok and ok
            msgs.append('Strefa ustawiona' if ok else m)
        if d.get('ntp'):
            ok, m = td(['set-ntp', 'true'], True)
            all_ok = all_ok and ok
            msgs.append('Czas z internetu włączony' if ok else m)
        else:
            ok, m = td(['set-ntp', 'false'], True)
            all_ok = all_ok and ok
            msgs.append('Czas z internetu wyłączony' if ok else m)
            dt = d.get('datetime')
            if dt:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?', dt):
                    return {'ok': False, 'msg': 'Zły format daty'}
                ok, m = td(['set-time', dt], True)
                all_ok = all_ok and ok
                msgs.append('Czas ustawiony' if ok else m)
        return {'ok': all_ok, 'msg': '; '.join(msgs)}

    def do_POST(self):
        if self.headers.get('Host') not in HOSTS or self.headers.get('X-TV') != '1':
            return self.out(403, {'error': 'zabronione'})
        o = self.headers.get('Origin')
        if o is not None and o not in ORIGINS:
            return self.out(403, {'error': 'origin'})
        path = urlparse(self.path).path
        try:
            if path == '/api/config':
                data = json.loads(self.body(300_000))
                if not isinstance(data, dict):
                    raise ValueError('Zły format')
                tmp = CONF + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                os.replace(tmp, CONF)
                return self.out(200, {'ok': True})
            if path == '/api/icon':
                ext = EXT.get((self.headers.get('Content-Type') or '').split(';')[0].strip())
                if not ext:
                    raise ValueError('Obsługiwane formaty: JPG, PNG, WebP, SVG')
                data = self.body(8_000_000)
                name = hashlib.sha1(data).hexdigest()[:12] + '.' + ext
                with open(os.path.join(CUSTOM, name), 'wb') as f:
                    f.write(data)
                return self.out(200, {'path': 'img/custom/' + name})
            if path == '/api/display':
                return self.out(200, display_set(json.loads(self.body(10_000))))
            if path == '/api/display/confirm':
                return self.out(200, display_confirm())
            if path == '/api/display/revert':
                return self.out(200, display_revert())
            if path == '/api/park':
                return self.out(200, {'ok': park_cursor()})
            if path == '/api/launch':
                return self.out(200, launch_app(str(json.loads(self.body(2_000)).get('id', ''))))
            if path == '/api/update/apply':
                res = update_apply()
                if res.get('ok'):
                    restart_soon()
                return self.out(200, res)
            if path == '/api/remote/reset':
                remote.reset()
                return self.out(200, dict(remote_info(), ok=True))
            if path == '/api/power':
                return self.out(200, power(json.loads(self.body(1_000)).get('action')))
            if path == '/api/time':
                return self.out(200, self.set_time(json.loads(self.body(10_000))))
        except Exception as e:
            return self.out(400, {'ok': False, 'msg': str(e)})
        self.out(404, {'error': 'brak'})

if __name__ == '__main__':
    import threading
    def _remote():
        try:
            remote.serve()
        except Exception as e:      # np. port zajęty - launcher działa dalej bez pilota
            print('Pilot na telefon nie wystartował:', e, flush=True)
    threading.Thread(target=_remote, daemon=True).start()
    srv = make_server('127.0.0.1', PORT, H)
    if '--browser' in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()
    srv.serve_forever()
