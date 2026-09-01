// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SignalLightApp",
    platforms: [
        .macOS(.v13)
    ],
    targets: [
        .target(name: "SignalLightCore", path: "Sources/SignalLightCore"),
        .executableTarget(
            name: "SignalLightApp",
            dependencies: ["SignalLightCore"],
            path: "Sources/SignalLightApp"
        ),
        .testTarget(
            name: "SignalLightAppTests",
            dependencies: ["SignalLightCore"],
            path: "Tests/SignalLightAppTests"
        ),
    ]
)
