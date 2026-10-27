import argparse
import ctypes
from ctypes import wintypes
import ipaddress
import json
import os
import secrets
import socket
import shutil
import subprocess
import sys
import tempfile
import winreg
import time
import threading
import hashlib
import ssl
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HOST = "0.0.0.0"
PORT = 18765
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "ReadestRemote")
CERT_FILE = os.path.join(DATA_DIR, "receiver-cert.pem")
KEY_FILE = os.path.join(DATA_DIR, "receiver-key.pem")
DEVICES_FILE = os.path.join(DATA_DIR, "paired_devices.json")
PAIR_LOCK = threading.Lock()
PAIRING = {"code": None, "expires": 0.0, "attempts": 0}

def ensure_identity():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CERT_FILE) or not os.path.exists(KEY_FILE):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Readest Remote receiver")])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]), critical=False)
                .sign(key, hashes.SHA256()))
        with open(KEY_FILE, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with open(CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    with open(CERT_FILE, "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    return fingerprint

def create_pairing_code():
    code = secrets.token_urlsafe(24)
    expires = time.time() + 180
    with PAIR_LOCK:
        PAIRING.update(code=code, expires=expires, attempts=0)
    return code, expires

def certificate_fingerprint():
    with open(CERT_FILE, "rb") as f:
        return x509.load_pem_x509_certificate(f.read()).fingerprint(hashes.SHA256()).hex()

def load_devices():
    try:
        with open(DEVICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_devices(devices):
    os.makedirs(DATA_DIR, exist_ok=True)
    temporary = DEVICES_FILE + ".tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(devices, f)
    os.replace(temporary, DEVICES_FILE)

def make_server():
    ensure_identity()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server

def local_ipv4_addresses():
    """Return LAN IPv4s, preferring the address Windows routes through."""
    addresses = []

    # UDP connect selects the active route without sending a packet. On a
    # phone hotspot this normally picks the laptop's hotspot-side address.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_probe:
            route_probe.connect(("192.0.2.1", 9))
            addresses.append(route_probe.getsockname()[0])
    except OSError:
        pass

    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
            addresses.append(result[4][0])
    except OSError:
        pass

    unique = []
    for address in addresses:
        try:
            parsed = ipaddress.IPv4Address(address)
        except ipaddress.AddressValueError:
            continue
        if parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified or parsed.is_multicast:
            continue
        value = str(parsed)
        if value not in unique:
            unique.append(value)
    return unique

def address_summary(addresses=None):
    if addresses is None:
        addresses = local_ipv4_addresses()
    if not addresses:
        return "No IPv4 address found"
    suffix = f" (+{len(addresses) - 1} more)" if len(addresses) > 1 else ""
    return f"{addresses[0]}:{PORT}{suffix}"

def copy_to_clipboard(text):
    if os.name != "nt":
        return False
    try:
        subprocess.run(
            ["clip.exe"], input=text, text=True, check=True, timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False

# Windows virtual-key codes
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_MENU = 0x12
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_ESCAPE = 0x1B
VK_J = 0x4A
VK_A = 0x41
VK_V = 0x56
VK_UP = 0x26
VK_DOWN = 0x28
VK_OEM_PLUS = 0xBB
VK_OEM_MINUS = 0xBD
VK_P = 0x50
VK_T = 0x54
VK_Q = 0x51
VK_F11 = 0x7A
VK_OEM_4 = 0xDB
VK_OEM_6 = 0xDD
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_size_t]
user32.keybd_event.restype = None
user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
user32.VkKeyScanW.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
user32.mouse_event.restype = None

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

def press_key(vk_code):
    # Send a normal key press to the currently focused Windows application.
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

def press_chord(*vk_codes):
    for vk_code in vk_codes:
        user32.keybd_event(vk_code, 0, 0, 0)
    for vk_code in reversed(vk_codes):
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)

def type_text(text):
    for char in text:
        mapped = user32.VkKeyScanW(char)
        if mapped == -1:
            raise ValueError(f"Cannot type character {char!r} using the active keyboard layout")
        mapped &= 0xFFFF
        vk_code = mapped & 0xFF
        modifiers = mapped >> 8
        if modifiers & 1:
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        if modifiers & 1:
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.012)

def foreground_is_readest(hwnd):
    if not hwnd:
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process:
        return False
    try:
        path = ctypes.create_unicode_buffer(32768)
        path_length = wintypes.DWORD(len(path))
        if not kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(path_length)):
            return False
        return os.path.basename(path.value).casefold() == "readest.exe"
    finally:
        kernel32.CloseHandle(process)

def readest_executable():
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Readest", "readest.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Readest", "readest.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Readest", "readest.exe"),
    ]
    located = shutil.which("readest.exe")
    if located:
        candidates.insert(0, located)
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\readest.exe") as key:
                registered, _ = winreg.QueryValueEx(key, None)
                candidates.insert(0, registered.strip('"'))
        except OSError:
            pass
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None

def readest_windows():
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd) and foreground_is_readest(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)
    return found

def launch_readest():
    windows = readest_windows()
    if windows:
        user32.ShowWindow(windows[0], SW_RESTORE)
        user32.SetForegroundWindow(windows[0])
        return True
    executable = readest_executable()
    if not executable:
        return False
    subprocess.Popen([executable], cwd=os.path.dirname(executable), close_fds=True)
    return True

def close_readest():
    windows = readest_windows()
    if not windows:
        return False
    # Use Readest's own Quit shortcut, as requested, instead of posting a
    # window-close message directly.
    user32.ShowWindow(windows[0], SW_RESTORE)
    user32.SetForegroundWindow(windows[0])
    time.sleep(0.08)
    press_chord(VK_CONTROL, VK_Q)
    return True

def refocus_reading_view():
    hwnd = user32.GetForegroundWindow()
    if not foreground_is_readest(hwnd):
        return False

    # The command palette leaves focus on its last toolbar selection. A click
    # in the reader viewport restores keyboard page-turn focus for later keys.
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return False
    point = wintypes.POINT((rect.right - rect.left) // 2, (rect.bottom - rect.top) // 2)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return False
    user32.SetForegroundWindow(hwnd)
    user32.SetCursorPos(point.x, point.y)
    time.sleep(0.04)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True

def move_readest_cursor(x_fraction, y_fraction):
    """Move the pointer to a point relative to the foreground Readest client."""
    hwnd = user32.GetForegroundWindow()
    if not foreground_is_readest(hwnd):
        return False
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return False
    point = wintypes.POINT(
        int((rect.right - rect.left) * x_fraction),
        int((rect.bottom - rect.top) * y_fraction),
    )
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return False
    return bool(user32.SetCursorPos(point.x, point.y))

def click_readest_client(x_fraction, y_fraction):
    """Click a point relative to the foreground Readest client area."""
    if not move_readest_cursor(x_fraction, y_fraction):
        return False
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True

def click_autoscroll_control(offset_from_center):
    # Readest's pill sits 24 CSS px above the reader area's bottom. Its center
    # is about 45 CSS px above that edge. Move away first so Windows generates
    # a fresh mouse-move event even when the pointer was already on the button;
    # that event reveals a faded pill. Then move to the target and click once.
    hwnd = user32.GetForegroundWindow()
    if not foreground_is_readest(hwnd):
        return False
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return False
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return False
    y_fraction = 1.0 - 45 / height
    target_x = 0.5 + offset_from_center / width
    if not move_readest_cursor(0.5, 0.5):
        return False
    time.sleep(0.25)
    if not move_readest_cursor(target_x, y_fraction):
        return False
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    # Let the bar's normal hide timer run after the remote click. If the pointer
    # stays over the pill, Readest intentionally keeps it visible while hovered.
    move_readest_cursor(0.5, 0.5)
    return True

def speed_reading_navigation(key, chapter=False):
    # RSVP captures Left/Right for WPM changes. Close the overlay before the
    # reader handles a page or chapter navigation key.
    press_key(VK_ESCAPE)
    time.sleep(0.18)
    if chapter:
        press_chord(VK_MENU, key)
    else:
        press_key(key)

def set_reading_mode(previous_mode, target_mode):
    valid_modes = {"normal", "autoscroll", "paragraph", "speed", "tts"}
    if previous_mode not in valid_modes or target_mode not in valid_modes:
        return False
    if not foreground_is_readest(user32.GetForegroundWindow()):
        return False

    # Always leave the current mode explicitly before entering another one.
    if previous_mode == "autoscroll":
        press_chord(VK_SHIFT, VK_A)
        time.sleep(0.15)
        press_chord(VK_SHIFT, VK_J)
        time.sleep(0.2)
    elif previous_mode == "paragraph":
        press_chord(VK_SHIFT, VK_P)
        time.sleep(0.2)
    elif previous_mode == "speed":
        press_key(VK_ESCAPE)
        time.sleep(0.25)
    elif previous_mode == "tts":
        press_key(VK_T)
        time.sleep(0.2)

    if target_mode == "autoscroll":
        # Auto Scroll is only active in scrolled layout.
        press_chord(VK_SHIFT, VK_J)
        time.sleep(0.25)
        press_chord(VK_SHIFT, VK_A)
    elif target_mode == "paragraph":
        press_chord(VK_SHIFT, VK_P)
    elif target_mode == "speed":
        press_chord(VK_SHIFT, VK_V)
        # If Readest offers its start-position dialog, choose option 3,
        # "From Current Page". With no dialog, this lands harmlessly in the
        # reader body after RSVP has started.
        time.sleep(0.5)
        click_readest_client(0.5, 0.61)
    elif target_mode == "tts":
        press_key(VK_T)
    return True

def cycle_readest_theme():
    # Readest exposes a Theme Mode action in its Ctrl+Shift+P command palette.
    press_chord(VK_CONTROL, VK_SHIFT, VK_P)
    time.sleep(0.25)
    type_text("Theme Mode")
    time.sleep(0.12)
    press_key(VK_RETURN)
    time.sleep(0.2)
    refocus_reading_view()

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True, "service": "Readest Remote"})
        elif self.path == "/verify":
            if self.authorized():
                self.send_json(200, {"ok": True, "service": "Readest Remote", "authenticated": True})
            else:
                self.send_json(401, {"ok": False, "error": "Unauthorized"})
        else:
            self.send_json(404, {"ok": False, "error": "Not found"})

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 2048:
            raise ValueError("Invalid body size")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        return data

    def authorized(self):
        device_id = self.headers.get("X-Device-Id", "")
        token = self.headers.get("X-Device-Token", "")
        record = load_devices().get(device_id, {})
        return bool(device_id and token and record.get("token_hash") and
                    secrets.compare_digest(hashlib.sha256(token.encode()).hexdigest(), record["token_hash"]))

    def do_POST(self):
        if self.path == "/pair":
            try:
                data = self.read_body()
                device_id = str(data.get("device_id", ""))[:100]
                code = str(data.get("pairing_code", ""))
                if not device_id:
                    raise ValueError("Missing device id")
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                self.send_json(400, {"ok": False, "error": "Invalid pairing request"})
                return
            with PAIR_LOCK:
                valid = (PAIRING["code"] is not None and time.time() < PAIRING["expires"] and
                         PAIRING["attempts"] < 5 and secrets.compare_digest(code, PAIRING["code"]))
                PAIRING["attempts"] += 1
                if valid:
                    PAIRING.update(code=None, expires=0.0, attempts=0)
            if not valid:
                self.send_json(401, {"ok": False, "error": "Pairing code is invalid or expired"})
                return
            token = secrets.token_urlsafe(32)
            devices = load_devices()
            devices[device_id] = {"token_hash": hashlib.sha256(token.encode()).hexdigest(),
                                  "name": str(data.get("device_name", "Android device"))[:80]}
            save_devices(devices)
            self.send_json(200, {"ok": True, "device_id": device_id, "device_token": token})
            return
        if self.path != "/turn":
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        if not self.authorized():
            self.send_json(401, {"ok": False, "error": "Unauthorized"})
            return

        try:
            data = self.read_body()
            action = data.get("action")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self.send_json(400, {"ok": False, "error": "Invalid JSON"})
            return

        if action == "set_mode":
            if not set_reading_mode(data.get("from_mode"), data.get("mode")):
                self.send_json(409, {"ok": False, "error": "Readest must be focused and mode names must be valid"})
                return
        elif action == "previous":
            press_key(VK_LEFT)
        elif action == "next":
            press_key(VK_RIGHT)
        elif action == "previous_chapter":
            press_chord(VK_MENU, VK_LEFT)
        elif action == "next_chapter":
            press_chord(VK_MENU, VK_RIGHT)
        elif action == "theme":
            cycle_readest_theme()
        elif action == "font_larger":
            press_chord(VK_CONTROL, VK_OEM_PLUS)
        elif action == "font_smaller":
            press_chord(VK_CONTROL, VK_OEM_MINUS)
        elif action == "font_reset":
            press_chord(VK_CONTROL, 0x30)  # Ctrl+0 resets Readest zoom.
        elif action == "fullscreen":
            windows = readest_windows()
            if not windows:
                self.send_json(409, {"ok": False, "error": "Readest is not running with an open window"})
                return
            user32.ShowWindow(windows[0], SW_RESTORE)
            user32.SetForegroundWindow(windows[0])
            time.sleep(0.08)
            press_key(VK_F11)
        elif action == "launch_readest":
            if not launch_readest():
                self.send_json(404, {"ok": False, "error": "Could not find Readest.exe in its usual install locations or App Paths"})
                return
        elif action == "close_readest":
            if not close_readest():
                self.send_json(409, {"ok": False, "error": "Readest is not running or has no open window"})
                return
        elif action == "enter_autoscroll":
            # Readest's Auto Scroll only runs in scrolled layout.
            press_chord(VK_SHIFT, VK_J)
            time.sleep(0.2)
            press_chord(VK_SHIFT, VK_A)
        elif action == "autoscroll_to_paragraph":
            press_chord(VK_SHIFT, VK_A)
            time.sleep(0.15)
            press_chord(VK_SHIFT, VK_J)
            time.sleep(0.15)
            press_chord(VK_SHIFT, VK_P)
        elif action == "paragraph_to_speed":
            press_chord(VK_SHIFT, VK_P)
            time.sleep(0.15)
            press_chord(VK_SHIFT, VK_V)
        elif action == "speed_to_normal":
            press_key(VK_ESCAPE)
        elif action == "autoscroll_pause":
            # A click in the reader pauses or resumes an active Auto Scroll session.
            click_readest_client(0.5, 0.5)
        elif action == "autoscroll_slower":
            if not click_autoscroll_control(-94):
                self.send_json(409, {"ok": False, "error": "Readest must be focused to adjust Auto Scroll speed"})
                return
        elif action == "autoscroll_faster":
            if not click_autoscroll_control(0):
                self.send_json(409, {"ok": False, "error": "Readest must be focused to adjust Auto Scroll speed"})
                return
        elif action == "speed_pause":
            press_key(0x20)  # Space toggles RSVP playback.
        elif action == "speed_slower":
            press_key(VK_DOWN)
        elif action == "speed_faster":
            press_key(VK_UP)
        elif action == "rsvp_previous":
            speed_reading_navigation(VK_LEFT)
        elif action == "rsvp_next":
            speed_reading_navigation(VK_RIGHT)
        elif action == "rsvp_previous_chapter":
            speed_reading_navigation(VK_LEFT, chapter=True)
        elif action == "rsvp_next_chapter":
            speed_reading_navigation(VK_RIGHT, chapter=True)
        elif action == "tts_toggle" or action == "tts_close":
            press_key(VK_T)
        elif action == "tts_pause":
            press_key(0x20)  # Space toggles TTS playback.
        elif action == "tts_previous":
            press_chord(VK_CONTROL, VK_OEM_4)
        elif action == "tts_next":
            press_chord(VK_CONTROL, VK_OEM_6)
        else:
            self.send_json(400, {"ok": False, "error": "Unknown action"})
            return

        self.send_json(200, {"ok": True, "action": action})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

class ServerController:
    def __init__(self):
        self.server = None
        self.thread = None
        self.lock = threading.Lock()

    @property
    def running(self):
        return self.server is not None

    def start(self):
        with self.lock:
            if self.server is not None:
                return
            self.server = make_server()
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        print(f"Readest Remote receiver listening on port {PORT}")
        addresses = local_ipv4_addresses()
        print(f"Use {addresses[0]} in the Android app." if addresses else "Could not detect a laptop IPv4 address.")

    def stop(self):
        with self.lock:
            server = self.server
            thread = self.thread
            self.server = None
            self.thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
            if thread is not None:
                thread.join(timeout=2)
            print("Readest Remote receiver stopped.")


def startup_script_path():
    startup_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    )
    return os.path.join(startup_dir, "Readest Remote.vbs")


def install_startup():
    if os.name != "nt":
        raise SystemExit("Automatic startup is supported on Windows only.")
    if getattr(sys, "frozen", False):
        command = subprocess.list2cmdline([sys.executable, "--tray"])
    else:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pythonw):
            raise SystemExit(f"Could not find pythonw.exe beside {sys.executable}")
        try:
            import pystray  # noqa: F401
            import qrcode  # noqa: F401
            from PIL import Image  # noqa: F401
            import cryptography  # noqa: F401
        except ImportError:
            raise SystemExit("Receiver dependencies are missing. Run setup_receiver.bat.")
        command = subprocess.list2cmdline([pythonw, os.path.abspath(__file__), "--tray"])
    vbs_command = command.replace('"', '""')
    script = (
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.Run "{vbs_command}", 0, False\r\n'
    )
    path = startup_script_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(script)
    print(f"Installed per-user auto-start shortcut: {path}")
    print("The receiver will start in the notification area after your next sign-in.")


def remove_startup():
    path = startup_script_path()
    if os.path.exists(path):
        os.remove(path)
        print("Removed Readest Remote from Windows auto-start.")
    else:
        print("Readest Remote auto-start is not installed.")


def tray_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (24, 54, 95, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 9, 57, 55), radius=8, fill=(248, 250, 255, 255))
    draw.polygon([(12, 17), (31, 21), (31, 48), (12, 44)], fill=(36, 74, 124, 255))
    draw.polygon([(34, 21), (52, 17), (52, 44), (34, 48)], fill=(36, 74, 124, 255))
    draw.line((32, 21, 32, 49), fill=(248, 250, 255, 255), width=2)
    draw.polygon([(25, 27), (18, 34), (25, 41), (25, 37), (34, 37), (34, 32), (25, 32)], fill=(255, 200, 87, 255))
    return image


def run_tray():
    if os.name != "nt":
        raise SystemExit("Tray mode is supported on Windows only.")
    try:
        import pystray
    except ImportError:
        raise SystemExit("Tray mode needs dependencies. Run: py -m pip install -r requirements.txt")

    controller = ServerController()
    controller.start()
    address_cache = {"items": local_ipv4_addresses()}

    def refresh_addresses():
        address_cache["items"] = local_ipv4_addresses()
        return address_cache["items"]

    def exit_app(icon, _item):
        controller.stop()
        icon.stop()

    def refresh_address(icon, _item):
        addresses = refresh_addresses()
        current = address_summary(addresses)
        icon.title = f"Readest Remote · {current}"
        icon.update_menu()
        try:
            icon.notify(f"Current receiver address: {current}", "Readest Remote")
        except Exception:
            pass

    def show_manual_address(icon, _item):
        addresses = refresh_addresses()
        preferred = addresses[0] if addresses else "No IPv4 address detected"
        all_addresses = "\n".join(addresses) if addresses else "Check your Wi-Fi connection."
        code, expires = create_pairing_code()
        message = (
            f"Preferred laptop IP: {preferred}\nPort: {PORT}\n\n"
            f"Temporary pairing code (valid 3 minutes):\n{code}\n\n"
            f"Receiver certificate SHA-256:\n{certificate_fingerprint()}\n\n"
            "Enter these values in Android Connection settings.\n\n"
            f"Detected IPv4 addresses:\n{all_addresses}"
        )
        icon.title = f"Readest Remote · {address_summary(addresses)}"
        icon.update_menu()
        ctypes.windll.user32.MessageBoxW(None, message, "Readest Remote · Manual connection", 0x40)

    def copy_primary_ip(icon, _item):
        addresses = refresh_addresses()
        icon.title = f"Readest Remote · {address_summary(addresses)}"
        if not addresses:
            message = "No IPv4 address is available to copy."
        elif copy_to_clipboard(addresses[0]):
            message = f"Copied {addresses[0]} to the clipboard. Port: {PORT}."
        else:
            message = "Could not copy the address to the clipboard."
        try:
            icon.notify(message, "Readest Remote")
        except Exception:
            print(message)

    def copy_all_ips(icon, _item):
        addresses = refresh_addresses()
        icon.title = f"Readest Remote · {address_summary(addresses)}"
        message = "No IPv4 addresses are available." if not addresses else (
            "Copied all IPv4 addresses." if copy_to_clipboard("\r\n".join(addresses))
            else "Could not copy the addresses to the clipboard."
        )
        try:
            icon.notify(message, "Readest Remote")
        except Exception:
            print(message)

    def revoke_all_devices(icon, _item):
        answer = ctypes.windll.user32.MessageBoxW(
            None, "This will disconnect every paired phone. Continue?", "Revoke paired phones", 0x24
        )
        if answer == 6:
            save_devices({})
            try:
                icon.notify("All paired phone credentials have been revoked.", "Readest Remote")
            except Exception:
                pass

    def show_pairing_qr(icon, _item):
        addresses = refresh_addresses()
        if not addresses:
            try:
                icon.notify("No laptop IPv4 address is available.", "Readest Remote")
            except Exception:
                pass
            return
        host = addresses[0]
        icon.title = f"Readest Remote · {host}:{PORT}"
        code, expires = create_pairing_code()
        payload = json.dumps({
            "type": "readest-remote-pairing",
            "version": 2,
            "host": host,
            "port": PORT,
            "fingerprint": certificate_fingerprint(),
            "pairing_code": code,
            "expires_at": int(expires),
        }, separators=(",", ":"))
        try:
            import qrcode
            from PIL import Image, ImageDraw, ImageFont

            qr = qrcode.QRCode(box_size=10, border=4)
            qr.add_data(payload)
            qr.make(fit=True)
            qr_image = qr.make_image(fill_color="#14233b", back_color="white").convert("RGB")
            canvas_width = max(480, qr_image.width + 40)
            canvas = Image.new("RGB", (canvas_width, qr_image.height + 118), "white")
            draw = ImageDraw.Draw(canvas)
            font = ImageFont.load_default()
            draw.text((20, 16), "Readest Remote pairing", fill="#14233b", font=font)
            draw.text((20, 38), f"Laptop IP: {host}    Port: {PORT}", fill="#14233b", font=font)
            draw.text((20, 60), "One-time code expires in 3 minutes; TLS certificate is pinned.", fill="#14233b", font=font)
            canvas.paste(qr_image, ((canvas_width - qr_image.width) // 2, 88))
            path = os.path.join(tempfile.gettempdir(), f"readest_remote_pairing_{os.getpid()}.png")
            canvas.save(path)
            os.startfile(path)
            try:
                icon.notify("One-time pairing QR opened. It expires in 3 minutes.", "Readest Remote")
            except Exception:
                pass
        except ImportError:
            try:
                icon.notify("QR support is missing. Run: py -m pip install -r requirements.txt", "Readest Remote")
            except Exception:
                print("QR support is missing. Install requirements.txt.")
        except OSError as error:
            try:
                icon.notify(f"Could not open pairing QR: {error}", "Readest Remote")
            except Exception:
                print(f"Could not open pairing QR: {error}")

    menu = pystray.Menu(
        pystray.MenuItem(lambda _item: "Receiver running" if controller.running else "Receiver stopped", None, enabled=False),
        pystray.MenuItem(lambda _item: f"Laptop address: {address_summary(address_cache['items'])}", None, enabled=False),
        pystray.MenuItem("Refresh IP address", refresh_address),
        pystray.MenuItem("Show IP for manual entry", show_manual_address),
        pystray.MenuItem("Copy laptop IP", copy_primary_ip, enabled=lambda _item: bool(address_cache["items"])),
        pystray.MenuItem("Copy all IPv4 addresses", copy_all_ips, enabled=lambda _item: bool(address_cache["items"])),
        pystray.MenuItem("Show pairing QR", show_pairing_qr, enabled=lambda _item: bool(address_cache["items"])),
        pystray.MenuItem("Revoke all paired phones", revoke_all_devices),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start receiver", lambda _icon, _item: controller.start(), enabled=lambda _item: not controller.running),
        pystray.MenuItem("Stop receiver", lambda _icon, _item: controller.stop(), enabled=lambda _item: controller.running),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", exit_app),
    )
    icon = pystray.Icon("Readest Remote", tray_image(), f"Readest Remote · {address_summary(address_cache['items'])}", menu)
    try:
        icon.run()
    finally:
        controller.stop()


def run_console():
    server = make_server()
    print(f"Readest Remote receiver listening on port {PORT}")
    print("HTTPS receiver ready. Open the tray menu and show a pairing QR.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping receiver...")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Readest Remote Windows receiver")
    parser.add_argument("--tray", action="store_true", help="run with a Windows notification-area icon")
    parser.add_argument("--install-startup", action="store_true", help="start in the tray at Windows sign-in")
    parser.add_argument("--remove-startup", action="store_true", help="remove the per-user auto-start shortcut")
    args = parser.parse_args()

    if args.install_startup:
        install_startup()
    elif args.remove_startup:
        remove_startup()
    elif args.tray:
        run_tray()
    else:
        run_console()
