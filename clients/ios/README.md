# Xong for iOS

The SwiftUI client discovers any compatible Xong server at runtime. It contains no
deployment-specific hostnames, identity-provider IDs, or signing credentials.

## Build and test

Requirements: Xcode 16 or later and an iOS 17 or later simulator.

```bash
xcodebuild -project clients/ios/Xong.xcodeproj -scheme Xong \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/xong-ios-build CODE_SIGNING_ALLOWED=NO build
```

To run the unit tests, select any available iPhone simulator in Xcode and use Product >
Test. CI selects an available simulator automatically and runs the same `Xong` scheme.

## Connect to a server

During onboarding, enter an email address, hostname, or full configuration URL. The app
loads `/.well-known/xong-config`, validates HTTPS and the advertised identity settings,
then uses OIDC Authorization Code with PKCE when requested by the server. Plain HTTP is
accepted only for loopback development servers.

## Signing and distribution

The repository intentionally contains no Apple team or certificate. Before creating an
archive, choose your Apple team in Xcode and replace `app.xong.client` with a bundle ID
registered to that team. CI disables code signing and never accesses Apple credentials.

The target includes the terrace app icon and a privacy manifest declaring its app-local
`UserDefaults` use. The manifest declares no tracking or developer data collection; a
distributor must review those declarations against its own server and privacy practices.
App Store Connect metadata, privacy-policy URL, screenshots, certificates, TestFlight,
and review submission remain the distributor's responsibility.
