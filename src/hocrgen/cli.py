from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from hocrgen.config.loader import ConfigBundle, load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import ConfigValidationError
from hocrgen.core.logging import configure_logging
from hocrgen.fetchers.base import StageOptions
from hocrgen.pipeline import execute_pipeline, write_run_metadata, write_run_summary


STAGE_COMMANDS = (
    "discover",
    "fetch-metadata",
    "policy-filter",
    "acquire",
    "normalize",
    "dedupe",
    "classify",
    "privacy-scan",
    "review-export",
    "split",
    "build-release",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hocrgen", description="HeOCR dataset operations CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    validate_parser = config_subparsers.add_parser("validate", help="Validate committed configuration")
    validate_parser.add_argument("--config-root", type=Path, default=None, help="Override config root directory")
    validate_parser.set_defaults(handler=handle_config_validate)

    for stage in STAGE_COMMANDS:
        stage_parser = subparsers.add_parser(stage, help=f"Run the {stage} stage")
        stage_parser.add_argument("--profile", required=True, help="Release profile id")
        stage_parser.add_argument("--workdir", type=Path, default=None, help="Work directory root")
        stage_parser.add_argument("--config-root", type=Path, default=None, help="Override config root directory")
        stage_parser.add_argument("--dry-run", action="store_true", help="Run the fixture/sample-backed milestone workflow without publishing")
        stage_parser.add_argument("--source", action="append", default=None, help="Limit execution to one or more source ids")
        stage_parser.add_argument("--max-items", type=int, default=None, help="Limit items per source during discovery/import")
        stage_parser.add_argument("--seed", type=int, default=None, help="Override the synthetic generator seed")
        stage_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
        stage_parser.set_defaults(handler=handle_stage, stage_name=stage)

    return parser


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _load_bundle(config_root: Path | None) -> ConfigBundle:
    return load_and_validate_bundle(config_root.resolve() if config_root else None)


def handle_config_validate(args: argparse.Namespace) -> int:
    try:
        bundle = _load_bundle(args.config_root)
    except ConfigValidationError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    _print_json(
        {
            "config_root": str(bundle.config_root),
            "profile_count": len(bundle.profiles),
            "profiles": sorted(bundle.profiles),
            "privacy_rules_version": bundle.privacy_rules.version,
            "quality_thresholds_version": bundle.quality_thresholds.version,
            "source_count": len(bundle.source_registry.sources),
            "status": "ok",
        }
    )
    return 0


def handle_stage(args: argparse.Namespace) -> int:
    try:
        bundle = _load_bundle(args.config_root)
    except ConfigValidationError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    if args.profile not in bundle.profiles:
        _print_json({"status": "error", "error": f"unknown profile: {args.profile}"})
        return 1

    context = create_run_context(profile_id=args.profile, dry_run=args.dry_run, workdir=args.workdir)
    logger = configure_logging(context.log_dir / "run.log", verbose=args.verbose)
    logger.info(
        "starting stage",
        extra={"run_id": context.run_id, "stage": args.stage_name, "profile": args.profile, "dry_run": args.dry_run},
    )

    run_path = write_run_metadata(context)
    options = StageOptions(
        source_filter=set(args.source) if args.source else None,
        max_items=args.max_items,
        synthetic_seed=args.seed,
    )
    stage_results = execute_pipeline(args.stage_name, bundle, context, options)
    artifacts = [run_path]
    for result in stage_results:
        artifacts.append(result.summary_path)
        artifacts.extend(result.extra_artifacts)
    run_summary_path = write_run_summary(context, args.stage_name, artifacts)
    logger.info(
        "stage completed",
        extra={"run_id": context.run_id, "stage": args.stage_name, "profile": args.profile, "dry_run": args.dry_run},
    )

    _print_json(
        {
            "dry_run": args.dry_run,
            "profile_id": args.profile,
            "run_dir": str(context.run_dir),
            "run_id": context.run_id,
            "stage": args.stage_name,
            "status": "ok",
            "summary_path": str(run_summary_path),
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
