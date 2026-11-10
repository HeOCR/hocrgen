# Consultation prompt behind the 2026-11-10 legal strategy

The HeOCR team lead drafted this prompt on 2026-11-10. The maintainer then sent it to several models for consultation. The answer he adopted is in `docs/legal/2026-11-10_legal_strategy.md`.

```text
I need a careful legal-risk analysis (not formal legal advice) for an open-source project. Please reason step by step, separate jurisdictions, cite cases/statutes/policies where you can, and clearly flag where you are uncertain or where the law is unsettled. If you don't know something, say so rather than guessing.

## Context

HeOCR is an open-source Hebrew OCR project, run by an individual maintainer in Israel. Everything it produces is meant to be released openly:
- Trained model weights are released under Apache-2.0.
- Datasets go out under open licences (CC0, CC BY or CC BY-SA), on Hugging Face and Zenodo.
- The maintainer's rule is that no input may enter the training pipeline if its terms would later cast doubt on releasing the derived data or models openly, including for commercial use by third parties. Attribution and share-alike obligations are acceptable. Non-commercial or no-derivatives restrictions are not.

The project uses scanned pages of old printed Hebrew books whose texts are in the public domain: mostly authors who died over 70 years ago, and books printed before 1929. We pair each scan with a public-domain digital transcription of the same edition (from Project Ben-Yehuda). From those pairs we:
1. crop individual text lines from the page images and pair each crop with its transcription, to make training and evaluation examples;
2. crop individual letter glyphs into a "glyph bank", which is used to compose new synthetic training pages;
3. train OCR models on these crops (fine-tuning Google's Apache-2.0 Tesseract `tessdata_best` model, and training kraken models);
4. publish the line-crop datasets, the glyph banks and the trained weights openly;
5. possibly publish page images in an evaluation benchmark.

## The question

Many scans of such public-domain books were made by Google, in the Google Books library partnership program. We meet them through three routes:

A. **National Library of Israel (NLI).** NLI hosts Google-digitized copies of its public-domain books. NLI labels them with a rights status of "public domain, non-commercial use". NLI's own (non-Google) scans of other public-domain books are labelled "public domain, free use". Our downloads come from NLI's IIIF API, which needs an API key, under NLI's terms of use.

B. **Internet Archive.** Some items are Google Books scans that were re-uploaded to IA. Their identifiers start with `bub_gb_` or end in `goog`, and their metadata shows them as digitized by Google. Some carry a Public Domain Mark. We got them from IA, not from Google.

C. **Wikimedia Commons.** Some files are Google Books scans (PDF/DjVu) that were uploaded to Commons and tagged public domain (PD-old or similar). Hebrew Wikisource uses them as the page images behind its proofread transcriptions. We got them from Commons and Wikisource, not from Google.

Google Books PDFs of public-domain books typically open with a front page of "usage guidelines". These ask readers to make non-commercial use of the files, to refrain from automated querying, to keep Google's watermark/attribution, and to keep the use legal. Google describes them as requests and as part of its stewardship of the material.

Please analyse:

1. **Copyright in the scans themselves.** Does a faithful photographic scan of a public-domain printed book attract any copyright or related right?
   - Under US law, consider Bridgeman v. Corel and later cases.
   - Under Israeli law, consider the Copyright Act 2007: its originality requirement, its treatment of photographs, and any relevant Israeli case law.
   - Under EU law, consider Article 14 of the 2019 DSM Directive and national neighbouring rights for simple photographs, for example Germany's §72 UrhG and Italy's rules, since users and mirrors may be in the EU.

2. **Contract or terms-of-use restrictions.** Can Google's usage guidelines, or NLI's "non-commercial" label and terms of use, bind:
   (a) us, who in routes B and C never received the files from Google and never agreed to Google's terms;
   (b) us in route A, where we accepted NLI's API terms;
   (c) downstream users of our released datasets and models?
   Discuss privity, browse-wrap/click-wrap enforceability, and whether a non-commercial condition on public-domain material is enforceable at all, in the US and in Israel.

3. **Derived artefacts.**
   - Line crops and glyph crops are small excerpts of the scans.
   - The model weights are statistical parameters learned from many crops.
   - Does any restriction that applies to the scans carry over to the crops, or to the weights?
   - Is training a model on these images, then releasing its weights for commercial use, a breach of a "non-commercial use" request?

4. **Practical risk.** For each route (A, B, C) and each artefact (internal training only; published line or glyph crops; published weights; published full page images in a benchmark), rate the risk as low, medium or high. Explain the realistic exposure: who could object, what they could plausibly claim, and how likely that is. Include reputational risk, for example Google, NLI or the Wikimedia community objecting.

5. **What comparable projects do.** How do comparable open projects and institutions treat Google-digitized public-domain scans? Examples: HathiTrust, Internet Archive, Wikimedia Commons policy on Google Books scans, Europeana, large open training corpora built from public-domain books, and OCR or HTR projects such as Transkribus models or kraken/eScriptorium datasets. Note any published guidance or precedent.

6. **Recommendation.** Should a project with the rule above:
   (i) exclude every Google-digitized scan regardless of route;
   (ii) exclude only route A, where an explicit non-commercial label from the host applies;
   (iii) accept routes B and C with attribution;
   (iv) do something else, such as keeping them for internal evaluation only?
   Explain the trade-offs, and give the minimum steps that would make each acceptable option defensible: attribution wording, NOTICE files, keeping per-item provenance so items can be removed later, and a takedown process.

Please structure the answer with one heading per question. Finish with a one-paragraph bottom line and a list of the points where a qualified Israeli or US copyright lawyer should be consulted.
```
