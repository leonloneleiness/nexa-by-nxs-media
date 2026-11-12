# NEXA mobile 0.1.0 — 2026-11-12

Implemented: Flutter native mobile chat UI, configurable HTTPS chat-completions endpoint and model, secure-storage configuration (iOS Keychain), session-only conversation, error recovery, new conversation action. This is an early text-chat client, not desktop feature parity.

Not implemented: voice, PC pairing/control, shared history, offline AI, background assistant. No backend is deployed by this change. Enter a working HTTPS endpoint, model and personal token in Settings. PC credentials are not embedded. The configured service receives the session conversation on Send.

Windows verification: see flutter analyze and flutter test results in the task. Network tests use a fake HTTP client. Keychain and Swift/iOS compilation have not been tested on macOS or a physical device. No signed IPA exists and nothing has been installed on the iPhone.

## Build without owning a Mac

The selected route is now **nexa-ios-sideload**, producing an unsigned IPA for
re-signing with Sideloadly on Windows. See [SIDELOAD_VI.md](SIDELOAD_VI.md).
The signed development workflow below remains optional, not a prerequisite
for this route. Neither workflow has been run on a macOS builder in this session.

1. Connect this repository to Codemagic, with root codemagic.yaml and mobile/ included. Source has not been pushed by this task.
2. Run an unsigned macOS build first to verify native plugin compilation.
3. For the signed workflow, configure the App Store Connect integration named NEXA_APP_STORE_CONNECT, register com.nxsmedia.nexaMobile (or update both project and YAML to an available identifier), and supply matching development signing identities/profiles including the test iPhone. Never commit private keys or passwords.
4. Run nexa-ios. It analyzes/tests and exports a development IPA. This is not a TestFlight workflow; TestFlight needs App Store signing and separate distribution setup.
5. Install the signed IPA using an appropriate Apple device deployment tool and verify startup, Keychain persistence, HTTPS response/error handling and keyboard layout on the real iPhone.

Official instructions: https://docs.flutter.dev/platform-integration/ios/setup
Codemagic: https://docs.codemagic.io/yaml-quick-start/building-a-flutter-app/
