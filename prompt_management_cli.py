"""
CLI helpers for Bedrock prompt version operations:
- Sync to Bedrock Prompt Management
- Configure active versions
- Configure A/B tests
- Rollback to previous versions
"""

from __future__ import annotations

import argparse
import json
from typing import Dict

from bedrock_prompt_management import BedrockPromptManager


def _parse_weights(raw: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    if not raw:
        return weights
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid weight entry '{item}'. Use format version=weight")
        key, value = item.split("=", 1)
        weights[key.strip()] = float(value.strip())
    return weights


def main() -> None:
    parser = argparse.ArgumentParser(description="Track B prompt management utility")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show", help="Show prompt registry summary")

    sync_parser = subparsers.add_parser("sync", help="Sync prompt templates to Bedrock")
    sync_parser.add_argument("--template", help="Optional single template name")

    set_active_parser = subparsers.add_parser("set-active", help="Set active version")
    set_active_parser.add_argument("--template", required=True)
    set_active_parser.add_argument("--version", required=True)
    set_active_parser.add_argument("--rationale", required=True)
    set_active_parser.add_argument("--changed-by", default="SYSTEM")

    rollback_parser = subparsers.add_parser("rollback", help="Rollback to a previous version")
    rollback_parser.add_argument("--template", required=True)
    rollback_parser.add_argument("--version", required=True)
    rollback_parser.add_argument("--rationale", required=True)
    rollback_parser.add_argument("--changed-by", default="SYSTEM")

    ab_parser = subparsers.add_parser("set-ab", help="Configure A/B test assignment")
    ab_parser.add_argument("--template", required=True)
    ab_parser.add_argument("--enabled", required=True, choices=["true", "false"])
    ab_parser.add_argument("--weights", default="")
    ab_parser.add_argument("--salt", default=None)
    ab_parser.add_argument("--rationale", default="")
    ab_parser.add_argument("--changed-by", default="SYSTEM")

    args = parser.parse_args()
    manager = BedrockPromptManager()

    if args.command == "show":
        templates = manager.registry.get("templates", {})
        summary = {
            "templates": {
                name: {
                    "active_version": cfg.get("active_version"),
                    "available_versions": sorted(list(cfg.get("versions", {}).keys())),
                    "bedrock_prompt_id": cfg.get("bedrock_prompt_id"),
                }
                for name, cfg in templates.items()
            },
            "ab_tests": manager.registry.get("ab_tests", {}),
        }
        print(json.dumps(summary, indent=2))
        return

    if args.command == "sync":
        if args.template:
            cfg = manager.registry["templates"].get(args.template)
            if not cfg:
                raise ValueError(f"Template not found: {args.template}")
            result = manager.sync_template_to_bedrock(args.template, cfg["active_version"])
            print(json.dumps({args.template: result}, indent=2))
            return
        print(json.dumps(manager.sync_all_templates(), indent=2))
        return

    if args.command == "set-active":
        manager.set_active_version(
            template_name=args.template,
            version=args.version,
            rationale=args.rationale,
            changed_by=args.changed_by,
        )
        print(f"Active version set: {args.template} -> {args.version}")
        return

    if args.command == "rollback":
        manager.rollback_to_version(
            template_name=args.template,
            version=args.version,
            rationale=args.rationale,
            changed_by=args.changed_by,
        )
        print(f"Rolled back: {args.template} -> {args.version}")
        return

    if args.command == "set-ab":
        result = manager.configure_ab_test(
            template_name=args.template,
            enabled=args.enabled == "true",
            weights=_parse_weights(args.weights) if args.weights else None,
            salt=args.salt,
            changed_by=args.changed_by,
            rationale=args.rationale,
        )
        print(json.dumps(result, indent=2))
        return


if __name__ == "__main__":
    main()
