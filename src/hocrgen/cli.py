from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from hocrgen.benchmark import load_benchmark_config
from hocrgen.config.loader import ConfigBundle, load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.core.logging import configure_logging
from hocrgen.fetchers.base import StageOptions
from hocrgen.package.alpha import AlphaExportConfig, export_alpha_release
from hocrgen.pipeline import execute_pipeline, write_run_metadata, write_run_summary
from hocrgen.review.merge import validate_review_data
from hocrgen.runs import load_resumed_pipeline_state, render_run_summary_markdown, summarize_run


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
    "review-merge",
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

    summarize_run_parser = subparsers.add_parser("summarize-run", help="Summarize a persisted run directory")
    summarize_run_parser.add_argument("--run-dir", type=Path, required=True, help="Path to the run directory to summarize")
    summarize_run_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for the run summary",
    )
    summarize_run_parser.set_defaults(handler=handle_summarize_run)

    export_alpha_parser = subparsers.add_parser("export-alpha", help="Export a narrow alpha release tree for the HeOCR repo")
    export_alpha_parser.add_argument("--profile", required=True, help="Release profile id")
    export_alpha_parser.add_argument("--workdir", type=Path, default=None, help="Work directory root")
    export_alpha_parser.add_argument("--config-root", type=Path, default=None, help="Override config root directory")
    export_alpha_parser.add_argument("--dry-run", action="store_true", help="Run the fixture/sample-backed milestone workflow without publishing")
    export_alpha_parser.add_argument("--source", action="append", default=None, help="Limit execution to one or more source ids")
    export_alpha_parser.add_argument("--max-items", type=int, default=None, help="Limit items per source during discovery/import")
    export_alpha_parser.add_argument("--seed", type=int, default=None, help="Override the synthetic generator seed")
    export_alpha_parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    export_alpha_parser.add_argument("--version", default="alpha-v0", help="Versioned release folder name")
    export_alpha_parser.add_argument("--output-dir", type=Path, default=None, help="Override the alpha export root directory")
    export_alpha_parser.add_argument("--heocr-repo", type=Path, default=None, help="Path to a checked-out HeOCR repo; exports to releases/<version> there")
    export_alpha_parser.add_argument(
        "--compare-to",
        type=Path,
        default=None,
        help="Optional path to a previous exported release directory to diff against",
    )
    export_alpha_parser.add_argument("--overwrite", action="store_true", help="Replace an existing alpha export directory")
    export_alpha_parser.add_argument("--max-real-items", type=int, default=10, help="Maximum number of real items to include")
    export_alpha_parser.add_argument(
        "--max-synthetic-items",
        type=int,
        default=20,
        help="Maximum number of synthetic items to include, additionally bounded by 2x exported real items",
    )
    export_alpha_parser.set_defaults(handler=handle_export_alpha)

    for stage in STAGE_COMMANDS:
        stage_parser = subparsers.add_parser(stage, help=f"Run the {stage} stage")
        stage_parser.add_argument("--profile", required=True, help="Release profile id")
        stage_parser.add_argument("--workdir", type=Path, default=None, help="Work directory root")
        stage_parser.add_argument("--config-root", type=Path, default=None, help="Override config root directory")
        stage_parser.add_argument("--dry-run", action="store_true", help="Run the fixture/sample-backed milestone workflow without publishing")
        stage_parser.add_argument("--source", action="append", default=None, help="Limit execution to one or more source ids")
        stage_parser.add_argument("--max-items", type=int, default=None, help="Limit items per source during discovery/import")
        stage_parser.add_argument("--seed", type=int, default=None, help="Override the synthetic generator seed")
        stage_parser.add_argument("--resume-run-dir", type=Path, default=None, help="Resume from a previous run directory")
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
        benchmark_config = load_benchmark_config(bundle.config_root)
        review_data = validate_review_data(bundle.config_root, args.config_root.resolve() if args.config_root else None)
    except ConfigValidationError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    _print_json(
        {
            "config_root": str(bundle.config_root),
            "profile_count": len(bundle.profiles),
            "profiles": sorted(bundle.profiles),
            "benchmark": {
                "approved_item_count": len(benchmark_config.approved_items),
                "benchmark_id": benchmark_config.benchmark_id,
                "version": benchmark_config.version,
            },
            "privacy_rules_version": bundle.privacy_rules.version,
            "quality_thresholds_version": bundle.quality_thresholds.version,
            "review_data_root": str(review_data.root),
            "review_data_counts": {
                "allowlist": len(review_data.allowlist),
                "blocklist": len(review_data.blocklist),
                "manual_decisions": len(review_data.manual_decisions),
            },
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
    initial_state = None
    start_stage = None
    if args.resume_run_dir is not None:
        try:
            initial_state, latest_stage = load_resumed_pipeline_state(args.resume_run_dir, args.profile, args.stage_name)
        except StageExecutionError as exc:
            _print_json({"status": "error", "error": str(exc)})
            return 1
        if latest_stage != args.stage_name:
            start_stage = {
                stage: STAGE_COMMANDS[index + 1]
                for index, stage in enumerate(STAGE_COMMANDS[:-1])
            }.get(latest_stage)
            if start_stage is None:
                _print_json(
                    {
                        "status": "error",
                        "error": f"resume run cannot determine the next stage after {latest_stage}",
                    }
                )
                return 1
    try:
        stage_results = execute_pipeline(
            args.stage_name,
            bundle,
            context,
            options,
            initial_state=initial_state,
            start_stage=start_stage,
        )
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1
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


def handle_summarize_run(args: argparse.Namespace) -> int:
    try:
        summary = summarize_run(args.run_dir)
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    if args.format == "markdown":
        print(render_run_summary_markdown(summary), end="")
        return 0

    _print_json(summary)
    return 0


def handle_export_alpha(args: argparse.Namespace) -> int:
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
        "starting alpha export",
        extra={"run_id": context.run_id, "stage": "export-alpha", "profile": args.profile, "dry_run": args.dry_run},
    )

    run_path = write_run_metadata(context)
    options = StageOptions(
        source_filter=set(args.source) if args.source else None,
        max_items=args.max_items,
        synthetic_seed=args.seed,
    )
    try:
        stage_results = execute_pipeline("build-release", bundle, context, options)
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1
    export_config = AlphaExportConfig(
        version=args.version,
        output_dir=args.output_dir,
        heocr_repo=args.heocr_repo,
        compare_to=args.compare_to,
        overwrite=args.overwrite,
        max_real_items=args.max_real_items,
        max_synthetic_items=args.max_synthetic_items,
    )
    try:
        export_result = export_alpha_release(bundle, context.run_dir, args.profile, export_config)
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    artifacts = [run_path]
    for result in stage_results:
        artifacts.append(result.summary_path)
        artifacts.extend(result.extra_artifacts)
    artifacts.append(export_result.summary_path)
    run_summary_path = write_run_summary(context, "export-alpha", artifacts)
    logger.info(
        "alpha export completed",
        extra={"run_id": context.run_id, "stage": "export-alpha", "profile": args.profile, "dry_run": args.dry_run},
    )

    _print_json(
        {
            "dry_run": args.dry_run,
            "export_dir": str(export_result.export_dir),
            "handoff_repo": str(args.heocr_repo.resolve()) if args.heocr_repo else None,
            "profile_id": args.profile,
            "run_dir": str(context.run_dir),
            "run_id": context.run_id,
            "stage": "export-alpha",
            "status": "ok",
            "summary_path": str(run_summary_path),
        }
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
