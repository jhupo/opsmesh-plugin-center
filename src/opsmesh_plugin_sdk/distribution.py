"""Data-only release and catalog contracts. No fetching or execution is performed here."""

import base64
import json
from typing import Literal

from packaging.specifiers import SpecifierSet
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opsmesh_plugin_sdk.packages import SignedPluginPackage, verify_package


class PluginReleaseDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = 1
    package: SignedPluginPackage
    platform_requires: str = Field(min_length=1, max_length=160)
    sdk_requires: str = Field(min_length=1, max_length=160)
    license: str = Field(min_length=1, max_length=120)
    source_repository: str = Field(pattern=r"^https://[^\s]+$", max_length=512)
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")

    @field_validator("platform_requires", "sdk_requires")
    @classmethod
    def valid_versions(cls, value: str) -> str:
        SpecifierSet(value)
        return value


class SignedPluginRelease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release: PluginReleaseDescriptor
    signature: str = Field(min_length=88, max_length=88)


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    publisher_key_id: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,120}$")
    release_url: str = Field(pattern=r"^https://[^\s]+$", max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    withdrawn: bool = False


class PluginCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[1] = 1
    entries: list[CatalogEntry] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_releases(self) -> "PluginCatalog":
        keys = [(entry.plugin_key, entry.version) for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Catalog contains duplicate releases")
        return self


def release_signing_bytes(release: PluginReleaseDescriptor) -> bytes:
    return json.dumps(
        {"purpose": "opsmesh.remote-plugin-release", "release": release.model_dump(mode="json")},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sign_release(release: PluginReleaseDescriptor, private_key: bytes) -> SignedPluginRelease:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(private_key)
    verify_package(release.package, key.public_key().public_bytes_raw())
    return SignedPluginRelease(
        release=release,
        signature=base64.b64encode(key.sign(release_signing_bytes(release))).decode(),
    )


def verify_release(release: SignedPluginRelease, public_key: bytes) -> None:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    verify_package(release.release.package, public_key)
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            base64.b64decode(release.signature, validate=True),
            release_signing_bytes(release.release),
        )
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("Release signature is invalid") from exc
