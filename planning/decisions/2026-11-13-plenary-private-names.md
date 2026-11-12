# 2026-11-13: Knesset plenary record: drop lines that name private persons

- **Status:** accepted
- **Decided by:** the maintainer (Shay Palachy Affek), 2026-11-13, relayed by heocr-lead. Asked "Should private people's names be filtered from the plenary-record lines?", he answered: "Yes, filter them".
- **Written by:** `data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource`
- **Builds on:**
  - `2026-11-11-knesset-protocols-training-vs-release.md`, item 8: the plenary record (Divrei ha-Knesset) is section 6 material, open for both training and publication.
  - The scout report's privacy notes (`tasks/modern-s6-scout/knesset/report.md` §4, in the HeOCR agents workspace). Speakers are MKs, ministers and the chair, but the content can name private persons: a letter read aloud, a radio caller's complaint, or a citizen's case in a parliamentary question.
- **Does not change:**
  - Knesset committee protocols. These stay train-only from 1976 on, with their own per-page privacy screen.
  - Court rulings. These stay out.

## Decision

1. **What is dropped.** Any plenary line that names a private person. A private person is anyone who is not:
   - an MK;
   - a minister or deputy minister;
   - an official; or
   - another public figure acting in their role.

   Example: a citizen named in a letter that an MK reads aloud.
2. **Drop, don't mask.** The whole line goes. Names are never blanked or replaced inside a kept line.
3. **Scope.** All Knesset periods, both activities (training and published datasets), and every line set built from the plenary record. That includes rendered K13+ sittings and any future K1–12 scan lines.
4. **When in doubt, drop.** A line whose names could not be judged is dropped. A line that was never checked is refused at intake.

## How it is applied

The gate is `hocrgen.privacy.plenary_names`, gate id `plenary_private_names_v1`.

1. **Tagging.** Every paragraph is tagged for person names by `dicta-il/dictabert-ner`, a Hebrew NER model under CC BY 4.0. It is used as a filter only, never as a training input or a released artefact. A pure-Python fallback (`heuristic_person_spans`) adds names that follow a private-person cue such as "מר", "הגברת", "האזרח" or "התושבת".
2. **Normalising mentions.** Each tagged span is widened to whole words, because the tagger can cut a name mid-word: "נעמה לזי" for MK Naama Lazimi. Spans separated only by whitespace are merged into one mention. Judged apart, the given name and the surname of a private person can each match some MK. Together they name that private person.
3. **Public or private.** A mention is public only when one of these holds:
   - **It is in a proven speaker heading.** A heading-shaped line ("X (faction):", "title X:") proves nothing by its shape alone: "וכך כתבה לי <name>:" introduces a letter read aloud. A heading counts only when one of these proves it:
     - the source's own structure: the builder sets `is_speaker_heading: true` from the document's speaker style (in the pilot, the K24–25 `<< דובר >>`, `<< יור >>`, `<< קריאה >>` markers);
     - the whole name, after any title, is a roster full name or a contiguous part of one;
     - a title, then optional initials, then a surname of someone who held a position in that Knesset term ("ראש הממשלה ושר הביטחון י' רבין:");
     - the parentheses name a faction of that term (`KNS_PersonToPosition.FactionName`), and the name ends in a surname of someone in that term. This covers nicknames and spelling variants of MKs: "דני נווה (הליכוד):".
   - **A public title comes immediately before it.**
     - Titles are matched exactly, with no proclitic stripping, so "מראש", "בשר", "כשר" and "משרת" are not titles. The one exception is a leading "ו" on a title of four or more letters ("והשר").
     - Single words that are also ordinary words are never titles on their own: "ראש", "סגן", "חבר", "יושב", "מנהל", "מזכיר", and military ranks.
     - Multi-word titles are matched as whole phrases: "חבר הכנסת", "ראש הממשלה", "מבקר המדינה", "היועצת המשפטית לממשלה", "סגן השר", "מזכיר הכנסת", and so on.
     - Ministers' titles are a head ("שר", "השר", "סגן שר") followed only by ministry words ("שר האוצר", "השר לביטחון פנים").
     - Initials between a title and a name are skipped ("סגנית מזכיר הכנסת ש' כרם").
   - **It is on a curated public-figure allowlist.** The list starts empty and grows only through review.
   - **It matches the Knesset roster** in one of these ways:
     - by full name, or by a contiguous part of a full name ("גלית דיסטל"), against the whole roster;
     - by a bare surname ("בן צור"), or by one word of a multi-word surname ("אטבריאן"), but only against people who held a position in **that Knesset term**. When the term is unknown, no bare surname matches.

     The roster is the committed `hocrgen/data/knesset_plenary/public_roster_v1.json`: 1,211 `KNS_Person` rows with at least one `KNS_PersonToPosition` row (MKs, ministers, deputy ministers), with each person's terms and each term's faction names. Hyphenated names match with or without the hyphen. Doubled vav and yod are normalised ("נווה" = "נוה").

   Everything else is private, including:
   - **a lone given name.** Common given names collide with the names of speakers and MKs, so nothing can vouch for one. Example: a bereaved parent named by first name in a eulogy;
   - **a namesake:** a first name followed by an MK's surname, when that MK has a different first name.
4. **Intake guard.** `refuse_ungated_plenary_lines` refuses a plenary row unless the row or its metadata carries `privacy_gate == "plenary_private_names_v1"`. A row counts as plenary when:
   - its `source_id` starts with `knesset_plenary`;
   - an identifier places it in a plenary sitting (`plenary:K<k>_<s>`, the eval-reserved id patterns); or
   - its unit id starts with `plenary:`.

   Every plenary line builder must call the guard on its line rows before writing a manifest. The release export (`hocrgen.package.common.copy_export_assets`) also calls it on every item.
5. **Counting.** Each build writes the gate summary into its `summary.json`: lines in, kept, dropped, and dropped by reason.

## Pilot measurement (2026-11-13)

No plenary line set has been built yet. The K1–12 scans have no text, and the K13+ renders have not been made. So the gate was measured on the scout pilot's 10 born-digital sittings: 1993, 1996, 1999 and 2002 (DOCX) and 2005–2025 (DOC). Each was converted to text, and its paragraphs were wrapped at 90 characters as stand-in lines.

| | v1 (first PR revision) | **v1 after review (hocrgen#196)** |
|---|---|---|
| Lines in | 42,058 | 42,058 |
| Kept | 40,761 | 40,528 |
| **Dropped** | 1,297 (3.1%) | **1,530 (3.6%)** |

- **Drop reasons:** `not_public` on 1,321 lines and `surname_namesake` on 238. One line can carry both.
- **Per sitting:** between 1.8% and 6.8%.
- **The review's seven probe sentences** (invented private names after "מראש", "בשר", a distant "השר", "החבר שלי", "סגן", a "…כתבה לי X:" letter intro, and a given name from that intro) are all dropped, and each is a test.
- **Known private passages, all dropped:**
  - a radio caller named in a parliamentary question (K15, 2002);
  - a bereaved relative named in a eulogy (K25, 2025);
  - a mother and her children named in a letter read aloud (K25, 2025);
  - private persons named by first name only.

  This record names no private person. The pilot outputs that do name them stay in the agents workspace and are never committed.
- **Over-dropping, mostly public figures outside the roster:** foreign leaders ("אסד", "ערפאת", "קלינטון"), historical and biblical figures, IDF and security chiefs, MKs under nicknames outside proven headings, and the chair addressing MKs by first name. Allowlist candidates are listed in the pilot output.
- **Artifacts:** `tasks/modern-s6-scout/knesset/privacy/` in the agents workspace, containing `pilot_gate_summary.json`, `pilot_dropped.jsonl` and `pilot_private_mentions_top.json`.

## Known limits

- **Bare-surname leak, the largest remaining one.** A private person mentioned only by a surname (`כהן`, `לוי`, `פרץ`) that someone in that Knesset term shares is kept. A first name that is also such a surname leaks the same way; the pilot found one, a victim addressed by first name in a eulogy. Matching bare surnames per term, not against everyone since 1949, narrows this but does not close it. In the record, private persons are normally named in full, and the full-name check catches those.
- **Faction-proven headings.** A heading-shaped line with a real faction in parentheses and a surname of that term is trusted. Text that imitates exactly that shape would pass.
- **Full-name namesake leak.** A private person with exactly an MK's first name and surname is kept.
- **Over-dropping.** A public figure outside the roster who appears without a role word is dropped. Examples are foreign leaders and historical figures. The allowlist is the remedy.
- **NER recall.** The tagger can miss a name. The cue heuristic is a backstop, not a guarantee.
