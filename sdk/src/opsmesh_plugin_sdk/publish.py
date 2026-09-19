"""Publisher-side signing command. Keys never enter the manifest or printed output."""

import argparse
import base64
import hashlib
import os
from pathlib import Path

from opsmesh_plugin_sdk.contracts import PluginManifest
from opsmesh_plugin_sdk.distribution import PluginReleaseDescriptor, sign_release
from opsmesh_plugin_sdk.packages import sign_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--publisher-key-id", required=True)
    parser.add_argument("--platform-requires", required=True)
    parser.add_argument("--sdk-requires", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument("--container-image")
    args = parser.parse_args()
    manifest = PluginManifest.model_validate_json(args.manifest.read_bytes())
    tag = os.environ.get("RELEASE_TAG")
    if tag is not None and tag != args.tag_prefix + manifest.version:
        parser.error("Release tag must match manifest version")
    private_key = base64.b64decode(os.environ["OPSMESH_PLUGIN_SIGNING_KEY"], validate=True)
    release = sign_release(
        PluginReleaseDescriptor(
            package=sign_package(manifest, args.publisher_key_id, private_key),
            platform_requires=args.platform_requires,
            sdk_requires=args.sdk_requires,
            license=args.license,
            source_repository=args.repository,
            source_commit=args.commit,
            container_image=args.container_image,
        ),
        private_key,
    )
    content = release.model_dump_json(indent=2).encode() + b"\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(content)
    print(hashlib.sha256(content).hexdigest(), args.output.name)


if __name__ == "__main__":
    main()
