# NEXA Mobile

Selected personal distribution route: [IPA → Google Drive → Sideloadly on Windows](SIDELOAD_VI.md).
Run the root Codemagic workflow `nexa-ios-sideload`; no Apple signing credentials
are needed on the build service. The resulting unsigned IPA must be re-signed
before installation. No cloud build has been performed yet.

Native Flutter iOS/Android text-chat client. See [BUILD_STATUS.md](BUILD_STATUS.md) for implemented scope, verification limits and signing instructions.

```sh
flutter pub get
flutter analyze
flutter test
```

Build iOS on macOS/Xcode or use root codemagic.yaml. Configure your own HTTPS chat-completions endpoint, model and token in Settings.
