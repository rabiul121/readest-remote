import argparse
import ctypes
from ctypes import wintypes
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The shared secret is loaded from ignored token.txt or READEST_REMOTE_TOKEN.
# Keep it private and enter the same value in the Android app.
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.txt")

def load_token():
    env_token = os.environ.get("READEST_REMOTE_TOKEN", "").strip()
    if env_token:
        return env_token
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8-sig") as token_file:
            configured = token_file.read().strip()
            return configured or "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
    except FileNotFoundError:
        return "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"

TOKEN = load_token()
HOST = "0.0.0.0"
PORT = 18765

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
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_size_t]
user32.keybd_event.restype = None
user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
user32.VkKeyScanW.restype = ctypes.c_short
user32.GetForegroundWindow.restype = wintypes.HWND
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
    # is about 45 CSS px above that edge. Move to the requested button to
    # reveal a faded pill, let its animation finish, then click once. Avoid a
    # separate reveal click: it can land on a control while the pill animates.
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
    if not move_readest_cursor(target_x, y_fraction):
        return False
    # The first move reveals the pill; allow its 200 ms fade/slide transition
    # to finish before aiming at the button.
    time.sleep(0.25)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
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
    valid_modes = {"normal", "autoscroll", "paragraph", "speed"}
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
            provided = self.headers.get("X-Remote-Token", "")
            if secrets.compare_digest(provided, TOKEN):
                self.send_json(200, {"ok": True, "service": "Readest Remote", "authenticated": True})
            else:
                self.send_json(401, {"ok": False, "error": "Unauthorized"})
        else:
            self.send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/turn":
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        provided = self.headers.get("X-Remote-Token", "")
        if not secrets.compare_digest(provided, TOKEN):
            self.send_json(401, {"ok": False, "error": "Unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 1024:
                raise ValueError("Invalid body size")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
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
        else:
            self.send_json(400, {"ok": False, "error": "Unknown action"})
            return

        self.send_json(200, {"ok": True, "action": action})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

if TOKEN == "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET":
    print("WARNING: Set a long random secret in token.txt before using this on your network.")

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
            self.server = ThreadingHTTPServer((HOST, PORT), Handler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        print(f"Readest Remote receiver listening on port {PORT}")
        print("Use your laptop's Wi-Fi IPv4 address in the Android app.")

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
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        raise SystemExit(f"Could not find pythonw.exe beside {sys.executable}")
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        raise SystemExit("Tray mode needs dependencies. Run: py -m pip install -r requirements.txt")

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

    def exit_app(icon, _item):
        controller.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _item: "Receiver running" if controller.running else "Receiver stopped", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Start receiver", lambda _icon, _item: controller.start(), enabled=lambda _item: not controller.running),
        pystray.MenuItem("Stop receiver", lambda _icon, _item: controller.stop(), enabled=lambda _item: controller.running),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", exit_app),
    )
    icon = pystray.Icon("Readest Remote", tray_image(), "Readest Remote receiver", menu)
    try:
        icon.run()
    finally:
        controller.stop()


def run_console():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Readest Remote receiver listening on port {PORT}")
    print("Use your laptop's Wi-Fi IPv4 address in the Android app.")
    print("Press Ctrl+C to stop. Keep this server on a trusted private network only.")
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
