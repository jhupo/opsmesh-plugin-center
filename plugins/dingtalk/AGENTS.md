# DingTalk connector development rules

This package owns only the independently deployed DingTalk connector. Read README.md first.
Use opsmesh-plugin-sdk public contracts and clients; never import or copy OpsMesh backend code.
Use official DingTalk Stream/OpenAPI SDKs for transport, authentication and cards.
Keep cohesive lifecycle code together. Store UI templates/mappings/previews under card-templates,
deployment assets under deploy; use the root CI and workspace lock, never nested workflows.
No compatibility shims, SDK monkeypatching or silent error fallbacks.
Platform installation credentials never represent a human user. Bind external staff identities
in OpsMesh; messages and buttons cannot grant roles. Approval buttons call the platform decision
endpoint with the displayed approval ID; installation, human and task authority remain mandatory.
Only the original sender may receive the card or operate it; disable forwarding.
Never log secrets, raw channel messages, card content or SDK exception response bodies.
Persist inbox state before acknowledging; use stable event/card IDs, compare-and-swap state,
and retain recoverable failures. Do not claim exactly-once delivery from remote APIs.
Use a product-flow test for receipt, stream, delivery, callback and recovery, not per-file tests.
Run focused flow, Ruff, type checking and wheel build; no full platform suite.
Commit completed features; no release tag or real outbound message without explicit authorization.
