# Stopped robotd wire fixture

`robotd-stopped-wire.json` is unmodified output from the real Rust serializers,
not a hand-written shape for the Studio test. It is shared with padd's stopped
proof test in the native release preparation branch.

- Producer test: `robotd::raw_stream::tests::stopped_pad_mapping_wire_uses_actual_flattened_serializer`.
- Production paths exercised: `raw_stream::Bus::report()`, its `DynamicBus` with
  `#[serde(flatten)]`, and `duck_ipc_proto::PoliciesResult` / `RobotState`.
- Robot build: `0791fcd-feetech-qinmo-control.47`.
- SHA-256: `aa9036954c808aa251fb3f560a302340538235abf52dc9faf66e93eb6b95e5b3`.
- Native source: `microduck-hd1910/firmware/robotd/src/raw_stream.rs` in
  `release/native-inputs-20261030`; exported under `#[cfg(test)]` with synthetic
  values and no hardware access. Robot control algorithms are unchanged.

The intended distinction is `policies.enabled=true` (configured model loading)
alongside top-level `bus.policy_enabled=false` (runtime strategy stopped).
`homed` and `home_recovery` also live at the bus top level. The two state frames
are fresh, held and zero-motion. Consumers must not add a `dynamic` JSON object
or set the configuration flag false merely to make a mapping test pass.
