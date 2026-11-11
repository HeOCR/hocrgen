"""Network-free tests for the Sefaria and Project Gutenberg text sources (hocrgen.fetchers.text_sources) and their
use by the F8f aligner's rights justification."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from hocrgen.fetchers import text_sources as ts
from hocrgen.fetchers import ia_justification as ij

NLI_SOURCE = "https://www.nli.org.il/he/books/NNL_ALEPH001922255"


def _version(**fields: object) -> dict:
    version = {"title": "Midrash Lekach Tov on Ruth", "heTitle": "מדרש לקח טוב על רות", "language": "he", "actualLanguage": "he",
               "versionTitle": "Perush Lekach Tov. Pesikta Zutrata on Ruth, Mainz 1887", "versionSource": NLI_SOURCE,
               "license": "Public Domain", "digitizedBySefaria": True,
               "schema": {"nodes": [{"enTitle": "Introduction"}, {"enTitle": ""}]},
               "text": {"Introduction": ["<b>הקדמה.</b> כת' (משלי כ\"ב ט')"], "": [["<b>ויהי בימי.</b> - אמ\"ר שמואל", "שני"]]}}
    version.update(fields)
    return {k: v for k, v in version.items() if v is not None}


# --- the licence gate ---------------------------------------------------------------------------------------


def test_public_domain_version_citing_a_printing_is_accepted():
    decision = ts.decide_sefaria_licence(_version())
    assert decision.accepted and decision.reason == ts.ACCEPTED
    assert decision.printing["kind"] == "nli_record" and decision.printing["id"] == "NNL_ALEPH001922255"
    assert decision.printing["year_in_title"] == [1887]


@pytest.mark.parametrize(
    ("licence", "reason"),
    [
        ("CC-BY-NC", ts.REASON_NON_COMMERCIAL),
        ("CC-BY-NC-SA 4.0", ts.REASON_NON_COMMERCIAL),
        ("unknown", ts.REASON_UNKNOWN),
        ("", ts.REASON_UNKNOWN),
        (None, ts.REASON_UNKNOWN),
        ("CC-BY", ts.REASON_ATTRIBUTION),
        ("CC-BY-SA", ts.REASON_ATTRIBUTION),
        ("CC0 1.0", ts.REASON_OTHER_LICENCE),  # exact strings only
        ("cc0", ts.REASON_OTHER_LICENCE),
        ("public domain", ts.REASON_OTHER_LICENCE),  # exact label only
        ("Public Domain ", ts.REASON_OTHER_LICENCE),
    ],
)
def test_every_other_licence_is_rejected(licence, reason):
    decision = ts.decide_sefaria_licence(_version(license=licence))
    assert not decision.accepted and decision.reason == reason


def test_cc0_is_accepted_like_public_domain_but_still_needs_a_printing():
    decision = ts.decide_sefaria_licence(_version(license="CC0"))
    assert decision.accepted and decision.licence == "CC0"
    no_print = ts.decide_sefaria_licence(_version(license="CC0", versionSource="https://www.sefaria.org"))
    assert not no_print.accepted and no_print.reason == ts.REASON_NO_PRINTING


@pytest.mark.parametrize(
    "fields",
    [
        {"versionSource": "http://www.toratemetfreeware.com/"},  # Torat Emet: PD with no printing
        {"versionSource": "https://www.sefaria.org"},
        {"versionSource": None},
        {"versionTitle": "Torat Emet 357"},  # a catalogue record but no year in the title
    ],
)
def test_public_domain_with_no_printing_is_rejected(fields):
    decision = ts.decide_sefaria_licence(_version(**fields))
    assert not decision.accepted and decision.reason == ts.REASON_NO_PRINTING


def test_non_hebrew_version_is_rejected():
    assert ts.decide_sefaria_licence(_version(actualLanguage="en", language="en")).reason == ts.REASON_NOT_HEBREW


def test_ia_and_gutenberg_records_name_a_printing():
    assert ts.printing_evidence("https://archive.org/details/abc00x", "Vilna 1884")["kind"] == "internet_archive_item"
    assert ts.printing_evidence("http://www.gutenberg.org/ebooks/43740", "Frankfurt am Main, 1881")["id"] == "43740"
    assert ts.printing_evidence("https://www.nli.org.il/he/books/NNL_ALEPH990019311530205171/NLI", "Berlin, 1903")["id"] == "NNL_ALEPH990019311530205171"


RDF = "<rdf><dcterms:rights>Public domain in the USA.</dcterms:rights></rdf>"
PG = """The Project Gutenberg eBook

Credits: Produced by A & the online
        Distributed Proofreaders Canada team. This file was produced from
        images generously made available by The Internet
        Archive/Canadian Libraries

*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

*חיים מאיר* /הלוי/ _הורוויץ_.
היכא דלא כתב ניקוּד
והגדולה והגדולה

                       הערות על המהדורה אלקטרונית

הטעויות דפוס הבאות תוקנו:

  * ע׳ 9, ש׳ 5: היכא רלא כתב ← היכא דלא כתב
  * ע׳ 20, ש׳ 2: והגדזלה ← והגדולה
  * ע׳ 9, ש׳ 8: מרכאות סוגרות חסרות

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***
license text
"""


def test_gutenberg_is_accepted_only_for_the_scan_it_was_proofread_from():
    ok = ts.decide_gutenberg_licence("43740", RDF, PG, ia_identifier="betnekhothahalak01horouoft")
    assert ok.accepted and ok.licence == "Public domain in the USA." and ok.printing["proofread_from"].endswith("betnekhothahalak01horouoft")
    assert ts.decide_gutenberg_licence("43740", RDF, PG, ia_identifier="other00x").reason == ts.REASON_GUTENBERG_OTHER_SCAN
    assert ts.decide_gutenberg_licence("99999", RDF, PG, ia_identifier="betnekhothahalak01horouoft").reason == ts.REASON_GUTENBERG_NOT_LISTED
    no_pd = RDF.replace("Public domain in the USA.", "Copyrighted.")
    assert ts.decide_gutenberg_licence("43740", no_pd, PG, ia_identifier="betnekhothahalak01horouoft").reason == ts.REASON_GUTENBERG_RIGHTS
    other = PG.replace("Archive/Canadian Libraries", "Archive")
    assert ts.decide_gutenberg_licence("43740", RDF, other, ia_identifier="betnekhothahalak01horouoft").reason == ts.REASON_GUTENBERG_CREDITS


def test_gutenberg_body_strips_framing_markup_and_reverts_unique_corrections():
    text, stats = ts.gutenberg_body(PG)
    assert "Credits" not in text and "license text" not in text and "הערות על המהדורה" not in text
    assert text.splitlines()[0] == "חיים מאיר הלוי הורוויץ."
    assert "היכא רלא כתב" in text  # the print's reading, reverted from the transcriber's correction
    assert "והגדולה והגדולה" in text  # corrected reading occurs twice: kept, reported
    assert "ניקוד" in text  # niqqud removed
    assert len(stats["corrections_reverted_to_print"]) == 1 and stats["corrections_kept"][0]["why_kept"].startswith("corrected reading occurs 2")
    assert stats["transcriber_corrections"] == 2  # the note without an arrow is not a correction


# --- the normaliser -----------------------------------------------------------------------------------------


def test_normaliser_removes_anchors_footnotes_tags_dash_and_niqqud():
    raw = ('﻿<i data-commentator="Notes and Corrections" data-order="1"></i> <b>ויהי בימי.</b> - אמ"ר '
           'שמואל<sup class="footnote-marker">1</sup><i class="footnote"> הערה של העורך</i> בַּר נחמני<br><small>קטן</small>'
           ' &amp; ר׳ עקיבא ״ — דבר־אחר')
    counts = ts.Counter()
    out = ts.normalise_sefaria_segment(raw, counts)
    assert out == 'ויהי בימי. אמ"ר שמואל בר נחמני\nקטן & ר׳ עקיבא ״ — דבר־אחר'
    assert counts["commentator_anchors"] == 1 and counts["footnotes"] == 1 and counts["bold_dashes"] == 1
    assert counts["format_chars"] == 1 and counts["points_removed"] == 2


def test_sefaria_text_follows_schema_order_and_parts():
    text, stats = ts.sefaria_text(_version())
    assert text.splitlines() == ["הקדמה. כת' (משלי כ\"ב ט')", "", 'ויהי בימי. אמ"ר שמואל', "שני"]
    only, _ = ts.sefaria_text(_version(), parts=[""])
    assert only.splitlines() == ['ויהי בימי. אמ"ר שמואל', "שני"]
    with pytest.raises(ValueError):
        ts.sefaria_text(_version(), parts=["Missing"])
    assert stats["segments"] == 3 and stats["hebrew_letters"] > 0


def test_text_stats_count_abbreviation_marks():
    stats = ts.text_stats('ר״ע אמר ז"ל ע\' שלום (שם)')
    assert stats["abbreviation_marks"] == 3 and stats["hebrew_words"] == 6
    assert stats["abbreviation_marks_per_1000_letters"] == round(1000 * 3 / stats["hebrew_letters"], 2)


# --- the text record ----------------------------------------------------------------------------------------

PEOPLE = [{"name": "Tobiah ben Eliezer", "role": "author", "qid": "Q1468644"}, {"name": "Seckel Bamberger", "role": "editor", "qid": "Q2263731"}]


def _record(**overrides: object) -> tuple[dict, str]:
    version = _version()
    text, stats = ts.sefaria_text(version)
    kwargs = dict(work_id="sefaria_lekach_tov_ruth", decision=ts.decide_sefaria_licence(version), title=version["title"],
                  he_title=version["heTitle"], text=text, stats=stats, api_url=ts.sefaria_download_url(version["title"], version["versionTitle"]),
                  snapshot_sha256="ab" * 32, contributors=PEOPLE, publication={"place": "Mainz", "year": 1887}, script="square",
                  normaliser=ts.SEFARIA_NORMALISER, digitizer=ts.SEFARIA_DIGITIZER)
    kwargs.update(overrides)
    return ts.build_text_record(**kwargs), text


def test_text_record_carries_the_provenance_fields():
    record, text = _record()
    for key in ts.PROVENANCE_FIELDS:
        assert record[key]
    assert record["text_licence"] == "Public Domain" and record["text_version_source"] == NLI_SOURCE
    assert record["text_api_url"].startswith("https://www.sefaria.org/download/version/Midrash%20Lekach%20Tov%20on%20Ruth%20-%20he%20-")
    assert record["text_digitizer"] == "Sefaria" and record["script"] == "square"
    assert ts.check_text_record(record, text) is None
    work = ts.work_fields(record)
    assert work["work_id"] == "sefaria_lekach_tov_ruth" and work["pby_id"] is None and work["text_licence"] == "Public Domain"


@pytest.mark.parametrize(
    "overrides",
    [
        {"work_id": "lekach_tov_ruth"},
        {"work_id": "gutenberg_1"},
        {"script": "cursive"},
        {"contributors": [{"name": "X", "role": "author", "qid": None}]},
        {"contributors": [{"name": "X", "role": "editor", "qid": "Q1"}]},  # no author, not anonymous
        {"publication": {"place": "Mainz"}},
        {"decision": ts.decide_sefaria_licence(_version(license="CC-BY-NC"))},
    ],
)
def test_text_record_refuses_bad_input(overrides):
    with pytest.raises(ValueError):
        _record(**overrides)


def test_anonymous_work_needs_no_author():
    record, _ = _record(contributors=[PEOPLE[1]], anonymous_work={"note": "traditional attribution only"})
    assert record["anonymous_work"]["note"] == "traditional attribution only"
    assert "anonymous_work" in ts.justification_row(record)


def test_check_text_record_fails_closed():
    record, text = _record()
    assert ts.check_text_record(record, text + "x") == "text file sha256 differs from the text record"
    assert "licence gate" in ts.check_text_record({**record, "text_licence": "CC-BY-NC"}, text)
    tampered = json.loads(json.dumps(record))
    tampered["text_licence_decision"]["evidence"]["versionSource"] = "http://www.toratemetfreeware.com/"
    assert ts.REASON_NO_PRINTING in ts.check_text_record(tampered, text)
    assert ts.check_text_record({**record, "format": "x"}, text).startswith("text record format")


# --- the rights justification from a text record ------------------------------------------------------------

AS_OF = dt.date(2026, 11, 11)


def _entity(qid: str, label: str, died: str) -> ij.WikidataSnapshot:
    claims = {"P570": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": died, "precision": 11}}}}]}
    data = json.dumps({"entities": {qid: {"id": qid, "labels": {"en": {"language": "en", "value": label}}, "claims": claims}}}).encode()
    return ij.wikidata_snapshot_from_bytes(qid, data)


WIKIDATA = {"Q1468644": _entity("Q1468644", "Tobiah ben Eliezer", "+1150-00-00T00:00:00Z"),
            "Q2263731": _entity("Q2263731", "Seckel Bamberger", "+1934-10-23T00:00:00Z")}
METADATA = {"metadata": {"identifier": "lekachtobpesikta00bamb", "mediatype": "texts", "date": "1887", "publisher": "Würzburg A. Boegler",
                         "contributor": "Robarts - University of Toronto", "imagecount": "3", "creator": "Bamberger, Seckel, 1863-1934"}}


def _justify(row: dict, wikidata: dict = WIKIDATA, metadata: dict = METADATA) -> ij.JustificationResult:
    return ij.build_ia_rights_justification(metadata, catalogue_row=row, wikidata=wikidata, as_of=AS_OF, metadata_sha256="m",
                                            manifest_url="u", manifest_sha256="s", canvas_count=3, image_urls=[],
                                            contributors_listed_in="text_record")


def test_justification_counts_text_record_editors():
    record, _ = _record()
    result = _justify(ts.justification_row(record))
    assert result.accepted, result.failures
    people = {c["name"]: c for c in result.record["work_public_domain"]["contributors"]}
    assert people["Seckel Bamberger"]["role"] == "editor" and people["Seckel Bamberger"]["death_year"] == 1934
    assert people["Seckel Bamberger"]["listed_in"] == "text_record.editors"
    assert result.record["work_public_domain"]["text_work_id"] == "sefaria_lekach_tov_ruth"
    assert "pby_id" not in result.record["work_public_domain"]


def test_justification_rejects_an_editor_still_protected():
    record, _ = _record()
    late = {**WIKIDATA, "Q2263731": _entity("Q2263731", "Seckel Bamberger", "+1960-01-01T00:00:00Z")}
    result = _justify(ts.justification_row(record), late)
    assert not result.accepted and "justification_not_pd_in_israel:Seckel Bamberger:1960" in result.failures


def test_justification_of_an_anonymous_work_checks_its_editor():
    record, _ = _record(contributors=[PEOPLE[1]], anonymous_work={"note": "traditional attribution only"})
    result = _justify(ts.justification_row(record))
    assert result.accepted, result.failures
    status = result.record["work_public_domain"]["israel_status"]
    assert status["basis"] == "anonymous_work_and_named_contributors_died_over_70_years_ago" and "ss. 38 and 40" in status["law"]
    # The IA creator field's life dates also count (cited as such); with neither source the item is rejected.
    assert _justify(ts.justification_row(record), {}).accepted
    bare = {"metadata": {k: v for k, v in METADATA["metadata"].items() if k != "creator"}}
    missing = _justify(ts.justification_row(record), {}, bare)
    assert not missing.accepted and any(f.startswith("justification_missing_death_year") for f in missing.failures)


def test_pby_rows_keep_their_justification_shape():
    row = {"ID": "31623", "authors": "Tobiah ben Eliezer", "author_uris": "https://wikidata.org/wiki/Q1468644", "translators": "",
           "translator_uris": "", "source_edition": "Mainz, 1887", "editors": "Seckel Bamberger", "editor_uris": "Q2263731"}
    result = ij.build_ia_rights_justification(METADATA, catalogue_row=row, wikidata=WIKIDATA, as_of=AS_OF, metadata_sha256="m",
                                              manifest_url="u", manifest_sha256="s", canvas_count=3, image_urls=[])
    assert result.accepted and result.record["work_public_domain"]["pby_id"] == "31623"
    # A PBY row's editor columns are not read: PBY has none, and its listing is unchanged.
    assert all(c["listed_in"] != "pby_catalogue.editors" for c in result.record["work_public_domain"]["contributors"])


# --- align --text-source ------------------------------------------------------------------------------------


def _align_args(tmp_path, record: dict, text: str, *extra: str):
    from hocrgen.tools import benyehuda_nli_alignment as tool

    (tmp_path / "r.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "t.txt").write_text(text, encoding="utf-8")
    args = tool.parse_args(["align", "--source", "ia", "--text-source", "sefaria", "--text-record", str(tmp_path / "r.json"),
                            "--text", str(tmp_path / "t.txt"), "--manifest", str(tmp_path / "m.json"), "--ia-identifier", "x00",
                            "--work-dir", str(tmp_path / "w"), "--out-dir", str(tmp_path / "o"), "--generated-on", "2026-11-11", *extra])
    return tool, args


def test_align_takes_the_text_record_in_place_of_a_catalogue_row(tmp_path):
    record, text = _record()
    tool, args = _align_args(tmp_path, record, text)
    row, edition, work = tool.text_source_inputs(args)
    assert edition == text and row["ID"] == "sefaria_lekach_tov_ruth" and "Seckel Bamberger" in row["editors"]
    assert work["work_id"] == "sefaria_lekach_tov_ruth" and work["text_path"] == "text/sefaria_lekach_tov_ruth.txt"
    assert {k: work[k] for k in ts.PROVENANCE_FIELDS} == {k: record[k] for k in ts.PROVENANCE_FIELDS}


def test_align_refuses_a_tampered_text_or_record_and_non_ia_scans(tmp_path):
    record, text = _record()
    tool, args = _align_args(tmp_path, record, text + "x")
    assert tool.text_source_inputs(args) == "text file sha256 differs from the text record"
    tool, args = _align_args(tmp_path, {**record, "text_source": "gutenberg"}, text)
    assert "not 'sefaria'" in tool.text_source_inputs(args)
    tool, args = _align_args(tmp_path, record, text)
    args.source = "nli"
    assert "Internet Archive scans only" in tool.text_source_inputs(args)
    args.source, args.text_source, args.catalogue = "ia", "pby", None
    assert "--catalogue and --pby-id are required" in tool.text_source_inputs(args)
