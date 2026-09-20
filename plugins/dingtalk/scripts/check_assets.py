"""Validate DingTalk package assets; does not establish live designer acceptance."""

import json
from pathlib import Path

from opsmesh_plugin_dingtalk.cards import CardTemplate


def check_assets(directory: Path) -> None:
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
    check_assets(Path(__file__).resolve().parents[1])
