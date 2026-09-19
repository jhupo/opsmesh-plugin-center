"""Static contribution checks, not evidence of vendor import or live delivery."""

import argparse
import json
import re
import tomllib
from pathlib import Path

from opsmesh_plugin_sdk.cards import CardTemplate
from opsmesh_plugin_sdk.contracts import PluginManifest
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
    for mapping_path in sorted((directory / "card-templates").glob("*/*/mapping.json")):
        mapping = CardTemplate.model_validate_json(mapping_path.read_bytes())
        preview = json.loads(mapping_path.with_name("preview.json").read_text(encoding="utf-8"))
        if set(preview) != set(mapping.parameters):
            raise ValueError(f"Preview and mapping parameters differ: {mapping_path}")
        card = json.loads(mapping_path.with_name("card.json").read_text(encoding="utf-8"))
        if mapping.channel == "dingtalk":
            editor = json.loads(card["editorData"])
            if {v["name"] for v in editor["variableList"]} != set(mapping.parameters):
                raise ValueError(f"DingTalk variables and mapping differ: {mapping_path}")
            actions: set[str] = set()
            nodes = list(editor["schema"]["componentsTree"])
            while nodes:
                node = nodes.pop()
                nodes.extend(node.get("children", []))
                for button in node.get("props", {}).get("buttons", []):
                    if button.get("actionType") == "request":
                        actions.update(
                            p["value"] for p in button.get("params", []) if p["name"] == "action"
                        )
            if actions != set(mapping.actions):
                raise ValueError(f"DingTalk callbacks and mapping differ: {mapping_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    check_package(args.directory)
    print("Package contracts and assets checked; live vendor acceptance is separate.")
