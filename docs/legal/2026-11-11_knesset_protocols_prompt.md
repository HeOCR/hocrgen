# Legal-research prompt: copyright in Knesset committee protocols (1976 onward)

Drafted by lead[claude/claude-code#shay-macbook-m4]@heocr/opensource at the maintainer's request (2026-11-11), for a Gemini Deep Research session. It concerns hocrgen decision 2026-11-06 item 5. The prompt follows.

---

I lead HeOCR, an open-source project that builds Hebrew OCR (text recognition) models. Every dataset we publish is CC0 or CC BY-SA, and every model is Apache-2.0. Both are released openly, including for commercial use. We need a careful legal analysis under **Israeli copyright law** of one question.

## The question

**May we copy, process, and publicly release protocols of Knesset *committee* meetings from 1976 onward?** We would use page images and their text to train OCR models, and publish line images with their transcriptions as an open dataset. The protocols here are typewritten or printed and are published on the Knesset website. If we may not, what is the narrowest path that would allow it?

**The same question for Knesset bills (הצעות חוק) from 1976 onward.** This covers government bills published in Reshumot (*Hatza'ot Hok*), and private members' and committee bills published by the Knesset. The Act does not define "דברי הכנסת". As far as we can tell, a broader wording covering "similar official documents" appeared in the bill but was dropped from the enacted text. Please verify that, and say what it implies for bills and for committee protocols.

One fact from our sample: 26 of 30 recent committee protocols name private persons, 7 of them in a personal capacity.

## What we believe so far (please test every point)

1. **Section 6 of the Copyright Act 2007 (חוק זכות יוצרים, התשס"ח-2007)** says there is no copyright in laws, regulations, "דברי הכנסת" and judicial decisions.
   - We read "דברי הכנסת" as at least the plenary record, which is published as the official series *Divrei ha-Knesset*.
   - Our working assumption is that committee protocols are **not** covered by "דברי הכנסת". Is that right?
2. **If section 6 does not apply**, committee protocols are works made by state employees in the course of their work. That makes them State copyright under section 36. Under section 42 that copyright lasts 50 years from creation, so protocols created by the end of 1975 are in the public domain today.
   - Is that the correct term rule, and is the year boundary right?
   - Does the transitional regime matter for works created under the 1911 Act / the 1924 Ordinance? See section 78 and the older Crown-copyright rules.
3. **Who is the author** of a protocol? Is it the stenographer or the transcription service? The Knesset? The speakers, whose speech may itself be a work? Does it matter that from some date the transcription was outsourced to private contractors?
4. **Third-party content.** Witnesses, experts and private persons speak in committees, and documents are sometimes quoted or attached. Do those contributors hold their own rights in their oral statements once they are written down?

## Please research

- **Statute:** the text of sections 6, 36, 42 and 78 of the Copyright Act 2007, and their legislative history. The explanatory notes to the bill (דברי הסבר להצעת החוק), and the committee discussion of the section 6 wording, especially any discussion of whether committee protocols are included.
- **The predecessor law:** how the 1911 Copyright Act as applied in Israel, and the 1924 Ordinance, treated parliamentary and government publications. How the transition affects pre-2008 works.
- **Case law:** Israeli rulings on section 6, on State copyright under section 36, on "דברי הכנסת", and on judicial decisions or other official documents as public domain. Also rulings on publishing parliamentary material.
- **The Knesset's own position:**
  - its website terms of use and any licence it states for protocols;
  - the Knesset Law (חוק הכנסת) and the Knesset Rules of Procedure (תקנון הכנסת) on publishing committee protocols;
  - whether protocols are published by law and whether that matters;
  - any Knesset legal adviser's opinion on reuse;
  - any open-data release of protocols (e.g. on data.gov.il or the Knesset's open-data/OData service) and its licence.
- **Government policy:** Israel's open-government-data policy, and government resolutions on releasing State works under open licences (e.g. CC BY). Does any of it cover Knesset protocols? The Knesset is not part of the government, so does that matter?
- **Comparative law, briefly:** how the UK (Parliamentary copyright, Open Parliament Licence) and the US (17 U.S.C. §105) treat committee transcripts. Only as context, or if Israeli courts have relied on it.
- **Other rules:** privacy, the Protection of Privacy Law, and any rules on the reuse of names of private persons who testified. We will screen protocols separately and exclude those with private persons, but flag anything that would change the copyright analysis.
- **Fair use (section 19):** does it help with training (as opposed to releasing the dataset)? Treat this separately. We need the dataset release itself to be lawful, not only the training.

## Deliverables

1. **A short answer.** Yes, no, or uncertain, for each of three periods: up to 1975, 1976 to about 2008, and after 2008. Give a confidence level for each.
2. **The reasoning**, section by section, with **citations to primary sources** (statute text, bill explanatory notes, case names and numbers, Knesset documents with URLs). Keep established law apart from your own inference. Say where sources disagree.
3. **The risk picture:** who could object (the State, the Knesset, a transcription contractor, a speaker), how likely that is, and what the realistic consequence is for a non-commercial open-source project that releases under open licences.
4. **Paths to permission**, if the answer is not a clear yes: whom to ask (e.g. the Knesset legal adviser, the Knesset spokesperson, the Knesset's open-data team), what to ask for (e.g. a licence or a statement that section 6 covers committee protocols), and a short draft of the request in Hebrew.
5. **Any part of our assumptions above that is wrong.**

Be concrete. We will act on this analysis, so an unsupported "probably" is costly. Say clearly what still needs a licensed Israeli lawyer's sign-off.
