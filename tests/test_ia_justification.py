"""Network-free tests for the per-item rights justification of Internet Archive scans (hocrgen.fetchers.ia_justification)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.fetchers import ia_iiif as ia
from hocrgen.fetchers import ia_justification as ij
from hocrgen.tools import benyehuda_nli_alignment as tool

FIXTURE = Path(__file__).parent / "fixtures" / "ia"
IDENTIFIER = "hegyoneshpinozah00rubi"
AS_OF = dt.date(2026, 11, 10)
RUBIN = "Q2215049"
ROW = {"ID": "31623", "authors": "שלמה רובין", "translators": "", "author_uris": f"https://wikidata.org/wiki/{RUBIN}",
       "translator_uris": "", "source_edition": "קראקוב: אהרן פויסט"}
NLI_RECORD = "990012345678905171"


def _metadata(**fields: object) -> dict:
    md = dict(json.loads((FIXTURE / f"metadata_{IDENTIFIER}.json").read_text(encoding="utf-8"))["metadata"])
    md["imagecount"] = "3"
    for key, value in fields.items():
        if value is None:
            md.pop(key, None)
        else:
            md[key] = value
    return {"metadata": md}


def _entity(qid: str, label: str, died: str | None = None, precision: int = 11) -> bytes:
    claims = {}
    if died:
        claims["P570"] = [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": died, "precision": precision}}}}]
    return json.dumps({"entities": {qid: {"id": qid, "labels": {"en": {"language": "en", "value": label}}, "claims": claims}}}).encode()


def _wd(*entities: tuple[str, str, str | None]) -> dict[str, ij.WikidataSnapshot]:
    return {qid: ij.wikidata_snapshot_from_bytes(qid, _entity(qid, label, died)) for qid, label, died in entities}


WIKIDATA = _wd((RUBIN, "Salomon Rubin", "+1910-12-27T00:00:00Z"))


def _justify(metadata: dict | None = None, *, row: dict | None = None, wikidata: dict | None = None, nli=None) -> ij.JustificationResult:
    return ij.build_ia_rights_justification(
        metadata or _metadata(),
        catalogue_row=row or ROW,
        wikidata=WIKIDATA if wikidata is None else wikidata,
        as_of=AS_OF,
        metadata_sha256="d" * 64,
        manifest_url=ia.IA_MANIFEST_URL.format(identifier=IDENTIFIER),
        manifest_sha256="m" * 64,
        canvas_count=3,
        image_urls=["https://iiif.archive.org/image/iiif/3/x%2Fp0.jp2"],
        nli_snapshot=nli,
    )


def _accepted(result: ij.JustificationResult) -> dict:
    assert result.accepted, result.failures
    assert result.record is not None
    return result.record


# --- the three accepted kinds -------------------------------------------------------------------------------


def test_plain_library_scan_is_justified_with_no_origin_label() -> None:
    record = _accepted(_justify())
    assert record["format"] == "hocrgen.rights_justification.v1" and record["as_of"] == "2026-11-10"
    assert record["source_class"] == "ia_library_scan_no_licence_field"
    assert record["route"]["name"] == "internet_archive"
    assert record["route"]["url"] == [f"https://archive.org/metadata/{IDENTIFIER}", f"https://iiif.archive.org/iiif/3/{IDENTIFIER}/manifest.json",
                                      "https://iiif.archive.org/image/iiif/3/x%2Fp0.jp2"]
    work = record["work_public_domain"]
    [rubin] = work["contributors"]
    assert rubin["name"] == "שלמה רובין" and rubin["role"] == "author" and rubin["death_year"] == 1910
    source = rubin["death_year_source"]
    assert source["kind"] == "wikidata_p570" and source["qid"] == RUBIN
    assert source["url"] == f"https://www.wikidata.org/wiki/Special:EntityData/{RUBIN}.json"
    assert source["sha256"] == hashlib.sha256(_entity(RUBIN, "Salomon Rubin", "+1910-12-27T00:00:00Z")).hexdigest()
    assert work["publication_year"]["year"] == 1897 and work["publication_year"]["sources"][0]["source"] == "ia_metadata_date"
    assert work["place"] == {"place": "rao", "source": "ia_metadata_publisher", "value": "rao : Be-hotsaat A. Fois"}
    assert work["israel_status"]["status"] == "pd_il" and work["israel_status"]["basis"] == "author_died_over_70_years_ago"
    assert work["israel_status"]["law"] == "Copyright Act 2007, s. 38"
    assert work["us_status"] == {"status": "pd_us", "reason": "published before 1931", "publication_year": 1897}
    assert "pby_catalogue: authors, translators (author_uris, translator_uris)" in work["contributors_basis"]["checked"]
    faithful = record["faithful_reproduction"]
    assert "Feist" in faithful["text"] and "Bridgeman" in faithful["text"] and "Interlego" in faithful["text"]
    assert faithful["evidence"]["mediatype"] == "texts" and faithful["evidence"]["scanner"] == "scribe10.toronto.archive.org"
    assert faithful["evidence"]["imagecount"] == 3 and faithful["evidence"]["consistent"] is True
    assert record["digitizer"]["name"] == "Robarts - University of Toronto"
    assert record["origin_label"] is None and record["why_not_binding"] is None
    assert record["hygiene"] == "none"
    assert record["route_terms"]["url"] == "https://archive.org/about/terms.php"
    assert record["route_terms"]["licenseurl"] is None and record["route_terms"]["rights"] is None
    assert record["decision_refs"] == [
        "planning/decisions/2026-11-10-legal-strategy.md",
        "docs/legal/2026-11-10_legal_strategy.md",
        "planning/decisions/2026-11-09-internet-archive-library-scans.md",
    ]
    assert record["summary"] == (
        "Public-domain book (author d. 1910, printed 1897); faithful scan digitized by Robarts - University of Toronto;"
        f" fetched from the Internet Archive ({IDENTIFIER}); no new right in the scan and no contract binds its reuse."
    )


def test_the_id_is_a_stable_hash_of_the_canonical_record() -> None:
    record = _accepted(_justify())
    body = {key: value for key, value in record.items() if key != "id"}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert record["id"] == f"rj:{IDENTIFIER}:{digest[:12]}"
    assert _justify().id == record["id"]
    other = ij.build_ia_rights_justification(
        _metadata(), catalogue_row=ROW, wikidata=WIKIDATA, as_of=dt.date(2027, 1, 1), metadata_sha256="d" * 64,
        manifest_url="u", manifest_sha256="m" * 64, canvas_count=3, image_urls=[],
    )
    assert other.id != record["id"]


def test_google_digitized_item_is_justified_with_google_as_digitizer_and_origin_label() -> None:
    metadata = _metadata(identifier="bub_gb_AbCdEf123", contributor=None, sponsor="Google", scanner=None)
    record = _accepted(_justify(metadata))
    assert record["source_class"] == "ia_google_digitized_scan" and record["id"].startswith("rj:bub_gb_AbCdEf123:")
    assert record["digitizer"]["name"] == "Google"
    assert "identifier: bub_gb_AbCdEf123 (Google Books import pattern bub_gb_)" in record["digitizer"]["evidence"]
    assert "sponsor: Google" in record["digitizer"]["evidence"]
    assert record["origin_label"]["holder"] == "Google" and record["origin_label"]["label"] == "google_books_usage_guidelines"
    assert "not from Google" in record["why_not_binding"] and "2(a) and 2(c)" in record["why_not_binding"]
    assert record["hygiene"] == "pending"
    assert "digitized by Google" in record["summary"] and "(bub_gb_AbCdEf123), not from Google;" in record["summary"]


def _nli_snapshot(slug: str = "public-domain-non-commercial-use") -> ij.NliSnapshot:
    manifest = {"@id": f"https://iiif.nli.org.il/IIIFv21/{NLI_RECORD}/manifest",
                "license": [f"https://www.nli.org.il/contenteditors/pages-for-terms-of-use/{slug}"],
                "label": "הגיוני שפינוזה", "metadata": [{"label": "The Creator", "value": "רובין, שלמה, 1823-1910"}]}
    return ij.nli_snapshot_from_bytes(json.dumps(manifest).encode())


def test_nli_origin_item_carries_its_nli_evidence_and_label_from_a_saved_snapshot() -> None:
    metadata = _metadata(source=f"https://www.nli.org.il/he/books/NNL_ALEPH/{NLI_RECORD}")
    unchecked = _accepted(_justify(metadata))
    assert unchecked["source_class"] == "ia_nli_origin_scan"
    origin = unchecked["digitizer"]["origin"]
    assert origin["name"] == "National Library of Israel" and origin["nli_record_id"] == NLI_RECORD
    assert origin["evidence"] == [f"source: https://www.nli.org.il/he/books/NNL_ALEPH/{NLI_RECORD}"]
    assert unchecked["origin_label"]["checked"] is False and unchecked["origin_label"]["label"] is None
    assert "(including the maintainer ruling on NLI-origin files)" in unchecked["decision_refs"][0]
    record = _accepted(_justify(metadata, nli=_nli_snapshot()))
    label = record["origin_label"]
    assert label["holder"] == "National Library of Israel" and label["label"] == "public-domain-non-commercial-use"
    assert label["checked"] is True and label["nli_record_id"] == NLI_RECORD
    assert label["snapshot"]["url"] == f"https://iiif.nli.org.il/IIIFv21/{NLI_RECORD}/manifest"
    assert "public-domain-non-commercial-use" in record["why_not_binding"] and "National Library of Israel" in record["why_not_binding"]
    assert "from an NLI copy" in record["summary"]


def test_google_and_nli_origin_item_records_both_and_keeps_the_google_class() -> None:
    metadata = _metadata(identifier="bub_gb_X1", source=f"Digitized from an NLI copy, record {NLI_RECORD} (nli.org.il)")
    record = _accepted(_justify(metadata, nli=_nli_snapshot()))
    assert record["source_class"] == "ia_google_digitized_scan"
    assert record["digitizer"]["name"] == "Google" and record["digitizer"]["origin"]["nli_record_id"] == NLI_RECORD
    assert record["origin_label"]["holder"] == "Google" and record["origin_label"]["also"]["label"] == "public-domain-non-commercial-use"
    assert "not from Google or National Library of Israel" in record["why_not_binding"]


# --- rejections and the Israeli and US rules ----------------------------------------------------------------


def test_missing_death_year_after_1855_rejects() -> None:
    result = _justify(wikidata=_wd((RUBIN, "Salomon Rubin", None)), metadata=_metadata(creator="Rubin, S. (Salomon)"))
    assert not result.accepted and result.record is None
    assert result.reason == "justification_missing_death_year:שלמה רובין"


def test_no_wikidata_death_year_falls_back_to_ia_creator_life_dates() -> None:
    # The entity has no P570, so the IA creator "Rubin, S. (Salomon), 1823-1910" is used: its surname matches a
    # Wikidata label of the contributor's QID.
    record = _accepted(_justify(wikidata=_wd((RUBIN, "Salomon Rubin", None))))
    [rubin] = record["work_public_domain"]["contributors"]
    assert rubin["death_year"] == 1910
    assert rubin["death_year_source"] == {"kind": "ia_metadata_creator", "field": "creator", "value": "Rubin, S. (Salomon), 1823-1910",
                                          "death_year": 1910, "match": "surname"}
    assert rubin["notes"] == [f"wikidata_no_p570:{RUBIN}"]


def test_nli_authority_dates_match_a_hebrew_name_spelled_differently() -> None:
    # PBY spells the name with matres (רובין); NLI's authority string is matched letter-skeleton to letter-skeleton.
    row = {**ROW, "author_uris": ""}
    metadata = _metadata(creator=None, source=f"nli.org.il {NLI_RECORD}")
    record = _accepted(_justify(metadata, row=row, nli=_nli_snapshot()))
    [rubin] = record["work_public_domain"]["contributors"]
    assert rubin["death_year"] == 1910 and rubin["death_year_source"]["kind"] == "nli_authority"


def test_work_printed_in_or_before_1855_without_a_death_year_is_presumed_pd() -> None:
    result = _justify(_metadata(date="1834", creator="Rubin, S."), wikidata=_wd((RUBIN, "Salomon Rubin", None)))
    record = _accepted(result)
    status = record["work_public_domain"]["israel_status"]
    assert status["status"] == "pd_il" and status["basis"] == "presumption_decision_10"
    assert status["presumed_for"] == ["שלמה רובין"] and "1834" in status["reason"]
    assert any("decision 10" in ref for ref in record["decision_refs"])
    assert "presumed PD (decision 10)" in record["summary"]


def test_book_published_after_the_us_cutoff_is_accepted_with_us_status_not_established() -> None:
    record = _accepted(_justify(_metadata(date="1935"), wikidata=_wd((RUBIN, "Salomon Rubin", "+1940-01-01T00:00:00Z"))))
    us = record["work_public_domain"]["us_status"]
    assert us["status"] == "not_established" and us["publication_year"] == 1935
    assert "not before 1931" in us["reason"]
    assert record["summary"].endswith("; US status not established.")


def test_a_translator_who_died_too_recently_blocks_the_israeli_status() -> None:
    row = {**ROW, "translators": "מתרגם צעיר", "translator_uris": "https://wikidata.org/wiki/Q999"}
    wikidata = {**WIKIDATA, **_wd(("Q999", "Young Translator", "+1960-05-01T00:00:00Z"))}
    result = _justify(row=row, wikidata=wikidata)
    assert not result.accepted and result.reason == "justification_not_pd_in_israel:מתרגם צעיר:1960"
    # The same translator dead by 1955 passes, and is listed with its role.
    ok = _accepted(_justify(row=row, wikidata={**WIKIDATA, **_wd(("Q999", "Young Translator", "+1955-05-01T00:00:00Z"))}))
    roles = [(c["role"], c["death_year"]) for c in ok["work_public_domain"]["contributors"]]
    assert roles == [("author", 1910), ("translator", 1955)]
    assert ok["summary"].startswith("Public-domain book (author d. 1910, translator d. 1955, printed 1897)")


def test_editor_named_in_the_description_counts_with_ia_creator_dates() -> None:
    metadata = _metadata(description=["Text mit Einleitung und Commentar von Dawid Kohn"], creator=["Rubin, S. (Salomon), 1823-1910", "Kohn, David, 1838-1915"])
    record = _accepted(_justify(metadata))
    contributors = record["work_public_domain"]["contributors"]
    kohn = [c for c in contributors if c["name"] == "Dawid Kohn"]
    assert kohn and kohn[0]["role"] == "annotator" and kohn[0]["death_year"] == 1915
    assert kohn[0]["listed_in"] == "ia_metadata_description" and kohn[0]["death_year_source"]["kind"] == "ia_metadata_creator"
    assert record["work_public_domain"]["contributors_basis"]["other_named_creators_not_counted"] == []


@pytest.mark.parametrize(("date", "accepted"), [("1912", False), ("1850", True)])
def test_editor_without_a_death_year_follows_the_1855_rule(date: str, accepted: bool) -> None:
    metadata = _metadata(date=date, creator=["Rubin, S. (Salomon), 1823-1910", "Levi, Moshe, editor"])
    result = _justify(metadata)
    assert result.accepted is accepted
    if not accepted:
        assert result.reason == "justification_missing_death_year:Levi, Moshe"
    else:
        assert result.record["work_public_domain"]["israel_status"]["presumed_for"] == ["Levi, Moshe"]


def test_unmarked_extra_creators_are_listed_but_not_counted() -> None:
    record = _accepted(_justify(_metadata(creator=["Rubin, S. (Salomon), 1823-1910", "Luria, Yosef"])))
    assert record["work_public_domain"]["contributors_basis"]["other_named_creators_not_counted"] == [
        {"value": "Luria, Yosef", "source": "ia_metadata_creator", "death_year": None}
    ]


def test_publication_year_missing_and_inconsistent_imagecount_reject() -> None:
    no_year = _justify(_metadata(date=None), row={**ROW, "source_edition": "קראקוב: אהרן פויסט"})
    assert not no_year.accepted and no_year.reason == "justification_publication_year_missing"
    counts = _justify(_metadata(imagecount="40"))
    assert not counts.accepted and counts.reason == "justification_imagecount_inconsistent:40:3"


def test_a_gate_rejection_is_not_justified() -> None:
    result = _justify(_metadata(rights="All rights reserved"))
    assert not result.accepted and result.reason == "ia_gate_rejected:ia_rights_restrictive"


def test_wikidata_decade_precision_uses_the_latest_year_and_coarser_is_unusable() -> None:
    decade = ij.wikidata_snapshot_from_bytes("Q1", _entity("Q1", "X", "+1910-00-00T00:00:00Z", precision=8))
    assert ij.wikidata_death_year(decade)["death_year"] == 1919
    century = ij.wikidata_snapshot_from_bytes("Q1", _entity("Q1", "X", "+1900-00-00T00:00:00Z", precision=7))
    assert ij.wikidata_death_year(century) is None


def test_load_wikidata_snapshots_reads_a_directory(tmp_path: Path) -> None:
    data = _entity(RUBIN, "Salomon Rubin", "+1910-12-27T00:00:00Z")
    (tmp_path / f"{RUBIN}.json").write_bytes(data)
    loaded = ij.load_wikidata_snapshots(tmp_path)
    assert list(loaded) == [RUBIN] and loaded[RUBIN].sha256 == hashlib.sha256(data).hexdigest()


# --- back-fill --------------------------------------------------------------------------------------------


def _alignment(metadata_bytes: bytes) -> dict:
    manifest = json.loads((FIXTURE / f"manifest_v3_{IDENTIFIER}.json").read_text(encoding="utf-8"))
    scan = tool.ia_scan_record(
        json.loads(metadata_bytes), manifest, identifier=IDENTIFIER, manifest_url=ia.IA_MANIFEST_URL.format(identifier=IDENTIFIER),
        manifest_sha256="m" * 64, metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(), catalogue_row=ROW, wikidata=WIKIDATA, as_of=AS_OF,
    )
    assert isinstance(scan, dict)
    canvases = ia.ia_v3_canvases(manifest)
    return tool.alignment_report(
        work={"pby_id": "31623", "title": "t", "authors": "a", "source_edition": "e"}, scan=scan, pby_text="שלום עולם " * 30,
        pages=[[], [], []], canvases=canvases, canvas_indices=[0, 1, 2], ocr_engine="tesseract", image_width=1600, generated_on="2026-11-10",
    )


def test_justify_existing_alignment_rebuilds_the_same_record_without_realigning() -> None:
    metadata_bytes = json.dumps(_metadata()).encode()
    alignment = _alignment(metadata_bytes)
    expected = alignment["scan"].pop("rights_justification")
    result = ij.justify_existing_alignment(alignment, metadata_bytes, WIKIDATA, AS_OF, catalogue_row=ROW)
    assert result.accepted and result.record == expected
    rejected = ij.justify_existing_alignment(alignment, metadata_bytes, {}, AS_OF, catalogue_row=ROW)
    assert not rejected.accepted and rejected.reason == "justification_missing_death_year:שלמה רובין"


def test_justify_existing_alignment_checks_the_snapshot_and_the_work() -> None:
    metadata_bytes = json.dumps(_metadata()).encode()
    alignment = _alignment(metadata_bytes)
    assert ij.justify_existing_alignment(alignment, metadata_bytes + b" ", WIKIDATA, AS_OF, catalogue_row=ROW).reason == "justification_metadata_snapshot_mismatch"
    assert ij.justify_existing_alignment(alignment, metadata_bytes, WIKIDATA, AS_OF, catalogue_row={**ROW, "ID": "1"}).reason == "justification_catalogue_row_mismatch"
    nli = {"scan": {"nli_record_id": "99"}}
    assert ij.justify_existing_alignment(nli, metadata_bytes, WIKIDATA, AS_OF, catalogue_row=ROW).reason == "justification_not_an_ia_alignment"
