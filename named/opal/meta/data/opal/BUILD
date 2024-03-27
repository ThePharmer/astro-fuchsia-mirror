package(default_visibility = [
    "//assistant/gallium/dragonglass/platform/fuchsia:fuchsia_deployments",
])

filegroup(
    name = "shaders",
    srcs = select({
        "//tools/cc_target_os:fuchsia": glob(["**"]),
        "//conditions:default": [],
    }),
)
