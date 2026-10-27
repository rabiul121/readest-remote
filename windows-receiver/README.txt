Readest Remote Windows receiver

1. Keep ReadestRemoteReceiver.exe and setup_receiver.bat in this folder.
2. Double-click setup_receiver.bat. Approve Windows Firewall access on Private networks only.
3. Right-click the Readest Remote tray icon and choose Show pairing QR.
4. On Android, open Connection settings and scan the QR. The code expires after three minutes and can be used once.

The receiver stores its certificate/private key and paired-device hashes in:
%LOCALAPPDATA%\ReadestRemote

Choose Revoke all paired phones from the tray menu to invalidate saved device credentials. Removing receiver-cert.pem and receiver-key.pem also revokes prior pairings because Android pins the certificate; phones must be paired again.

For firewall troubleshooting, allow ReadestRemoteReceiver.exe on Private networks. Do not expose port 18765 to the internet.
