# Follow-up legal-research prompt: Knesset bills (and open points on committee protocols)

Drafted by lead[claude/claude-code#shay-macbook-m4]@heocr/opensource at the maintainer's request (2026-11-11). It follows up the Gemini analysis archived as hocrgen `docs/legal/2026-11-11_knesset_protocols_analysis.md`, and is meant to be sent in the same Gemini conversation. The prompt follows.

---

Thank you, this was very useful. Based on your analysis we decided:
- to **train and release Apache-2.0 weights** on Knesset committee protocols from **all three periods**;
- to **publish line crops and transcriptions (CC0 / CC BY-SA) only for period 1** (created up to 31 December 1975, with the cutoff moving each 1 January);
- **not** to publish single-word or glyph crops from later protocols.

Your answer did not separately analyse **bills (הצעות חוק)**, which my prompt also asked about. Please answer the questions below to the same standard: primary sources, case names and numbers, established law kept apart from your inference, a confidence level per answer, and the Activity A / Activity B split.

## 1. Bills from 1976 onward

We have three kinds of bills in view:
- **(i) Government bills** (הצעות חוק הממשלה), published in Reshumot (the *Hatza'ot Hok* series), born-digital from about July 2005 and scanned before that.
- **(ii) Private members' bills** (הצעות חוק פרטיות) and **(iii) committee bills** (הצעות חוק של ועדה), published by the Knesset, mostly as PDFs on its website.

The questions:

1. **Section 6.** Are bills "חוקים" or "דברי הכנסת" for section 6? Or are they State works under section 36, with 50 years from creation? Does the answer differ for:
   - (i) government bills drafted by ministries, whose explanatory notes (דברי הסבר) are written by civil servants;
   - (ii) private members' bills, drafted by MKs or their staff, sometimes with outside help;
   - (iii) committee bills?
2. **The dropped clause.** We believe the 2005 Government Bill or the 2003 memorandum had a broader exemption that also covered "similar official documents", and that it was dropped from the enacted text. Please verify this from the bill and memorandum texts and the Economics Committee's discussion. Did the drafters say anything about bills, explanatory notes or committee protocols? What does the drop imply under Israeli rules of interpretation (e.g. reading deleted text as a deliberate exclusion)?
3. **Bills that became law.** The enacted law is covered by section 6. Does the bill text published in Reshumot before enactment share that status? Is a bill's explanatory note a separate work?
4. **Bills read in the plenary.** When a bill is tabled, read or debated in a plenary sitting and appears in the plenary record (Divrei ha-Knesset), is that copy covered by section 6 even if the standalone bill booklet is not?
5. **Publication by law.** Bills are published in Reshumot under a legal duty. Does publication in the official gazette matter under section 6 or section 21 (works deposited for public inspection)?
6. **Terms.**
   - Do the Reshumot site's terms of use (gov.il, Ministry of Justice) or the Knesset site's terms add any contractual limit beyond copyright, for training (Activity A) or for publication (Activity B)?
   - Does the Government's open-data policy (Resolution 1933, data.gov.il) cover Reshumot bills, as a government publication, even though it does not bind the Knesset?

## 2. Open points on committee protocols

7. **Evaluation use.** We plan to use committee protocol lines from 1976 onward as **evaluation references in an unpublished, access-restricted repository**: measuring our own models, never released. Is that within the same fair-use basis as training (Activity A)? Does anything change if summary scores computed on them are published?
8. **Weights that memorise.** OCR models can occasionally reproduce training text verbatim, for example through their language-model components. Does that affect the Activity A conclusion for periods 2 and 3, and is there a practical mitigation you'd recommend? For instance, we never ship a word list or dictionary built from post-1975 protocol text.
9. **Citations to verify.** Please confirm, with a link or a reference to the official publication:
   - the Ministry of Justice opinion on machine learning: its exact title, date and URL;
   - the current wording and date of the Knesset website terms of use (termsofuse.aspx), quoted;
   - section 78(a)–(j): confirm that no subsection keeps the 1911 Act's "from first publication" term for State works;
   - the Legal Adviser to the Knesset's official contact channel, from a Knesset page. We will not write to an address that isn't confirmed on an official page.

## Deliverables

- For each question: a short answer, a confidence level, and the reasoning with primary sources.
- For bills: a table like your first one, with bill type (i)/(ii)/(iii) × period × Activity A / Activity B.
- Anything in our decision above that you think is wrong or riskier than we assume.
