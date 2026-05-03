from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord, ItemRecord
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file, read_text


class _NLIHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.description: str | None = None
        self.rights: str | None = None
        self.assets: list[str] = []
        self._capture_title = False
        self._capture_rights = False
        self._capture_description = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = dict(attrs)
        if tag == "meta" and attr_map.get("property") == "og:title":
            self.title = attr_map.get("content")
        if tag == "meta" and attr_map.get("name") == "description":
            self.description = attr_map.get("content")
        if tag in {"h1", "span", "div"} and attr_map.get("class") == "item-title":
            self._capture_title = True
        if tag in {"span", "div"} and attr_map.get("class") == "rights-label":
            self._capture_rights = True
        if tag in {"p", "div"} and attr_map.get("class") == "item-description":
            self._capture_description = True
        if tag == "img" and attr_map.get("class") == "page-image" and attr_map.get("src"):
            self.assets.append(attr_map["src"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._capture_title = False
        if tag in {"span", "div"}:
            self._capture_rights = False
            self._capture_description = False

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        if self._capture_title and not self.title:
            self.title = value
        if self._capture_rights and not self.rights:
            self.rights = value
        if self._capture_description and not self.description:
            self.description = value


@dataclass(frozen=True)
class ParsedNliFixture:
    title: str | None
    description: str | None
    rights: str | None
    assets: list[str]


def parse_nli_fixture_html(path: Path) -> ParsedNliFixture:
    parser = _NLIHTMLParser()
    parser.feed(read_text(path))
    return ParsedNliFixture(
        title=parser.title,
        description=parser.description,
        rights=parser.rights,
        assets=list(parser.assets),
    )


class NliFetcher:
    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        seed_manifest = bundle.resolve_path(source.settings.seed_manifest or "")
        seeds = load_yaml_file(seed_manifest)["items"]
        candidates: list[CandidateRecord] = []
        for item in seeds:
            source_depth_only = item.get("f1_source_depth_only") is True
            if source_depth_only and not options.f1_target_scale_trial:
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            fixture_reference = item.get("fixture_html")
            fixture_path: Path | None = None
            if fixture_reference:
                if isinstance(fixture_reference, str) and fixture_reference.startswith("package://"):
                    fixture_path = bundle.resolve_path(fixture_reference)
                else:
                    fixture_path = (
                        Path(fixture_reference).resolve()
                        if Path(fixture_reference).is_absolute()
                        else (seed_manifest.parent / fixture_reference).resolve()
                    )
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{item['id']}",
                    source_id=source.id,
                    source_item_id=item["id"],
                    source_url=item["url"],
                    discovery_method="f1_target_scale_seed_manifest" if source_depth_only else "seed_manifest",
                    title=item.get("title"),
                    fixture_path=str(fixture_path) if fixture_path else None,
                    raw_metadata={
                        "f1_target_scale_trial": options.f1_target_scale_trial,
                        "f1_source_depth_only": source_depth_only,
                        "notes": item.get("notes"),
                        "seed_manifest": str(seed_manifest),
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(
        self,
        source: SourceConfig,
        bundle: ConfigBundle,
        candidates,
        options: StageOptions,
    ) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            if not candidate.fixture_path:
                raise StageExecutionError(
                    f"NLI seed {candidate.source_item_id} is missing fixture_html; live fetching is not implemented yet."
                )
            fixture_path = Path(candidate.fixture_path)
            parsed_fixture = parse_nli_fixture_html(fixture_path)
            asset_refs = [
                AssetReference(
                    reference=reference,
                    resolved_path=str((fixture_path.parent / reference).resolve()),
                )
                for reference in parsed_fixture.assets
            ]
            record_data = candidate.model_dump()
            metadata = dict(record_data.pop("raw_metadata"))
            record_data.pop("title", None)
            if parsed_fixture.description:
                metadata["description"] = parsed_fixture.description
            enriched.append(
                EnrichedCandidateRecord(
                    **record_data,
                    title=parsed_fixture.title or candidate.title,
                    raw_rights_text=parsed_fixture.rights,
                    asset_references=asset_refs,
                    metadata=metadata,
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            assets: list[AcquiredAsset] = []
            for index, asset in enumerate(item.asset_references, start=1):
                resolved = Path(asset.resolved_path or "")
                extension = resolved.suffix or ".svg"
                destination = output_dir / item.item_id / f"page_{index}{extension}"
                copy_file(resolved, destination)
                assets.append(
                    AcquiredAsset(
                        item_id=item.item_id,
                        path=str(destination),
                        sha256=sha256_file(destination),
                        media_type=asset.media_type,
                    )
                )
            acquired_items.append(AcquiredItemRecord(**item.model_dump(), acquired_assets=assets))
        return acquired_items
