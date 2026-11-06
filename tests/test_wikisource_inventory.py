from __future__ import annotations

import json
from pathlib import Path

from hocrgen.fetchers.wikisource import index_exclusion_reasons
from hocrgen.tools import wikisource_inventory as inv

SUMMARY_JSON = Path("docs/wikisource_index_inventory.json")
SUMMARY_MD = Path("docs/wikisource_index_inventory.md")

INDEX_WIKITEXT = """{{:MediaWiki:Proofreadpage_index_template
|Type=book
|כותרת=ספר חורב
|מחבר=[[מחבר:רש"ר הירש|שמשון רפאל הירש]], [[מחבר:משה זלמן אהרנסון|משה זלמן אהרנסון]]
|מתרגם=
|עורך=יוסף פלוני
|שנה=תרנ"ג
|מקור=[[:קובץ:Horev.pdf]]
}}"""

FILE_WIKITEXT = """== {{int:filedesc}} ==
{{Book
| Author       = {{Creator:Samson Raphael Hirsch}}
| Translator   = {{Label|Q33127885|{{{1|{{int:lang}}}}}}} (1848-1906/8)
| Date         = 1893
| City         = Vilna
| institution  = [http://chabadlibrary.org/catalog Chabad-Lubavitch Library]
| Source       = [http://www.hebrewbooks.org/41650 hebrewbooks.org (41650)]
}}

== {{int:license-header}} ==
{{PD-scan|PD-old-auto-1923|deathyear=1908}}

[[Category:1893 books]]
"""


def _entity(death: str | None, precision: int = 11, labels: dict[str, str] | None = None) -> dict:
    claims = {}
    if death:
        claims["P570"] = [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": death, "precision": precision}}}}]
    return {"labels": {lang: {"value": value} for lang, value in (labels or {}).items()}, "aliases": {}, "claims": claims}


def _record(*, file_wikitext: str = FILE_WIKITEXT, index_wikitext: str = INDEX_WIKITEXT, metadata=None, entities=None, author_pages=None):
    metadata = metadata if metadata is not None else [{"name": "text", "value": [{"name": 0, "value": "ספר " * 300}]}]
    file_page = {
        "file_title": "Horev.pdf",
        "repository": "commons",
        "imageinfo": {"sha1": "abc", "size": 1, "mime": "application/pdf", "pagecount": 69, "user": "Uploader"},
        "revision": {"revid": 7, "sha1": "def"},
        "wikitext": file_wikitext,
        "extmetadata_categories": [],
        "metadata": metadata,
    }
    mentions = inv.index_creator_mentions(index_wikitext) + inv.commons_creator_mentions(file_wikitext)
    return inv.build_index_record(
        index_title="מפתח:Horev.pdf",
        index_page={"pageid": 336000, "revisions": [{"revid": 99, "slots": {"main": {"content": index_wikitext}}}]},
        file_page=file_page,
        mentions=mentions,
        author_pages=author_pages if author_pages is not None else {
            'רש"ר הירש': {"title": 'מחבר:רש"ר הירש', "wikidata": "Q76985", "death_year": 1888, "permalink": "https://he.wikisource.org/w/index.php?oldid=1", "display_name": "שמשון בן רפאל הירש"},
            "משה זלמן אהרנסון": {"title": "מחבר:משה זלמן אהרנסון", "wikidata": "Q33127885", "death_year": None, "permalink": None, "display_name": "משה זלמן אהרנסון"},
        },
        wiki_ids={},
        commons_creators={"Samson Raphael Hirsch": "Q76985"},
        entities=entities if entities is not None else {
            "Q76985": _entity("+1888-12-31T00:00:00Z"),
            "Q33127885": _entity("+1906-00-00T00:00:00Z", precision=9),
        },
        checked_at="2026-11-06",
    )


def test_field_and_mention_parsing() -> None:
    assert inv.template_field(INDEX_WIKITEXT, "שנה") == 'תרנ"ג'
    mentions = inv.index_creator_mentions(INDEX_WIKITEXT)
    assert [m.get("author_page") for m in mentions[:2]] == ['רש"ר הירש', "משה זלמן אהרנסון"]
    assert mentions[2] == {"role": "editor", "name": "יוסף פלוני", "origin": "index:עורך"}
    commons = inv.commons_creator_mentions(FILE_WIKITEXT)
    assert {"role": "author", "commons_creator": "Samson Raphael Hirsch", "origin": "commons:author"} in commons
    assert {"role": "translator", "wikidata": "Q33127885", "origin": "commons:translator"} in commons
    # The {{Label|Q..}} display text and the lifespan are not a second, unevidenced translator.
    assert not [m for m in commons if m["role"] == "translator" and "name" in m]
    assert inv.licence_templates(FILE_WIKITEXT) == ["PD-scan|PD-old-auto-1923|deathyear=1908"]
    assert inv.commons_creator_mentions("{{Book\n| Author = {{unknown|author}}\n}}")[0]["anonymous"] is True


def test_death_year_upper_bounds_never_guess() -> None:
    assert inv.death_year_upper_bound("+1888-12-31T00:00:00Z", 11) == 1888
    assert inv.death_year_upper_bound("+1880-00-00T00:00:00Z", 8) == 1889
    assert inv.death_year_upper_bound("+1700-00-00T00:00:00Z", 7) == 1800
    assert inv.death_year_upper_bound("+1900-00-00T00:00:00Z", 5) is None
    assert inv.death_year_upper_bound("-0200-00-00T00:00:00Z", 9) is None
    entity = _entity("+1906-00-00T00:00:00Z", precision=9)
    entity["claims"]["P570"].append({"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": "+1908-00-00T00:00:00Z", "precision": 9}}}})
    entity["claims"]["P570"].append({"rank": "deprecated", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": "+1990-00-00T00:00:00Z", "precision": 9}}}})
    assert inv.wikidata_death(entity)["death_year"] == 1908
    assert inv.wikidata_death({"claims": {"P570": [{"rank": "normal", "mainsnak": {"snaktype": "somevalue"}}]}}) is None


def test_admitted_record_reuses_the_f8b_gate() -> None:
    record = _record(author_pages={
        'רש"ר הירש': {"title": 'מחבר:רש"ר הירש', "wikidata": "Q76985", "death_year": 1888, "permalink": "p", "display_name": "שמשון בן רפאל הירש"},
        "משה זלמן אהרנסון": {"title": "מחבר:משה זלמן אהרנסון", "wikidata": "Q33127885", "death_year": None, "permalink": None, "display_name": "משה זלמן אהרנסון"},
    }, index_wikitext=INDEX_WIKITEXT.replace("|עורך=יוסף פלוני", "|עורך="))
    creators = record["work"]["creators"]
    # The Index author link and the Commons Creator template are one creator (same Wikidata id).
    assert [(c["wikidata"], c["role"], c["death_year"]) for c in creators] == [("Q76985", "author", 1888), ("Q33127885", "author", 1906)]
    assert creators[0]["death_year_evidence_url"] in {"https://www.wikidata.org/wiki/Q76985", "p"}
    assert record["scan_rights"]["basis"] == "faithful_reproduction_of_pd_work"
    assert record["scan_rights"]["scan_source"]["name"] == "HebrewBooks"
    assert record["scan_rights"]["digitized_by_google"] is False
    assert record["work"]["published_year"] == 1893
    assert index_exclusion_reasons(record) == []


def test_missing_evidence_is_recorded_as_missing_so_the_gate_rejects() -> None:
    record = _record()  # the plain-text editor has no death-year evidence
    editor = next(c for c in record["work"]["creators"] if c["role"] == "editor")
    assert editor["death_year"] is None and editor["death_year_evidence_url"] is None
    assert index_exclusion_reasons(record) == ["creator_death_year_missing"]

    bare = _record(index_wikitext="{{:MediaWiki:Proofreadpage_index_template\n|מחבר=\n}}", file_wikitext=FILE_WIKITEXT.replace("{{Creator:Samson Raphael Hirsch}}", "").replace("{{Label|Q33127885|{{{1|{{int:lang}}}}}}} (1848-1906/8)", ""))
    assert bare["work"]["creators"] == []
    assert "creators_missing" in index_exclusion_reasons(bare)

    late = _record(entities={"Q76985": _entity("+1888-12-31T00:00:00Z"), "Q33127885": _entity("+1960-01-01T00:00:00Z")}, index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert index_exclusion_reasons(late) == ["creator_died_after_1955"]


def test_scan_source_licence_and_google_evidence() -> None:
    unsourced = _record(file_wikitext=FILE_WIKITEXT.replace("[http://www.hebrewbooks.org/41650 hebrewbooks.org (41650)]", "ספר חורב, וילנא").replace("[http://chabadlibrary.org/catalog Chabad-Lubavitch Library]", ""), index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert unsourced["scan_rights"]["scan_source"] is None
    assert "scan_provenance_unrecorded" in index_exclusion_reasons(unsourced)

    pd_us = _record(file_wikitext=FILE_WIKITEXT.replace("{{PD-scan|PD-old-auto-1923|deathyear=1908}}", "{{PD-US-not renewed}}"), index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert pd_us["scan_rights"]["basis"] is None
    assert index_exclusion_reasons(pd_us)[:2] == ["pd_us_only_licence", "scan_rights_basis_unsupported"]

    cc0 = _record(file_wikitext=FILE_WIKITEXT.replace("{{PD-scan|PD-old-auto-1923|deathyear=1908}}", "{{cc-zero}}"), index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert (cc0["scan_rights"]["basis"], cc0["scan_rights"]["licence"]) == ("explicit_open_licence", "CC0-1.0")

    google = _record(metadata=[{"name": "text", "value": [{"name": 0, "value": "Digitized by Google " * 40}]}], index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert google["scan_rights"]["digitized_by_google"] is True
    assert index_exclusion_reasons(google) == ["google_digitized_scan_pending"]

    no_layer = _record(metadata=[{"name": "Producer", "value": "ABBYY"}], index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    assert no_layer["scan_rights"]["digitized_by_google"] is None
    assert index_exclusion_reasons(no_layer) == ["google_digitization_unchecked"]


def test_anonymous_basis_only_from_explicit_markers() -> None:
    record = _record(index_wikitext="{{:MediaWiki:Proofreadpage_index_template\n|מחבר=לא ידוע\n}}", file_wikitext=FILE_WIKITEXT.replace("{{Creator:Samson Raphael Hirsch}}", "{{anonymous}}").replace("{{Label|Q33127885|{{{1|{{int:lang}}}}}}} (1848-1906/8)", ""))
    assert {c["role"] for c in record["work"]["creators"]} == {"anonymous"}
    assert record["work_rights"]["basis"] == "anonymous_published_by_1955"
    assert index_exclusion_reasons(record) == []


def test_free_text_roles_langswitch_and_wiki_links() -> None:
    notes = "{{:MediaWiki:Proofreadpage_index_template\n|מחבר=מאיר להמן\n|שפה=he\n|הערות=מתרגם: שמואל יוסף פין\n}}"
    mentions = inv.index_creator_mentions(notes)
    assert {"role": "translator", "name": "שמואל יוסף פין", "origin": "index:הערות", "from_free_text": True} in mentions
    assert inv.work_language("", notes) == "he"
    langswitch = "{{Book\n| Author = {{LangSwitch\n | en = Moshe Silberberg\n | he = משה זילברברג\n }}\n| Editor = [[w:Samuel David Luzzatto|Luzzatto]], edited by Jane Roe\n}}"
    assert inv.template_field(langswitch, "author") == "Moshe Silberberg"
    commons = inv.commons_creator_mentions(langswitch)
    assert {"role": "author", "name": "Moshe Silberberg", "origin": "commons:author"} in commons
    assert {"role": "editor", "wiki_title": "enwiki:Samuel David Luzzatto", "origin": "commons:editor"} in commons
    assert {"role": "editor", "name": "Jane Roe", "origin": "commons:editor"} in commons
    # A translator only named in prose is a creator; resolved through a matching Wikidata label it gets its evidence.
    record = _record(
        index_wikitext=notes,
        file_wikitext=FILE_WIKITEXT.replace("{{Creator:Samson Raphael Hirsch}}", "").replace("{{Label|Q33127885|{{{1|{{int:lang}}}}}}} (1848-1906/8)", ""),
        author_pages={},
        entities={},
    )
    assert index_exclusion_reasons(record) == ["creator_death_year_missing"]


def test_packaged_render_check_is_reused_but_never_overrides_google_evidence() -> None:
    checks = inv.packaged_render_checks()
    assert checks and all(check["digitized_by_google"] is False for check in checks.values())
    packaged = next(iter(checks.values()))
    assert inv.with_render_check(None, "unchecked", packaged)[0] is False
    assert inv.with_render_check(True, "text layer names Google", packaged) == (True, "text layer names Google")
    assert inv.with_render_check(None, "unchecked", None) == (None, "unchecked")
    mentions = inv.packaged_creator_mentions()
    assert all(mention["origin"] == "f8b_snapshot" and mention["wikidata"].startswith("Q") for values in mentions.values() for mention in values)


def _inventory_with(records: list[dict], pages: list[dict]) -> dict:
    for record in records:
        record["pages"] = {"in_index": 3, "quality_counts": {"3": 2, "4": 1}}
        record["gate"] = {"reasons": index_exclusion_reasons(record)}
        record["gate"]["admitted"] = not record["gate"]["reasons"]
    return {"schema_version": inv.INVENTORY_SCHEMA_VERSION, "checked_at": "2026-11-06", "site": inv.WS_SITE, "indexes": records, "pages": pages}


def test_compact_inventory_and_summary_are_deterministic_and_text_free() -> None:
    admitted = _record(index_wikitext=INDEX_WIKITEXT.replace("יוסף פלוני", ""))
    rejected = _record()
    rejected["index_title"] = "מפתח:Other.pdf"
    rejected["index_key"] = "ws_index_2"
    pages = [
        {"index_key": admitted["index_key"], "quality": 4, "reasons": ["transcription_coverage_unrecorded"], "adjudication_eligible": True},
        {"index_key": admitted["index_key"], "quality": 3, "reasons": ["transcription_coverage_unrecorded"], "adjudication_eligible": False},
        {"index_key": admitted["index_key"], "quality": 3, "reasons": ["quality_editor_not_named_human", "transcription_coverage_unrecorded"], "adjudication_eligible": False},
    ]
    compact = inv.compact_inventory(_inventory_with([admitted, rejected], pages))
    gate = compact["indexes"][0]["page_gate"]
    assert gate == {"checked": 3, "pending_coverage_only": {"3": 1, "4": 1}, "reference_eligible_q4": 1, "rejected_by_first_reason": {"quality_editor_not_named_human": 1}, "unsupported_markup": {}}
    assert compact["indexes"][1]["page_gate"] is None
    summary = inv.render_summary(compact)
    assert summary == inv.render_summary(json.loads(json.dumps(compact)))
    assert "| Indexes admitted by the Index gate | 1 |" in summary
    assert "| `creator_death_year_missing` | 1 | 3 | 1 | 3 |" in summary
    assert "death year for יוסף פלוני" in summary


def test_committed_inventory_replays_through_the_unchanged_gate() -> None:
    compact = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    assert compact["schema_version"] == "wikisource_index_inventory_summary.v1"
    assert len(compact["indexes"]) >= 100
    for record in compact["indexes"]:
        assert index_exclusion_reasons(record) == record["gate"]["reasons"], record["index_title"]
        assert record["gate"]["admitted"] == (not record["gate"]["reasons"])
        for creator in record["work"]["creators"]:
            # A death year is never recorded without its evidence URL.
            assert (creator["death_year"] is None) == (creator["death_year_evidence_url"] is None)
    text = SUMMARY_JSON.read_text(encoding="utf-8")
    for forbidden in ("/Users/", "/home/", "wikitext_path", "text_path", "\"text\":"):
        assert forbidden not in text
    assert SUMMARY_MD.read_text(encoding="utf-8") == inv.render_summary(compact)
