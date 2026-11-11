"""Network-free tests for the hocrgen#171 review rules, applied in the Index gate and the Route C justification:
commentaries printed on the page, possible later reprints, and a cited floruit as an author's basis."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from hocrgen.fetchers import wikisource_justification as wj
from hocrgen.fetchers.wikisource import index_exclusion_reasons
from hocrgen.tools import wikisource_inventory as inv

ROOT = Path(__file__).resolve().parents[1]
AS_OF = dt.date(2026, 11, 11)


def _index(**work) -> dict:
    index = {
        "index_key": "ws_index_9",
        "index_title": "מפתח:Book.pdf",
        "commons_file": {"title": "File:Book.pdf", "repository": "commons", "file_page_revision_id": 7, "sha1": "a" * 40,
                         "page_count": 10, "source_field": "http://hebrewbooks.org/1", "institution_field": None,
                         "provenance_text": None, "licence_templates": ["PD-old"], "categories": []},
        "work": {"title": "ספר", "published_year": 1900, "published_year_evidence": "Commons date field: 1900", "language": "he",
                 "creators": [{"name": "Author", "role": "author", "wikidata": "Q1", "death_year": 1204,
                               "death_year_evidence_url": "https://www.wikidata.org/wiki/Q1"}]},
        "work_rights": {"basis": "author_died_by_1955", "evidence": "x"},
        "scan_rights": {"basis": "faithful_reproduction_of_pd_work", "licence": None, "scan_source": None, "evidence": "x",
                        "digitized_by_google": False, "digitization_check": "x"},
    }
    index["work"].update(work)
    return index


def _commentaries(*detected, attributed=(), complete=None) -> dict:
    return {"detected": list(detected), "attributed": list(attributed), **({"complete": complete} if complete else {})}


UNNAMED = {"kind": "unnamed", "title": None, "source": "commons_author", "snippet": "multiple authors of classic commentaries"}
KESEF = {"kind": "named", "title": "כסף משנה", "source": "page_heading", "snippet": "כסף משנה", "pages": 5}


# --- rule 1: commentaries printed on the page ---------------------------------------------------------------


def test_an_unnamed_printed_commentary_fails_the_edition() -> None:
    assert "printed_commentary_unnamed" in index_exclusion_reasons(_index(printed_commentaries=_commentaries(UNNAMED)))
    # A recorded complete list of the printing's commentaries resolves the unnamed signal.
    assert index_exclusion_reasons(_index(printed_commentaries=_commentaries(UNNAMED, complete="recorded list"))) == []


def test_a_named_commentary_needs_its_author_with_a_cited_death_year() -> None:
    assert index_exclusion_reasons(_index(printed_commentaries=_commentaries(KESEF))) == ["printed_commentary_unattributed"]
    karo = {"name": "Joseph Karo", "role": "annotator", "wikidata": "Q467148", "death_year": 1575,
            "death_year_evidence_url": "https://www.wikidata.org/wiki/Q467148"}
    work = _index()["work"]
    attributed = [{"titles": ["כסף משנה"], "creators": ["Joseph Karo"], "evidence": "x"}]
    assert index_exclusion_reasons(_index(creators=[*work["creators"], karo],
                                          printed_commentaries=_commentaries(KESEF, attributed=attributed))) == []
    unknown = {**karo, "death_year": None, "death_year_evidence_url": None}
    reasons = index_exclusion_reasons(_index(creators=[*work["creators"], unknown], published_year=1900,
                                             printed_commentaries=_commentaries(KESEF, attributed=attributed)))
    assert "printed_commentary_death_year_missing" in reasons
    # On or before 1855 the name is enough (decision 10's presumption covers the death year).
    early = _index(creators=[*work["creators"], unknown], published_year=1850,
                   printed_commentaries=_commentaries(KESEF, attributed=attributed),
                   published_year_evidence="Commons date field: 1850")
    early["work_rights"] = {"basis": "presumed_pd_by_publication_age", "evidence": "x"}
    assert index_exclusion_reasons(early) == []


def test_commentary_signals_from_the_commons_and_index_records() -> None:
    file_wikitext = ("{{Information\n|description={{en|1=Mishneh Torah by Maimonides}}\n"
                     "|author=Maimonides (accompanied by multiple authors of classic commentaries on his work).\n}}")
    assert [s["kind"] for s in inv.commentary_signals_from_records(file_wikitext, "")] == ["unnamed"]
    named = "{{Information\n|description={{en|1=Proverbs with the commentary ''Qav ve-Naqi'', by David}}\n}}"
    assert [(s["kind"], s["title"]) for s in inv.commentary_signals_from_records(named, "")] == [("named", "Qav ve-Naqi")]
    # The work itself being a commentary is no signal; nor is a cross-reference to another Index.
    itself = "{{Information\n|description={{en|1=The commentary ''Ma'yan Ganim'' on Job}}\n}}"
    assert inv.commentary_signals_from_records(itself, "") == []
    index = "{{:MediaWiki:Proofreadpage_index_template\n|כותרת=משלי עם פירוש קב ונקי\n|הערות=ראו [[מפתח:משלי עם פירוש אחר.pdf|כאן]]\n}}"
    assert [(s["kind"], s["title"]) for s in inv.commentary_signals_from_records("", index)] == [("named", "קב ונקי")]


def test_commentary_headings_on_the_pinned_pages() -> None:
    pages = [
        ("עמוד:X/1", "{{מרכז|{{גדול|'''כסף משנה'''}}}}\ntext\n{{מרכז|{{גדול|'''פירוש'''}}}}\nmore"),
        ("עמוד:X/2", "'''השגת הראב\"ד.''' א\"א ...\n{{מרכז|'''כסף משנה'''}}\n(עיין בכסף משנה)"),
    ]
    signals = {(s["kind"], s["title"]): s for s in inv.commentary_signals_from_pages(pages)}
    assert signals[("named", "כסף משנה")]["pages"] == 2
    assert ("named", 'השגות הראב"ד') in signals  # an inline gloss marker
    assert ("unnamed", None) in signals  # the generic heading "פירוש"
    assert inv.commentary_signals_from_pages([("עמוד:Y/1", "plain text mentioning כסף משנה in a sentence")]) == []


# --- rule 2: possible later reprints -------------------------------------------------------------------------


def test_a_possible_later_reprint_stays_rejected_until_cleared() -> None:
    signals = inv.reprint_signals("{{Information\n|source=based on scans of a later mechanical reprint\n}}", "")
    assert [s["source"] for s in signals] == ["commons_source"]
    record = {"work": {}}
    inv.apply_rights_rules(record, commentary_signals=[], reprint=signals, evidence=None)
    assert index_exclusion_reasons(_index(**record["work"])) == ["possible_later_reprint"]
    recorded = {"recorded_by": "agent", "checked_at": "2026-11-11"}
    inv.apply_rights_rules(record, commentary_signals=[], reprint=[], evidence={"reprint": {"status": "suspected", "evidence": "review", **recorded}})
    assert record["work"]["reprint_check"]["signals"][0]["source"] == "recorded"
    inv.apply_rights_rules(record, commentary_signals=[], reprint=signals, evidence={"reprint": {"status": "cleared", "evidence": "colophon", **recorded}})
    assert index_exclusion_reasons(_index(**record["work"])) == []


# --- rule 3: a cited floruit as the author's basis ----------------------------------------------------------


FLORUIT = {"kind": "floruit", "source": "wikidata_P1317", "value": "+1300-00-00T00:00:00Z", "label": "13th century",
           "precision": 7, "latest_year": 1400, "evidence_url": "https://www.wikidata.org/wiki/Q94949710"}


def test_a_cited_floruit_counts_for_the_author_only() -> None:
    author = {"name": "Masnuth", "role": "author", "wikidata": "Q94949710", "death_year": None, "death_year_evidence_url": None,
              "floruit": FLORUIT}
    buber = {"name": "Buber", "role": "editor", "wikidata": "Q982067", "death_year": 1906,
             "death_year_evidence_url": "https://www.wikidata.org/wiki/Q982067"}
    assert index_exclusion_reasons(_index(published_year=1899, creators=[author, buber])) == []
    # Every other contributor still needs a cited death year after 1855.
    editor = {**buber, "death_year": None, "death_year_evidence_url": None, "floruit": FLORUIT}
    assert index_exclusion_reasons(_index(published_year=1899, creators=[author, editor])) == ["creator_death_year_missing"]
    late = {**author, "floruit": {**FLORUIT, "latest_year": 1900}}
    assert index_exclusion_reasons(_index(published_year=1899, creators=[late, buber])) == ["creator_death_year_missing"]
    record = wj.build_wikisource_rights_justification(
        _index(published_year=1899, creators=[author, buber]),
        {"file": {"url": "https://upload.wikimedia.org/x.pdf", "sha1": "a" * 40, "mime": "application/pdf"}}, as_of=AS_OF,
    ).record
    source = record["work_public_domain"]["contributors"][0]["death_year_source"]
    assert source["kind"] == "floruit" and source["url"].endswith("Q94949710") and source["value"].startswith("+1300")
    assert record["work_public_domain"]["israel_status"]["floruit_for"] == ["Masnuth (floruit 13th century)"]
    assert "author fl. 13th century" in record["summary"]


def test_wikidata_floruit_and_duplicate_creators() -> None:
    entity = {"claims": {"P1317": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {
        "value": {"time": "+1300-00-00T00:00:00Z", "precision": 7}}}}]}}
    floruit = inv.wikidata_floruit(entity)
    assert floruit["label"] == "13th century" and floruit["latest_year"] == 1400 and floruit["kind"] == "floruit"
    creators = inv.resolve_creators(
        [{"role": "author", "name": "שמואל מסנות", "origin": "index:מחבר"},
         {"role": "author", "wikidata": "Q94949710", "origin": "commons:author"},
         {"role": "author", "name": "שמואל מסנות", "origin": "commons:author"}],
        author_pages={}, wiki_ids={}, commons_creators={},
        entities={"Q94949710": {"labels": {"he": {"value": "שמואל מסנות"}}, "claims": entity["claims"]}},
    )
    assert len(creators) == 1 and creators[0]["wikidata"] == "Q94949710" and creators[0]["floruit"]["latest_year"] == 1400


# --- the committed state -------------------------------------------------------------------------------------


def test_the_committed_inventory_and_justifications_apply_the_three_rules() -> None:
    inventory = {i["index_key"]: i for i in json.loads((ROOT / "docs" / "wikisource_index_inventory.json").read_text())["indexes"]}
    registry = {i["index_key"]: i for i in json.loads((ROOT / "docs" / "wikisource_rights_justifications.json").read_text())["items"]}
    for key in ("ws_index_1711486", "ws_index_1711487", "ws_index_1711490"):  # Mishneh Torah, Warsaw-Vilna 1900
        assert "printed_commentary_unnamed" in inventory[key]["gate"]["reasons"]
        assert not registry[key]["accepted"]
    assert "printed_commentary_unattributed" in inventory["ws_index_1711486"]["gate"]["reasons"]
    for key in ("ws_index_1711486", "ws_index_1711487", "ws_index_370788"):
        assert "possible_later_reprint" in inventory[key]["gate"]["reasons"]
    assert inventory["ws_index_368531"]["gate"]["reasons"][:1] == ["creator_death_year_missing"]
    assert "possible_later_reprint" in inventory["ws_index_368531"]["gate"]["reasons"]
    maayan = registry["ws_index_1735193"]
    assert maayan["accepted"] and len(inventory["ws_index_1735193"]["work"]["creators"]) == 2
    assert registry["ws_index_1720479"]["accepted"]  # Qav ve-Naqi is named and attributed


@pytest.mark.parametrize("key", ["printed_commentaries", "reprint"])
def test_the_evidence_file_validates_the_new_facts(key: str) -> None:
    record = {"index_title": "מפתח:X", "commons_file_sha1": "a" * 40}
    bad = copy.deepcopy(record)
    bad[key] = [{"titles": ["x"]}] if key == "printed_commentaries" else {"status": "maybe", "evidence": "x"}
    assert inv.index_evidence_problems(bad)
