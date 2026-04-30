from __future__ import annotations

from typing import Any

from hocrgen.manifests.models import AnnotationManifestItemRecord, AnnotationManifestRecord


def build_annotation_manifest(items: list[Any], *, subset_id: str) -> AnnotationManifestRecord:
    manifest_items = [
        AnnotationManifestItemRecord(
            item_id=item.item_id,
            source_id=item.source_id,
            split=item.split,
            annotation_status=item.annotation_status,
            transcription=item.transcription,
            layout_labels=list(item.layout_labels),
        )
        for item in items
    ]
    return AnnotationManifestRecord(
        subset_id=subset_id,
        annotated_item_count=sum(1 for item in manifest_items if item.annotation_status != "not_available"),
        transcription_item_count=sum(1 for item in manifest_items if item.transcription is not None),
        layout_label_item_count=sum(1 for item in manifest_items if item.layout_labels),
        items=manifest_items,
    )
