"""Network-free tests for Commons scan files as an F8f text-source scan source (Route C): hocrgen.fetchers.commons_scan."""

from __future__ import annotations

import datetime as dt
import json

from hocrgen.fetchers import commons_scan as cs
from hocrgen.fetchers import ia_justification as ij
from hocrgen.tools import benyehuda_nli_alignment as tool
from hocrgen.tools import benyehuda_nli_lines as lines

AS_OF = dt.date(2026, 11, 18)
THUMB = ("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Example_code.pdf/page1-1920px-Example_code.pdf.jpg"
         "?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail")


def _api(source: str, templates: str = "{{PD-old-70}}", mime: str = "application/pdf", description: str = "A code, vol. 1") -> dict:
    wikitext = ("=={{int:filedesc}}==\n{{Information\n|description=" + description + "\n|source=" + source
                + "\n|author=Joseph Karo\n|date=1893\n}}\n\n=={{int:license-header}}==\n" + templates + "\n")
    return {"query": {"pages": [{
        "pageid": 123, "title": "File:Example code.pdf",
        "revisions": [{"revid": 456, "slots": {"main": {"content": wikitext}}}],
        "imageinfo": [{"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Example_code.pdf",
                       "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example_code.pdf",
                       "thumburl": THUMB, "sha1": "f" * 40, "mime": mime, "size": 1000, "width": 1240, "height": 1754,
                       "pagecount": 3, "extmetadata": {"Categories": {"value": "Shulchan Arukh|PDF files in Hebrew"}}}]}]}}


SEFARIA_SOURCE = "Scan by Sefaria of NNL_ALEPH001157672"


def _version(source: str = "https://www.nli.org.il/he/books/NNL_ALEPH001157672/NLI", digitized: bool = True) -> dict:
    return {"title": "Shulchan Arukh", "versionTitle": "Lemberg, 1893", "versionSource": source, "digitizedBySefaria": digitized}


def test_the_file_record_reads_the_information_template_and_licence() -> None:
    f = cs.commons_file_record(_api(SEFARIA_SOURCE))
    assert f["title"] == "File:Example code.pdf" and f["page_count"] == 3 and f["file_page_revision_id"] == 456
    assert f["source"] == SEFARIA_SOURCE and f["licence_templates"] == ["PD-old-70"]


def test_a_sefaria_scan_records_whether_its_version_is_the_same_copy() -> None:
    d = cs.decide_commons_rights(cs.commons_file_record(_api(SEFARIA_SOURCE)), sefaria_version=_version())
    assert d.accepted and d.source_class == cs.SOURCE_CLASS_COMMONS_SEFARIA
    assert d.record["digitizer"]["name"] == "Sefaria"
    assert d.record["nli_record_ids"] == ["990011576720205171"]
    assert d.record["edition_evidence"]["same_copy_as_sefaria_version"] is True
    # A version of another copy, or one Sefaria did not digitize, is recorded but does not reject the file (decision 10).
    for version, check in ((_version("https://www.nli.org.il/he/books/NNL_ALEPH001234567/NLI"), "commons_sefaria_scan_nli_record_mismatch"),
                           (_version(digitized=False), "commons_sefaria_version_not_digitized_by_sefaria")):
        d = cs.decide_commons_rights(cs.commons_file_record(_api(SEFARIA_SOURCE)), sefaria_version=version)
        assert d.accepted and d.record["digitizer"]["name"] == "unrecorded"
        assert d.record["edition_evidence"] == {**d.record["edition_evidence"], "same_copy_as_sefaria_version": False, "check": check}


def test_no_recorded_scan_source_is_accepted_under_decision_10() -> None:
    d = cs.decide_commons_rights(cs.commons_file_record(_api("[http://www.hebrewbooks.org/43956 HebrewBooks]")))
    assert d.accepted and d.source_class == cs.SOURCE_CLASS_COMMONS
    assert d.record["digitizer"]["name"] == "unrecorded"


def test_the_gate_rejects_restrictive_missing_licence_google_and_non_scans() -> None:
    cases = {
        "commons_restrictive_template:CC-BY-NC-4.0": _api(SEFARIA_SOURCE, templates="{{PD-old-70}}{{CC-BY-NC-4.0}}"),
        "commons_no_public_domain_template": _api(SEFARIA_SOURCE, templates="{{self|cc-by-sa-4.0}}"),
        "commons_google_scan_needs_wikisource_hygiene": _api("Digitized by Google from a library copy"),
        "commons_not_a_scan_file:audio/ogg": _api(SEFARIA_SOURCE, mime="audio/ogg"),
    }
    for reason, api in cases.items():
        d = cs.decide_commons_rights(cs.commons_file_record(api), sefaria_version=_version())
        assert not d.accepted and d.reason == reason, (reason, d.record["failed_conditions"])


def test_page_canvases_use_per_page_thumbnails() -> None:
    canvases = cs.commons_canvases(cs.commons_file_record(_api(SEFARIA_SOURCE)))
    assert [c["label"] for c in canvases] == ["1", "2", "3"]
    assert canvases[2]["image_url"].endswith("/page3-1920px-Example_code.pdf.jpg")
    assert canvases[0]["@id"].endswith("Example_code.pdf?page=1")


def _wikidata(qid: str, died: str) -> ij.WikidataSnapshot:
    claims = {"P570": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": died, "precision": 11}}}}]}
    entity = {"entities": {qid: {"id": qid, "labels": {"en": {"language": "en", "value": "Joseph Karo"}}, "claims": claims}}}
    return ij.wikidata_snapshot_from_bytes(qid, json.dumps(entity).encode())


ROW = {"ID": "sefaria_example", "source_edition": "Lemberg, 1893", "authors": "Joseph Karo", "author_uris": "http://www.wikidata.org/entity/Q1",
       "translators": "", "translator_uris": "", "editors": "", "editor_uris": "", "annotators": "", "annotator_uris": ""}


def test_the_rights_justification_and_the_derivation_blocker() -> None:
    f = cs.commons_file_record(_api(SEFARIA_SOURCE))
    d = cs.decide_commons_rights(f, sefaria_version=_version())
    ok = cs.build_commons_rights_justification(f, d, catalogue_row=ROW, wikidata={"Q1": _wikidata("Q1", "+1575-03-24T00:00:00Z")},
                                               as_of=AS_OF, api_snapshot_sha256="0" * 64, image_urls=[THUMB])
    assert ok.accepted and ok.record["id"].startswith("rj:commons:Example_code.pdf:")
    assert ok.record["work_public_domain"]["israel_status"]["status"] == "pd_il"
    assert ok.record["digitizer"]["source_established"]["reason"] == "sefaria_version_cites_same_nli_record"
    late = cs.build_commons_rights_justification(f, d, catalogue_row=ROW, wikidata={"Q1": _wikidata("Q1", "+1990-01-01T00:00:00Z")},
                                                 as_of=AS_OF, api_snapshot_sha256="0" * 64, image_urls=[THUMB])
    assert not late.accepted and late.reason.startswith("justification_not_pd_in_israel")
    scan = {"source": cs.COMMONS_SOURCE, "rights_decision": d.evidence()}
    assert cs.commons_derivation_blocker(scan) == "commons_rights_justification_missing"
    assert cs.commons_derivation_blocker({**scan, "rights_justification": ok.record}) is None
    assert cs.commons_derivation_blocker({"source": "internet_archive"}) is None
    assert lines.rights_accepted(scan)
    assert lines.line_id("cm_0123456789ab", 4, 7, source=cs.COMMONS_SOURCE) == "cm_0123456789ab_c0004_l007"


def test_align_accepts_a_commons_source() -> None:
    args = tool.parse_args(["align", "--source", "commons", "--text-source", "sefaria", "--text-record", "r.json", "--text", "t.txt",
                            "--manifest", "api.json", "--work-dir", "w", "--out-dir", "o", "--generated-on", "2026-11-18"])
    assert args.source == "commons"
