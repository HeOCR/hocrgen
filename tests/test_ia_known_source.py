"""Condition 3 of the IA gate as amended on 2026-11-18: an item whose description names its digitizer is a known
source (planning/decisions/2026-11-18-ia-known-source-named-digitizer.md). Network-free; the metadata is synthetic."""

from __future__ import annotations

from hocrgen.fetchers import ia_iiif as ia

BASE = {"identifier": "example-item-images", "mediatype": "texts", "scanner": "Internet Archive HTML5 Uploader 1.7.0",
        "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/"}
NLI_RECORD = "990012024480205171"


def _md(description: str) -> dict:
    return {"metadata": {**BASE, "description": description}}


def test_an_nli_mirror_naming_nli_and_its_record_is_accepted() -> None:
    d = ia.decide_ia_rights(_md(
        '<div><b>Source:</b> Scanned by the National Library of Israel from a copy in its holdings '
        f'(<a href="https://www.nli.org.il/he/books/NNL_ALEPH{NLI_RECORD}/NLI">here</a>).</div>'))
    assert d.accepted and d.reason == "ia_nli_origin_scan_accepted"
    ks = d.record["known_source"]
    assert ks["established"] and ks["reason"] == "item_cites_nli_record" and ks["nli_record_ids"] == [NLI_RECORD]
    assert d.record["digitizer"]["name"] == ia.DIGITIZER_NLI
    assert d.record["digitizer"]["source_established"]["decision_record"] == ia.KNOWN_SOURCE_DECISION_RECORD
    assert "Scanned by the National Library of Israel" in d.record["digitizer"]["evidence"][0]


def test_nli_named_without_a_record_is_still_rejected() -> None:
    d = ia.decide_ia_rights(_md("Scanned by the National Library of Israel."))
    assert not d.accepted
    assert d.record["failed_conditions"] == ["ia_anonymous_upload_no_known_library", "ia_nli_scan_cites_no_nli_record"]


SEFARIA_DESCRIPTION = ("Source: The full set was scanned by Sefaria in black-and-white "
                       '(<a href="https://www.nli.org.il/he/books/NNL_ALEPH990019359700205171/NLI">NLI</a>).')


def _version(**over) -> dict:
    return {"title": "Tur", "versionTitle": "Tur, Vilna, 1923", "digitizedBySefaria": True,
            "versionSource": "https://www.nli.org.il/he/books/NNL_ALEPH001935970/NLI", **over}


def test_a_sefaria_scan_needs_its_version_digitized_by_sefaria_with_the_same_nli_record() -> None:
    ok = ia.decide_ia_rights(_md(SEFARIA_DESCRIPTION), sefaria_version=_version())
    assert ok.accepted and ok.record["digitizer"]["name"] == ia.DIGITIZER_SEFARIA
    ks = ok.record["known_source"]
    assert ks["reason"] == "sefaria_version_cites_same_nli_record"
    assert ks["sefaria_version"]["nli_record_ids"] == ["990019359700205171"]  # the Aleph number in its record-id form

    cases = {
        None: "ia_sefaria_scan_needs_sefaria_version",
        "not_digitized": "ia_sefaria_version_not_digitized_by_sefaria",
        "other_record": "ia_sefaria_scan_nli_record_mismatch",
    }
    for case, reason in cases.items():
        version = None if case is None else _version(digitizedBySefaria=False) if case == "not_digitized" else \
            _version(versionSource="https://www.nli.org.il/he/books/NNL_ALEPH001234567/NLI")
        d = ia.decide_ia_rights(_md(SEFARIA_DESCRIPTION), sefaria_version=version)
        assert not d.accepted and d.record["failed_conditions"] == ["ia_anonymous_upload_no_known_library", reason]


def test_a_sefaria_statement_without_an_nli_record_is_rejected() -> None:
    d = ia.decide_ia_rights(_md("Scanned by Sefaria."), sefaria_version=_version())
    assert not d.accepted and d.record["failed_conditions"][-1] == "ia_sefaria_scan_cites_no_nli_record"


def test_a_named_library_digitizer_is_accepted() -> None:
    d = ia.decide_ia_rights(_md("<b>Source:</b> Scanned by&nbsp;Duke University Libraries&nbsp;from volumes in its collection."))
    assert d.accepted and d.record["digitizer"]["name"] == "Duke University Libraries"
    assert d.record["known_source"]["reason"] == "digitizer_named"


def test_a_description_that_names_no_digitizer_is_still_rejected() -> None:
    for description in ("Noda B'Yehuda<div>Warsaw, 1880 edition.</div>",
                        "Full text can be found here: http://www.sefaria.org/texts/Responsa/Radbaz",
                        "The set was uploaded in 2016 by Some_User in four parts.",
                        "Scanned by [email redacted] at home."):
        d = ia.decide_ia_rights(_md(description))
        assert not d.accepted
        assert d.record["failed_conditions"] == ["ia_anonymous_upload_no_known_library"], description
        assert d.record["known_source"]["statements"] == []


def test_a_library_contributor_needs_no_description() -> None:
    d = ia.decide_ia_rights({"metadata": {**BASE, "contributor": "Robarts - University of Toronto"}})
    assert d.accepted and d.record["known_source"] is None and d.reason == "ia_library_scan_accepted"


def test_restrictive_rights_still_reject_a_described_item() -> None:
    md = _md("Scanned by Duke University Libraries.")
    md["metadata"]["licenseurl"] = "https://creativecommons.org/licenses/by-nc/4.0/"
    d = ia.decide_ia_rights(md)
    assert not d.accepted and d.reason.startswith("ia_licence_non_commercial")
