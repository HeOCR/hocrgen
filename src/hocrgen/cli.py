from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from hocrgen.annotation_pilots import load_annotation_pilot_config
from hocrgen.benchmark import load_benchmark_config
from hocrgen.benchmark_references import load_benchmark_reference_manifest, validate_benchmark_reference_files
from hocrgen.config.loader import ConfigBundle, load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.core.logging import configure_logging
from hocrgen.evaluation import (
    evaluate_text_predictions,
    load_benchmark_examples,
    load_text_records,
    summarize_benchmark_examples,
)
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.hocrsyngen_manifest import validate_hocrsyngen_batch
from hocrgen.fetchers.modern_handwriting import validate_modern_intake_manifest
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


def _add_pipeline_common_args(parser: argparse.ArgumentParser, *, dry_run_help: str) -> None:
    parser.add_argument("--profile", required=True, help="Release profile id")
    parser.add_argument("--workdir", type=Path, default=None, help="Work directory root")
    parser.add_argument("--config-root", type=Path, default=None, help="Override config root directory")
    parser.add_argument("--dry-run", action="store_true", help=dry_run_help)
    parser.add_argument("--source", action="append", default=None, help="Limit execution to one or more source ids")
    parser.add_argument("--max-items", type=int, default=None, help="Limit items per source during discovery/import")
    parser.add_argument("--seed", type=int, default=None, help="Override the synthetic generator seed")
    parser.add_argument("--synthetic-template", action="append", default=None, help="Limit synthetic generation to one or more template ids")
    parser.add_argument("--synthetic-recipe", action="append", default=None, help="Limit synthetic generation to one or more recipe ids")
    parser.add_argument(
        "--synthetic-degradation-preset",
        action="append",
        default=None,
        help="Limit synthetic generation to one or more degradation preset ids",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")


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

    evaluate_benchmark_parser = subparsers.add_parser(
        "evaluate-benchmark",
        help="Evaluate JSON/JSONL text predictions against benchmark item references",
    )
    evaluate_benchmark_parser.add_argument(
        "--benchmark-manifest",
        type=Path,
        required=True,
        help="Path to benchmark_manifest.json from build-release or export-alpha",
    )
    evaluate_benchmark_parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="JSONL/JSON predictions keyed by item_id with a text field",
    )
    evaluate_benchmark_parser.add_argument(
        "--references",
        type=Path,
        required=True,
        help="JSONL/JSON references keyed by item_id with a text field",
    )
    evaluate_benchmark_parser.add_argument(
        "--item-manifest",
        type=Path,
        default=None,
        help="Optional exported item_manifest.json to expose release-relative asset paths",
    )
    evaluate_benchmark_parser.add_argument(
        "--annotation-manifest",
        type=Path,
        default=None,
        help="Optional annotation_manifest.json to expose reference availability",
    )
    evaluate_benchmark_parser.add_argument(
        "--prediction-field",
        default="text",
        help="Prediction text field name in the predictions file",
    )
    evaluate_benchmark_parser.add_argument(
        "--reference-field",
        default="text",
        help="Reference text field name in the references file",
    )
    evaluate_benchmark_parser.add_argument("--output", type=Path, default=None, help="Optional path for the JSON report")
    evaluate_benchmark_parser.set_defaults(handler=handle_evaluate_benchmark)

    export_alpha_parser = subparsers.add_parser("export-alpha", help="Export a narrow alpha release tree for the HeOCR repo")
    _add_pipeline_common_args(
        export_alpha_parser,
        dry_run_help="Run the fixture/sample-backed milestone workflow without publishing",
    )
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

    f1_trial_parser = subparsers.add_parser(
        "f1-beta-trial",
        help="Run the operator-only F1c target-scale beta trial through build-release gates",
    )
    _add_pipeline_common_args(
        f1_trial_parser,
        dry_run_help="Run the operator-only target-scale workflow without publication side effects",
    )
    f1_trial_parser.set_defaults(handler=handle_f1_beta_trial, stage_name="build-release", f1_target_scale_trial=True)

    for stage in STAGE_COMMANDS:
        stage_parser = subparsers.add_parser(stage, help=f"Run the {stage} stage")
        _add_pipeline_common_args(
            stage_parser,
            dry_run_help="Run the fixture/sample-backed milestone workflow without publishing",
        )
        stage_parser.add_argument("--resume-run-dir", type=Path, default=None, help="Resume from a previous run directory")
        stage_parser.set_defaults(handler=handle_stage, stage_name=stage)

    return parser


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _load_bundle(config_root: Path | None) -> ConfigBundle:
    return load_and_validate_bundle(config_root.resolve() if config_root else None)


def _stage_options_from_args(args: argparse.Namespace) -> StageOptions:
    synthetic_template = getattr(args, "synthetic_template", None)
    synthetic_recipe = getattr(args, "synthetic_recipe", None)
    synthetic_degradation_preset = getattr(args, "synthetic_degradation_preset", None)
    return StageOptions(
        source_filter=set(args.source) if args.source else None,
        max_items=args.max_items,
        synthetic_seed=args.seed,
        synthetic_template_filter=set(synthetic_template) if synthetic_template else None,
        synthetic_recipe_filter=set(synthetic_recipe) if synthetic_recipe else None,
        synthetic_degradation_filter=set(synthetic_degradation_preset) if synthetic_degradation_preset else None,
        f1_target_scale_trial=bool(getattr(args, "f1_target_scale_trial", False)),
    )


def handle_config_validate(args: argparse.Namespace) -> int:
    try:
        bundle = _load_bundle(args.config_root)
        hocrsyngen_batches = []
        for source in bundle.source_registry.sources:
            if source.fetcher == "hocrsyngen_manifest":
                if not source.settings.hocrsyngen_batch_path:
                    raise StageExecutionError(f"source {source.id} settings.hocrsyngen_batch_path is required")
                batch = validate_hocrsyngen_batch(bundle.resolve_path(source.settings.hocrsyngen_batch_path))
                hocrsyngen_batches.append(
                    {
                        "page_count": batch.page_count,
                        "provider_version": batch.manifest.provider_metadata.provider_version,
                        "sample_count": batch.sample_count,
                        "source_id": source.id,
                    }
                )
            if source.fetcher == "modern_handwriting_intake":
                validate_modern_intake_manifest(source, bundle)
        benchmark_config = load_benchmark_config(bundle.config_root)
        benchmark_reference_manifest, benchmark_reference_manifest_path = load_benchmark_reference_manifest(bundle.config_root)
        benchmark_reference_validation = validate_benchmark_reference_files(bundle.config_root)
        annotation_pilot_config = load_annotation_pilot_config(bundle.config_root)
        review_data = validate_review_data(bundle.config_root, args.config_root.resolve() if args.config_root else None)
    except (ConfigValidationError, StageExecutionError) as exc:
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
            "benchmark_references": {
                "item_count": len(benchmark_reference_manifest.items) if benchmark_reference_manifest else 0,
                "layout_reference_count": len(benchmark_reference_validation.layout_references),
                "reference_manifest_id": (
                    benchmark_reference_manifest.reference_manifest_id if benchmark_reference_manifest else None
                ),
                "transcription_reference_count": len(benchmark_reference_validation.transcription_references),
                "path": str(benchmark_reference_manifest_path) if benchmark_reference_manifest_path else None,
            },
            "annotation_pilot": {
                "approved_item_count": len(annotation_pilot_config.approved_items),
                "pilot_id": annotation_pilot_config.pilot_id,
                "version": annotation_pilot_config.version,
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
            "hocrsyngen_batches": hocrsyngen_batches,
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
    options = _stage_options_from_args(args)
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


def handle_f1_beta_trial(args: argparse.Namespace) -> int:
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
        "starting F1 target-scale beta trial",
        extra={"run_id": context.run_id, "stage": "f1-beta-trial", "profile": args.profile, "dry_run": args.dry_run},
    )

    run_path = write_run_metadata(context)
    options = _stage_options_from_args(args)
    try:
        stage_results = execute_pipeline("build-release", bundle, context, options)
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1
    artifacts = [run_path]
    for result in stage_results:
        artifacts.append(result.summary_path)
        artifacts.extend(result.extra_artifacts)
    run_summary_path = write_run_summary(context, "f1-beta-trial", artifacts)
    f1_report_path = context.stage_dir("build-release") / "f1_target_scale_trial_report.json"
    logger.info(
        "F1 target-scale beta trial completed",
        extra={"run_id": context.run_id, "stage": "f1-beta-trial", "profile": args.profile, "dry_run": args.dry_run},
    )

    _print_json(
        {
            "dry_run": args.dry_run,
            "f1_target_scale_trial_report": str(f1_report_path),
            "profile_id": args.profile,
            "run_dir": str(context.run_dir),
            "run_id": context.run_id,
            "stage": "f1-beta-trial",
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


def handle_evaluate_benchmark(args: argparse.Namespace) -> int:
    try:
        examples = load_benchmark_examples(
            args.benchmark_manifest,
            item_manifest_path=args.item_manifest,
            annotation_manifest_path=args.annotation_manifest,
        )
        predictions = load_text_records(args.predictions, value_field=args.prediction_field)
        references = load_text_records(args.references, value_field=args.reference_field)
        report = {
            "status": "ok",
            "benchmark": summarize_benchmark_examples(examples),
            "metrics": evaluate_text_predictions(examples, predictions=predictions, references=references),
        }
        if args.output is not None:
            try:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
            except OSError as exc:
                raise StageExecutionError(f"could not write evaluation report to {args.output}: {exc}") from exc
    except StageExecutionError as exc:
        _print_json({"status": "error", "error": str(exc)})
        return 1

    _print_json(report)
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
    options = _stage_options_from_args(args)
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
