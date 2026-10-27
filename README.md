# Readest Remote (Android + Windows receiver)

A minimal Wi-Fi remote for turning pages in Readest on Windows. The Android app sends `previous` or `next` commands to a small Python server on your laptop. The receiver sends Left/Right arrow keys to the currently focused Windows app.

## What you need

- Windows 10 laptop with Readest installed
- Android phone on the same Wi-Fi network
- Windows receiver ZIP from the GitHub release (Python is only needed to build from source)
- Android Studio on a development computer to build the APK

## 1. Install and start the Windows receiver

1. Download and extract `ReadestRemote-Windows.zip` from the latest GitHub release.
2. Double-click `setup_receiver.bat`. It installs a per-user startup shortcut and starts the tray receiver. No Python, pip, or hand-generated secret is needed.
3. Allow the receiver through Windows Firewall on **Private networks only** when prompted. Keep the receiver on a trusted local network; do not expose port `18765` to the internet.

Right-click the Readest Remote tray icon and choose **Show pairing QR**. The QR is short-lived: it contains the laptop address, a three-minute one-use pairing code, and the receiver certificate fingerprint. In Android Connection settings, tap **Scan secure pairing QR**. Each phone receives its own credential, stored encrypted by Android Keystore; the Windows receiver stores only a hash of that credential. Credentials travel over HTTPS with the receiver certificate pinned by the app.

If QR scanning is unavailable, use **Show IP for manual entry** in the tray. Enter the displayed IP, port, certificate SHA-256 fingerprint, and temporary pairing code in Android settings before the three-minute expiry. **Refresh IP address**, **Copy laptop IP**, and **Copy all IPv4 addresses** are also available. Address lookup happens only when requested; the tray does not poll in the background.

The receiver creates its TLS identity and device registry automatically under `%LOCALAPPDATA%\ReadestRemote`. The private key stays on the laptop. Right-click the tray icon and choose **Revoke all paired phones** to invalidate every phone credential. Removing the receiver identity files also requires pairing phones again.

### Build the Windows receiver from source

Install Python 3, then run `windows-receiver\build_receiver.bat`. It installs the build dependencies and creates `dist\ReadestRemoteReceiver.exe`. Put that executable beside `setup_receiver.bat` to use the packaged install flow. The `windows-receiver` folder also supports direct Python source startup for development.

The executable is not code-signed, so Windows SmartScreen may show a reputation prompt. Verify downloads against the GitHub release page before running them.

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
2. Run `setup_receiver.bat` on the laptop, or start the receiver from the tray.
3. Open Readest and open a book. Click once inside the reading area so Readest is focused.
4. Open Readest Remote on Android.
5. On first launch, scan the pairing QR shown by the Windows receiver tray. Pairing completes automatically, and the phone stores its per-device credential encrypted with Android Keystore. Manual entry is available from the tray dialog if scanning fails.
6. On later launches, the app connects using HTTPS and pins the receiver certificate. If you reset receiver identity or revoke the device, pair it again from Connection settings.
7. Use the page and chapter buttons. Hold either page button to repeat. Keep Readest focused on the laptop.

The Android app supports Auto, Day, and Night appearance; tap the sun/moon icon to cycle modes. In **Connection settings**, scan the secure receiver QR; it automatically completes per-phone pairing. The scanner uses Google Play services and may need to download its scanner module the first time. The reading-mode buttons select Normal, Auto Scroll, Paragraph, Speed Reading, or Text to Speech. Tap the active mode again to return to Normal; choosing another mode first turns off the current one. Auto Scroll switches Readest to scrolled layout before starting. Its controls adjust speed, pause/resume, and turn pages. Speed Reading uses its WPM controls, play/pause, and page navigation. Text to Speech provides previous sentence, play/pause, next sentence, and stop. The **A−** and **A+** buttons adjust the laptop reader's font size (reflowable books); **A0** resets zoom. The fullscreen button toggles Readest's full screen mode. **Start Readest** launches or focuses Readest; **Close Readest** focuses Readest and sends `Ctrl+Q`. Tap the pin icon in the Android app to keep controls in an ongoing notification while using other apps. Its compact view uses mode-specific icon controls; expand it for the additional mode controls, full screen, and Readest launch/close buttons. Android 13 and newer ask for notification permission. When Readest asks where to begin Speed Reading, the receiver chooses **From Current Page**. Keep Readest focused on the laptop while using the remote. Auto Scroll speed controls click Readest's floating control pill near the bottom center of the reader window, so keep the laptop display unobstructed and the reader window in its usual layout.

The mode buttons control Readest on the laptop, not the phone's own display. The remote opens with Normal selected and remembers the last mode successfully sent to the receiver so it can turn that mode off before switching. Tap any active non-Normal mode again, or tap Normal, to return to Normal. If you change modes directly in Readest, its actual mode can differ from the remote's remembered mode; return Readest to Normal before continuing with the phone. Switching into Auto Scroll assumes Readest starts in paginated mode because `Shift+J` toggles the layout. If Readest is already scrolled, first switch it to paginated mode in Readest.

The remote follows Readest's documented shortcuts: `Shift+J` toggles scrolled layout, `Shift+A` toggles Auto Scroll, `Shift+P` toggles paragraph mode, `Shift+V` starts Speed Reading, `T` toggles Text to Speech, and `F11` toggles full screen. TTS uses Space for play/pause and `Ctrl+[` / `Ctrl+]` for previous/next sentence. In Speed Reading, Space toggles playback and Up/Down changes WPM. `Ctrl+0` resets zoom. (`Ctrl+T` is Readest's Translate shortcut, so the remote uses `T` for TTS.) Page and chapter navigation closes the RSVP overlay before sending the navigation key; the Android mode indicator resets to Normal afterward. If the receiver file was updated while tray mode was running, restart the receiver so it loads the new actions. See [Readest Reading docs](https://readest.com/docs/reading), [Advanced keyboard shortcuts](https://readest.com/docs/advanced), and [Customization](https://readest.com/docs/customization).

Readest's default shortcuts are Left Arrow for previous page and Right Arrow for next page. Chapter turns use `Alt+Left` and `Alt+Right`. Readest also lets you customize keyboard bindings under Settings → Behavior → Page Turner. See https://www.readest.com/docs/advanced.

## Troubleshooting

- **Connection failed:** confirm both devices are on the same Wi-Fi, ensure `receiver.py` is running, and allow Python through Windows Firewall on Private networks. Use **Show IP for manual entry** in the tray if QR scanning fails. Scan a fresh QR if its one-use pairing code has expired.
- **Connected but pages do not turn:** click inside the Readest reading area on the laptop first. The receiver sends keys to the currently focused app; it intentionally does not steal focus from other apps.
- **Wrong network/IP:** laptop IPv4 addresses often change when reconnecting to Wi-Fi. Use **Refresh IP address** and scan a new **Show pairing QR**, or select **Show IP for manual entry** in the tray.
- **Do not expose the receiver to the internet.** The secret is a basic shared-token safeguard, not a replacement for a VPN or secure remote-access system. Use a trusted private network.

## Notes

- Receiver traffic uses HTTPS with certificate pinning and unique per-phone credentials. The pairing code is single-use and expires after three minutes.
- The receiver does not read your books or access Readest's files.
