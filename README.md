# Readest Remote (Android + Windows receiver)

A minimal Wi-Fi remote for turning pages in Readest on Windows. The Android app sends `previous` or `next` commands to a small Python server on your laptop. The receiver sends Left/Right arrow keys to the currently focused Windows app.

## What you need

- Windows 10 laptop with Readest installed
- Android phone on the same Wi-Fi network
- Python 3 on Windows
- Android Studio on a development computer to build the APK

## 1. Start the Windows receiver

1. Install Python 3 from https://www.python.org/downloads/windows/ if needed. During installation, select **Add python.exe to PATH**.
2. Open the `windows-receiver` folder.
3. The receiver reads its shared secret from `windows-receiver/token.txt` (or the `READEST_REMOTE_TOKEN` environment variable). On a fresh checkout, generate the file from the `windows-receiver` folder with:

   ```bat
   py -c "import secrets; print(secrets.token_urlsafe(32))" > token.txt
   ```

   Enter the contents of `token.txt` in the Android app. Keep this file private; it is excluded from Git. The current local token file is preserved when updating this checkout.
4. To run the receiver in a console, open PowerShell in that folder and run:

   ```bat
   py receiver.py
   ```

   The receiver listens on port `18765`. Find your laptop's Wi-Fi IPv4 address by running `ipconfig` in another Command Prompt and looking for **IPv4 Address** under the active Wi-Fi adapter (for example `192.168.1.25`).

If Windows Firewall asks, allow Python on **Private networks only**. Do not expose/forward this port to the internet.

### Run in the notification area and start with Windows

Install the tray icon dependencies once:

```bat
py -m pip install -r requirements.txt
```

To run it in the Windows notification area now:

```bat
pyw receiver.py --tray
```

Right-click the Readest Remote tray icon to stop/start the receiver or exit. To launch it automatically at your next Windows sign-in, install a per-user Startup shortcut:

```bat
py receiver.py --install-startup
```

The shortcut starts the tray version without a console window. Remove it with `py receiver.py --remove-startup`. Tray mode uses `pythonw.exe`, so if Firewall asks again, allow that Python executable on **Private networks only** too. Auto-start is opt-in; the install command does not run automatically.

## 2. Build the Android release APK

1. Install Android Studio: https://developer.android.com/studio
2. Extract/open the `android-app` folder in Android Studio.
3. Let Gradle sync and install any SDK components Android Studio requests.
4. In Android Studio's Gradle tool window, run `:app:assembleRelease` (or run `gradle assembleRelease` from `android-app`).
5. The release APK is generated at:

   `app/build/outputs/apk/release/app-release.apk`

6. To use the requested filename, copy it in PowerShell from `android-app`:

   ```powershell
   Copy-Item .\app\build\outputs\apk\release\app-release.apk .\app\build\outputs\apk\release\readest_remote.apk -Force
   ```

7. Copy `app/build/outputs/apk/release/readest_remote.apk` to your phone and install it. This locally installable build uses the machine's Android debug signing key; use a private release key before distributing through an app store. Android may ask you to allow installs from that file manager/browser.

## 3. Connect and use it

1. Keep the laptop and phone on the same Wi-Fi network. Some guest Wi-Fi networks block device-to-device connections.
2. Start `receiver.py` on the laptop.
3. Open Readest and open a book. Click once inside the reading area so Readest is focused.
4. Open Readest Remote on Android.
5. On first launch, enter the laptop's Wi-Fi IPv4 address, port `18765`, and the same secret as `TOKEN` in `receiver.py`.
6. Tap **Save pairing**, then **Test connection**. The test checks both network access and the secret. The app stores the secret encrypted with Android Keystore. On later launches, pairing opens from the settings icon.
7. Use the page and chapter buttons. Hold either page button to repeat. Keep Readest focused on the laptop.

The Android app supports Auto, Day, and Night appearance; tap the sun/moon icon to cycle modes. The four labeled reading-mode buttons select Normal, Auto Scroll, Paragraph, or Speed Reading. Tap the active mode again to return to Normal; choosing another mode first turns off the current one. Auto Scroll switches Readest to scrolled layout before starting. Its controls adjust speed, pause/resume, and turn pages or chapters. Speed Reading uses its WPM controls, play/pause, and page/chapter navigation. The **A−** and **A+** buttons adjust the laptop reader's font size (reflowable books) with Readest's `Ctrl+-` and `Ctrl+=` shortcuts. When Readest asks where to begin Speed Reading, the receiver chooses **From Current Page**. Keep Readest focused on the laptop while using the remote. Auto Scroll speed controls click Readest's floating control pill near the bottom center of the reader window, so keep the laptop display unobstructed and the reader window in its usual layout.

The mode buttons control Readest on the laptop, not the phone's own display. The remote opens with Normal selected and remembers the last mode successfully sent to the receiver so it can turn that mode off before switching. Tap any active non-Normal mode again, or tap Normal, to return to Normal. If you change modes directly in Readest, its actual mode can differ from the remote's remembered mode; return Readest to Normal before continuing with the phone. Switching into Auto Scroll assumes Readest starts in paginated mode because `Shift+J` toggles the layout. If Readest is already scrolled, first switch it to paginated mode in Readest.

The remote follows Readest's documented shortcuts: `Shift+J` toggles scrolled layout, `Shift+A` toggles Auto Scroll, `Shift+P` toggles paragraph mode, and `Shift+V` starts Speed Reading. In Speed Reading, Space toggles playback and Up/Down changes WPM. Page and chapter navigation closes the RSVP overlay before sending the navigation key; the Android mode indicator resets to Normal afterward. If the receiver file was updated while tray mode was running, restart the receiver so it loads the new actions. See [Readest Reading docs](https://readest.com/docs/reading), [Advanced keyboard shortcuts](https://readest.com/docs/advanced), and [Customization](https://readest.com/docs/customization).

Readest's default shortcuts are Left Arrow for previous page and Right Arrow for next page. Chapter turns use `Alt+Left` and `Alt+Right`. Readest also lets you customize keyboard bindings under Settings → Behavior → Page Turner. See https://www.readest.com/docs/advanced.

## Troubleshooting

- **Connection failed:** confirm both devices are on the same Wi-Fi, check the laptop IP with `ipconfig`, ensure `receiver.py` is running, and allow Python through Windows Firewall on Private networks. **Test connection** also reports when the secret does not match.
- **Connected but pages do not turn:** click inside the Readest reading area on the laptop first. The receiver sends keys to the currently focused app; it intentionally does not steal focus from other apps.
- **Wrong network/IP:** laptop IPv4 addresses often change when reconnecting to Wi-Fi. Update the address in the Android app if needed.
- **Do not expose the receiver to the internet.** The secret is a basic shared-token safeguard, not a replacement for a VPN or secure remote-access system. Use a trusted private network.

## Notes

- This starter project uses HTTP on your local network for simplicity. The secret is sent in an HTTP header, so use it only on a trusted Wi-Fi network.
- The receiver does not read your books or access Readest's files.
