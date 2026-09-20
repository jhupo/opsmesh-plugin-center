"""Static contribution checks, not evidence of vendor import or live delivery."""

import argparse
import re
from pathlib import Path

import tomllib
from opsmesh_plugin_sdk.packaging.manifest import PluginManifest
from packaging.specifiers import SpecifierSet


def check_package(directory: Path) -> None:
    project = tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if directory.name == "sdk":
        return
    if not re.fullmatch(r"[a-z][a-z0-9-]*", directory.name):
        raise ValueError("Plugin directory must be lowercase kebab-case")
    manifest = PluginManifest.model_validate_json((directory / "plugin.json").read_bytes())
    if manifest.version != project["version"]:
        raise ValueError("Plugin manifest and package versions differ")
    release = tomllib.loads((directory / "release.toml").read_text(encoding="utf-8"))
    if set(release) != {"publisher_key_id", "platform_requires", "sdk_requires"}:
        raise ValueError("Invalid plugin release configuration")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,120}", release["publisher_key_id"]):
        raise ValueError("Invalid publisher key ID")
    SpecifierSet(release["platform_requires"])
    sdk_range = SpecifierSet(release["sdk_requires"])
    sdk = tomllib.loads(Path("sdk/pyproject.toml").read_text(encoding="utf-8"))["project"]
    if sdk["version"] not in sdk_range:
        raise ValueError("Current SDK is outside the plugin release requirements")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    check_package(args.directory)
    print("Package contracts and assets checked; live vendor acceptance is separate.")
