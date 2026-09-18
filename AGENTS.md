# SDK repository rules

- This repository owns the independently distributed Apache-2.0 Python plugin SDK.
- Keep SDK contracts and HTTP/signature adapters independent of OpsMesh backend imports,
  databases, workers and provider Agent SDKs. Business plugins live in their own repositories.
- Use HTTPX, Pydantic and cryptography directly; do not reimplement their protocols.
- Keep signing optional. Import cryptography only inside signing operations.
- Never introduce compatibility aliases, silent fallbacks, wrappers or duplicate contracts.
- Callers own credentials, HTTP client lifetime, network retries, durable deduplication
  and channel delivery. Never log tokens, signing keys or raw user payloads.
- Keep cohesive modules in src/opsmesh_plugin_sdk. Add a package only for a real boundary.
- During organization-only changes, use Ruff, mypy, compile and package checks;
  do not add single-class or helper tests. Behavior tests should exercise connector flows.
- Update README and distribution metadata for public contract or packaging changes.
- Preserve LICENSE, LICENSE-MIT and NOTICE. Do not import LGPL platform implementations.
- Before publishing, align the version with the tag and verify the built wheel and sdist.
