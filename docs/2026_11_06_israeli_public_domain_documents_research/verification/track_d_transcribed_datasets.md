# Track D: existing transcribed Hebrew page datasets (images + human transcriptions)

Research date: 2026-11-06. Read-only checks only: public pages, Zenodo / Hugging Face / GitHub / figshare APIs, and `gh`. No sign-ins and no bulk downloads. The only file downloaded whole was one 1.2 MB Sofer Mahir ALTO zip. For three large zips (BiblIA, Pinkas, MiDRASH), only the zip central directory was read, using HTTP range requests.

Tags: *(verified 2026-11-06)* means I loaded the primary page or API record myself. *(inferred)* is my reading of the evidence. `Needs verification` means I could not confirm it.

## 0. Key cross-cutting findings

1. **hocrgen's `biblia_open` and `pinkas_open` have nothing to do with the BiblIA and Pinkas GT datasets except their names.** *(verified 2026-11-06, `src/hocrgen/data/{biblia,pinkas}/records.json`)*
   - `biblia_open` contains 26 Wikimedia Commons images of "Hebrew Bible from 1300" (NLI/Ktiv).
   - `pinkas_open` contains 27 Commons/WDL scans of community pinkasim.
   - Neither has any transcription field. Neither comes from Zenodo 5167263 (BiblIA) or Zenodo 3569694 (Pinkas Dataset).
   - So there is **no image overlap**, and HeOCR currently holds **zero** human-GT pages from these datasets.
   - The shared names are a naming-collision risk for future adapters.
2. **Open, commercial-use-OK, human-GT Hebrew page datasets are rare.** Most of the high-quality medieval GT is non-commercial:
   - BiblIA: CC-BY-NC-SA-4.0.
   - Sofer Mahir: CC BY-NC-SA.
   - Princeton Geniza Project: CC-BY-NC-4.0.
3. The clean candidates are:
   - the **Pinkas Dataset** (CC-BY-4.0, images plus PAGE GT);
   - the **YidTakNL / Vaybertaytsh GT** (CC-BY-4.0, printed Yiddish).
4. `CC-BY-NC-SA-4.0` / `CC-BY-NC-4.0` and `CC-BY-3.0` have no hocrgen licence value. Either add `CC-BY-NC-SA-4.0` and `CC-BY-NC-4.0` (always mapped to `restricted_review_only`), or collapse them into `RESTRICTED-NONOPEN`.

---

## 1. BiblIA open annotated dataset (EPHE-PSL / Scripta-PSL)

- **Identity:** "BiblIA - an Open Annotated Dataset", by Stökl Ben Ezra, Brown-DeVost, Jablonski, Kiessling, Lolli and Lapin.
  - Record: https://zenodo.org/records/5167263, DOI 10.5281/zenodo.5167263, v1.0, 2021-08-06.
  - Paper: HIP@ICDAR 2021, doi:10.1145/3476887.3476896. The ACM page returned 403, so I could not read it.
- **Gemini claim check:** "EPHE … PAGE/ALTO corpora of fully transcribed Hebrew manuscripts" holds for EPHE, but it is one 202-page dataset, not a large corpus, and its licence is NC.
  - **The HTR-United catalogue lists the licence as "CC-BY-SA 4.0", which is wrong.** The Zenodo record and the description both say CC-BY-NC-SA 4.0 *(verified 2026-11-06)*.
  - The SA-only licence belongs to the BiblIA *models* (Zenodo 5468286, 5468478, 5468573, 5468665, all cc-by-sa-4.0).
- **Content:**
  - 202 page images of medieval Hebrew manuscripts, square/semi-cursive bookhands: Ashkenazi, Italian and Sephardi.
  - Biblical and Rabbinic genres. HTR-United gives dates 1000–1499.
  - 12,461 lines, 509 regions, about 278.6k characters. 100% Hebrew script.
  - Period: **pre-18th century, so outside HASH scope.** This is a separate "medieval scribal hand" slice for HeOCR. *(verified 2026-11-06: Zenodo API, HTR-United YAML)*
- **Text availability:** ALTO 4.2 XML with regions, toplines, line polygons and Unicode transcriptions, one XML per page.
  - The zip directory shows 202 XML files and 132 JPG files, in folders such as `BiblIA_dataset/Ashkenazy/btv1b10539358v.{jpg,xml}` *(verified 2026-11-06, range read of the central directory)*.
  - It was produced in eScriptorium with Kraken. Per the paper/record this is GT annotated by the project, i.e. HTR output corrected by humans *(inferred; paper not loaded: `Needs verification`)*.
- **Access:**
  - One 546 MB zip on Zenodo. Zenodo serves HTTP range requests, so a fixture can pick single members without a bulk download.
  - The BnF images are included (Gallica ark IDs, `btv1b…`).
  - The 70 Vatican (BAV) images are **not** included. `catalogue.txt` gives their IIIF links.
- **Rights:**
  - Transcriptions and dataset: Zenodo states "Licence CC-BY-NC-SA 4.0" *(verified 2026-11-06)*.
  - The record says BAV images were left out "for copyright issues". BnF/Gallica reuse terms have long been "réutilisation non commerciale … libre et gratuite" (commercial reuse is paid). I could not load the Gallica terms page (403), so that wording comes only from old notices (`Needs verification` for current terms).
  - Proposed: `normalized_license` = new value `CC-BY-NC-SA-4.0` (else `RESTRICTED-NONOPEN`); `rights_classification` = `restricted_review_only`; status `review_only`. NC and SA are incompatible with an open default release.
- **Fixture feasibility:** Technically easy (one page = one JPG plus one ALTO, selectable by range read). Rights block a public fixture. A private, review-only fixture is fine.
  - Sample checked: `BiblIA_dataset/Ashkenazy/btv1b10539358v.xml` (56 KB) and its JPG (1.9 MB), in the zip at https://zenodo.org/records/5167263.
  - The Gallica page for that ID is https://gallica.bnf.fr/ark:/12148/btv1b10539358v (not loaded).
- **HeOCR value:** **High for a medieval-manuscript slice and for evaluation.** It is the best line-level Hebrew HTR GT with geometry, but NC-SA blocks public training releases.
- **Open questions:**
  - Should HeOCR accept NC-SA material in internal or eval-only splits?
  - Should we ask EPHE (Stökl Ben Ezra) for a CC-BY relicence of the BnF subset? BnF images of PD manuscripts may be negotiable.

## 2. Sofer Mahir ALTO transcriptions (EPHE-PSL and U. Maryland)

- **Identity:** https://github.com/dstoekl/sofer_mahir, "(c) 2021 Daniel Stökl Ben Ezra (EPHE, PSL) and Hayim Lapin". The data README is v0.9 (2022).
- **Gemini claim check:** Not named by Gemini. It fits the "EPHE eScriptorium corpora" lead.
  - A HASH note claims there is a `github.com/MiDRASH-Project` org with model releases. **That GitHub org does not exist** (`gh` reports an unknown owner, 2026-11-06). The MiDRASH models are on Zenodo (section 5).
- **Content:**
  - Line-level GT for 16 large medieval codices of Tannaitic works (Mishnah, Tosefta, Sifra, Sifre, Mekhilta). Examples: Oxford Marshall Or. 24, BL Add. 16406, Vat. ebr. 299/31/32/66, Parma 3173/3259, Vienna Heb. 20, Kaufmann A50, Cambridge Add. 470.1, Erfurt, Munich 117, Berlin Or. Qu. 1594, JTS 2392.
  - The repo holds 15 ALTO zips (the Vat. 66 zip was deleted in 2022).
  - Medieval, so **pre-18th century and outside HASH scope.**
  - The CHARTES/PSL page says the project "produces manually corrected transcriptions of 16 large medieval Hebrew codexes", i.e. **HTR output that humans corrected** *(verified 2026-11-06, chartes.psl.eu video page)*.
- **Text availability:**
  - ALTO 4.2 with baselines, polygons, region tags (Main / Margin / Paratext / Correction) and diplomatic transcription, including abbreviation marks.
  - The JTS 2392 zip (1.17 MB, 28 ALTO pages) was checked. `Fol__001r.xml` has 26 `TextLine`s and a 5025×6668 page *(verified 2026-11-06)*.
  - **No images are included.** The ALTO points to `Fol__001r.jpg`. Images must come from each holding library (IIIF where available), and filenames have to be mapped to canvases.
  - There are also TEI files (`data/TEI/Mekhilta…/LEAF_transcription_MekhY_Vat299.xml`).
- **Access:** Public GitHub repo with ALTO zips of 1–24 MB each. Stable, but it is a personal repo with no tagged release.
- **Rights:**
  - The root README links to "https://creativecommons.org/licenses/by-nc-sa/4.0/". `data/README.md` says "CC-BY-SA-NC Licence 2022". There is no LICENSE file, and the GitHub licence field is empty *(verified 2026-11-06)*.
  - Image rights depend on each library (BL, BAV, Parma, Bodleian, CUL, JTS, SBB, BSB, ÖNB and others), so they are **per item and mostly restrictive.**
  - Proposed: `CC-BY-NC-SA-4.0` (new value) / `RESTRICTED-NONOPEN`; `restricted_review_only`; status `review_only`.
- **Fixture feasibility:** The text side is easy (a single ALTO zip). An image pairing needs per-library IIIF lookup. A public fixture is not rights-clean.
  - Samples: `data/alto/export_doc1516_jts2392_alto_202209050838.zip` → `Fol__001r.xml`, and `export_doc767_v299_mekh_alto_202209050831.zip` (listed, not opened).
- **HeOCR value:** **Medium-high.** It is large (16 codices, thousands of pages *(inferred)*) and has line geometry. But it has no images, is NC, and is medieval.
- **Open questions:**
  - Is a license-compatible image source available for the JTS and Cambridge codices?
  - Is an alignment-only adapter (ALTO plus a fetch-on-demand IIIF image) acceptable for internal eval?

## 3. The Pinkas Dataset (Ben-Gurion University)

- **Identity:** Rabaev, Kurar Barakat and El-Sana, ICDAR 2019. https://zenodo.org/records/3569694 (v1, 2019-12-10).
- **Gemini claim check:** Gemini's "BGU" lead holds for this dataset (BGU's other set, HHD, is in section 9).
- **Content:**
  - 30 pages from "a historical Hebrew manuscript that contains records of Jewish communities in Europe in the early modern period (c. 1500–1800)".
  - Several non-professional writers, cursive Ashkenazi hands, degraded pages.
  - The `cyttic/pinkas-hebrew-lines` derivative card says "Hebrew and Yiddish".
  - Period: **early modern, partly overlapping HASH's 18th-century+ scope.**
  - The exact manuscript, holding library and date are `Needs verification`. The txt files inside the zip were not read.
- **Text availability:** PAGE XML, "labeled at word, line and page levels". It is human GT built for word spotting.
  - The zip has 30 JPG and 30 XML files, plus 2 txt files, e.g. `Page 105_1.{jpg,xml}` *(verified 2026-11-06, range read)*.
  - Some XML files are tiny (647 B, 3.5 KB), so some pages may carry little or no text. `Needs verification`.
- **Access:** One 47.7 MB zip on Zenodo (range reads work).
- **Rights:**
  - Zenodo licence field: `cc-by-4.0` *(verified 2026-11-06)*. It covers the dataset, images included.
  - The images are reproductions of an early-modern manuscript, so the underlying work is PD. Who made the scans, and whether the holding library adds terms, is `Needs verification`.
  - Proposed: `CC-BY-4.0`; `open_with_attribution`; status `allowed`, provisionally, pending the image-provenance check.
- **Fixture feasibility:** **Yes.** One page with its PAGE XML is about 2 MB. Samples: `pinkas_dataset/pinkas_dataset_images_and_xmls/Page 105_1.jpg` + `.xml`, and `Page 112_1.jpg` + `.xml`.
  - Derivative: https://huggingface.co/datasets/cyttic/pinkas-hebrew-lines (CC-BY-4.0). It has polygon line crops, normalized text and horizontal stretching. **Use the original, not this derivative.** The derivative alters the geometry and the text.
- **HeOCR value:** **High.** It is the only CC-BY Hebrew handwritten page GT with images and geometry. It is small (30 pages).
- **Open questions:** Identify the source manuscript and scan provenance (check the 2 txt files and the ICDAR paper). Should this become a new `pinkas_dataset_bgu` source, kept distinct from `pinkas_open`?

## 4. YidTakNL / Vaybertaytsh printed-Yiddish GT (Erasmus University Rotterdam)

- **Identity:** Reshef and Gutschow.
  - GT: "Dataset for Transkribus Vaybertaytsh HTR model", figshare doi:10.6084/m9.figshare.25422844 (2024-03-16).
  - Corpus: https://zenodo.org/records/11179901.
  - Papers: JOHD 9:29 (2023) and JOHD 10:35 (2024).
- **Gemini claim check:** Not mentioned by Gemini.
- **Content:**
  - **Printed** Yiddish in Vaybertaytsh, a Hebrew-script semi-cursive typeface: Amsterdam Ashkenazi community regulations, 1709–1781.
  - The texts come from HUC (mss.huc.edu) and NLI copies.
  - The training set has 26,331 words *(inferred: the JOHD paper's "training set size of 26331")*.
  - Hebrew script, but in the **Yiddish language**.
  - 18th century, `printed_historical`.
- **Text availability:** Transkribus GT, i.e. human-corrected HTR, with images ("includes … transcriptions and images").
  - The figshare item is **link-only**, pointing to SURFdrive (`surfdrive.surf.nl/files/index.php/s/mov7H4wDaog4zkF`). The format (likely PAGE XML from Transkribus) is `Needs verification`.
  - The Zenodo record holds docx/pdf editions (27 files), which are text only.
- **Access:** figshare API and an external SURFdrive share. Stability is medium, because the share link could disappear.
- **Rights:**
  - figshare licence: "CC BY 4.0" *(verified 2026-11-06)*. Zenodo corpus: cc-by-4.0 *(verified 2026-11-06)*.
  - The source prints are PD (18th century). Whether the HUC/NLI scan reproductions carry extra terms is per item, `Needs verification`.
  - Proposed: `CC-BY-4.0`; `open_with_attribution`; status `allowed` (provisional).
- **Fixture feasibility:** Probably yes, once the SURFdrive bundle structure is confirmed. Item URLs listed in the dataset description (not loaded): https://mss.huc.edu/portfolio/rbr-o-128/ and https://www.nli.org.il/en/books/NNL_ALEPH990012586850205171/NLI.
- **HeOCR value:** **Medium-high.** It is the only real printed Hebrew-script OCR GT with images and an open licence that I found. It covers an unusual typeface.
- **Open questions:** Is Yiddish in HeOCR scope (Hebrew script vs Hebrew language)? Does the content-type vocabulary need a script or language tag?

## 5. MiDRASH (ERC Synergy 101071829) outputs

- **Identity:**
  - Hosts and partners: EPHE-PSL hosts (Olszowy-Schlanger, Stökl Ben Ezra), with TAU (Dershowitz), Bar-Ilan (Shmidman), NLI and Haifa. Runs 2023-10-01 to 2029-09-30.
  - Project pages: https://www.ephe.psl.eu/en/midrash *(verified 2026-11-06: the page itself mentions no datasets)* and CORDIS 101071829.
- **Gemini claim check:** **False.** Gemini says the "Friedberg Genizah Project and MiDRASH database include tens of thousands of scanned fragments alongside full and accurate transcription".
  - MiDRASH's published transcriptions are **automatic**. The record itself says "a very preliminary and imperfect result", with known segmentation, reading-order and Arabic-script errors.
  - I found no MiDRASH human-GT dataset on Zenodo, GitHub or the project pages.
  - CORDIS (per search, not loaded) mentions internally homogenized GT and a self-supervised GT pipeline ("TABA"), but nothing published.
- **Published outputs** *(all verified 2026-11-06 via the Zenodo API)*:
  - **"MiDRASH Automatic Transcriptions of the Cairo Geniza Fragments"**, https://zenodo.org/records/17734473 (2025-11-27).
    - Licence `cc-by-4.0`.
    - One 445 MB zip holding a single 1.47 GB `Transcriptions.txt`.
    - Covers the whole NLI digital Geniza image collection, keyed by NLI "99…" IDs (look them up in Ktiv).
    - Kraken 5.3.1 output: **HTR, not GT**, with no geometry.
  - **MiDRASH Geniza 01 HTR model**, https://zenodo.org/records/18732245: `cc-by-nc-sa-4.0`, reported accuracy 86.78%. It was trained on Geniza documentary and literary texts on top of a base model of "a huge variety of Hebrew script texts and prints". The training data is not released.
  - **MiDRASH transcription conventions**, https://zenodo.org/records/17931140 (cc-by-4.0): a CSV/XLSX of transcription conventions. It is useful for HeOCR's GT guidelines.
  - Related publications (not data): GenizaNexus (21810900) and the MiDRASH project paper (14878461).
- **Content:** Cairo Genizah, roughly 10th–19th century, mostly medieval. Hebrew, Aramaic and Judeo-Arabic. **Mostly pre-18th century.**
- **Rights:**
  - The transcription text is CC-BY-4.0, but it is OCR/HTR output: tier 3, diagnostics only.
  - The images are not included. NLI Ktiv Genizah items carry holding-library terms (e.g. CUL fragments "teaching, research and personal use only", per NLI records seen in search results, not loaded).
  - Proposed for transcriptions: `CC-BY-4.0`, `open_with_attribution`, status `review_only` (diagnostic text, not GT). The paired images would be `restricted_review_only`.
- **Fixture feasibility:** A single-text-line fixture is possible, but only from inside the 1.47 GB file. No image pairing is rights-clean.
- **HeOCR value:** **Low-medium.** It is a large weak-label or pseudo-label pool for Geniza HTR research. It is never GT.
- **Open questions:** Contact MiDRASH (they invite requests via a Google Form linked from the model record) about releasing a human-GT subset.

## 6. Princeton Geniza Project (PGP) transcriptions

- **Identity:** Princeton (Rustow, Koeser).
  - https://geniza.princeton.edu/
  - Data repos: https://github.com/princetongenizalab/pgp-text and `pgp-metadata`. Zenodo backups: 22663982 and concept 15839055.
- **Gemini claim check:** Not named by Gemini. It is the real "Genizah fragments with full human transcription" resource that Gemini may have been gesturing at.
- **Content:**
  - Scholar-typed transcriptions of Geniza documents, mostly documentary, mostly Judeo-Arabic plus Hebrew/Aramaic.
  - Medieval (c. 10th–13th century, `inferred`), so **outside HASH scope.**
- **Text availability:** Human transcriptions as W3C/IIIF annotations, keyed to IIIF canvases at CUDL, JTS, Penn and others. Line breaks are kept as `<li>` items.
  - The checked sample's geometry is coarse: one region `xywh=percent:1,1,98,98` per canvas, not line polygons.
  - Sample: `annotations/00000/444/list/cudl_MS-TS-00013-J-00035-00003_canvas_1.json` → CUL T-S 13J35.3 *(verified 2026-11-06)*.
  - Per-PGPID txt/html exports also exist.
- **Access:** GitHub (automated backups updated daily), Zenodo snapshots, IIIF. No rate limits found.
- **Rights:**
  - pgp-metadata README: "released under the noncommercial Creative Commons Attribution 4.0 license (CC-BY-NC.4.0)" *(verified 2026-11-06)*. `pgp-text` has no LICENSE file.
  - The images belong to the holders. The CUL IIIF manifest for T-S 13J35.3 says: "may be used in accord with fair use and fair dealing provisions … If you wish to reproduce it … contact" CUL. Its metadata is CC0 *(verified 2026-11-06)*.
  - Proposed: `CC-BY-NC-4.0` (new) / `RESTRICTED-NONOPEN`; `restricted_review_only`; status `review_only`.
- **Fixture feasibility:** Text and IIIF links are easy to fixture. Images can't be committed. Samples: https://geniza.princeton.edu/documents/444/ and https://cudl.lib.cam.ac.uk/iiif/MS-TS-00013-J-00035-00003.
- **HeOCR value:** **Medium.** A large volume of human text paired to images by IIIF, but NC, page-level only, and with mixed languages.
- **Open questions:** Is page-level (not line-level) human text useful for HeOCR's aligner (forced alignment against HTR line segmentation)?

## 7. Friedberg Genizah Project / FJMS portal

- **Identity:** Friedberg Jewish Manuscript Society. https://fgp.genizah.org/ redirects to https://fjms.genizah.org/?lang=eng (login portal).
- **Gemini claim check:** **False as an open source.** Gemini claims it holds "full and accurate transcription" alongside images for open reuse. The portal requires registration, and its terms forbid downloading images.
- **Rights** *(verified 2026-11-06, from the terms text embedded in the portal page)*:
  - "I shall not use any image, data or information … for commercial use of any kind … only for personal study and research".
  - Images: "I will not download, store, copy, print, reproduce or publish any of these images … without written consent from the owners and the FJMS".
  - Transcriptions "belong to their respective authors".
  - Users must also grant FJMS a licence over their own findings.
- **Content and text:** Images of Genizah fragments plus scholarly transcriptions for some of them; medieval. Not assessed further.
- **Access:** Login only. No API found.
- **Proposed:** `RESTRICTED-NONOPEN`; `blocked`; status **`blocked`**. It requires an account, bans downloads, and is research-only.
- **Fixture feasibility:** None.
- **HeOCR value:** **None** (blocked).
- **Open questions:** None. Don't pursue.

## 8. Academy of the Hebrew Language, "Ma'agarim" (Historical Dictionary Project)

- **Identity:** https://maagarim.hebrew-academy.org.il/ (Ma'agarim 3.0). It blocks scripted fetches through Cloudflare; I loaded it in the built-in browser *(verified 2026-11-06)*.
- **Gemini claim check:** Gemini's description is **partly wrong**.
  - Gemini says it has "thousands of manually transcribed manuscripts and documents" and that researchers can get access to the source files.
  - It is a **text corpus** (genres from Bible through Genizah and Karaite literature up to modern literature and journalism). There are no paired page images.
  - Access to source files is not a free research grant. The terms say entire texts can be **purchased** for research or non-commercial use.
- **Rights** (terms page, Hebrew and English; quoted from the English version):
  - "All rights to the site, including software and database content, are reserved"
  - "No commercial use … without prior written permission"
  - "Entire texts may be purchased … for research or other non-commercial purposes"
- **Content and text:** Human-typed, diplomatic-style text editions, some based on manuscripts. **No images.** Alignment to scans would need a separate image source plus a purchase.
- **Access:** Web search UI with a registered-user login. No API or bulk export.
- **Proposed:** `RESTRICTED-NONOPEN`; `blocked`; status **`blocked`** (text-only, all rights reserved, paid).
- **Fixture feasibility:** None.
- **HeOCR value:** **Low.** Text-only and closed. At most a reference for spelling or lexicon checks, under its terms.
- **Open questions:** None.

## 9. HHD family (BGU: HHD_v0, HHD_gender, HHD_age) and `sivan22/hebrew-handwritten-dataset`

- **Identity:** Rabaev et al., "The HHD Dataset", ICFHR 2020.
  - HHD_gender: https://zenodo.org/records/4729908. HHD_age: https://zenodo.org/records/14996257.
  - HF re-upload of HHD_v0 characters: https://huggingface.co/datasets/sivan22/hebrew-handwritten-dataset.
- **Gemini/HASH claim check:**
  - HASH lists sivan22 as a CC-BY-3.0 candidate. The card does say `license: cc-by-3.0`, but it describes itself as "HDD_v0 … isolated Hebrew characters … collected from hand-filled forms", i.e. **a re-upload of BGU's HHD_v0** *(verified 2026-11-06)*.
  - The BGU originals say "This database may be used for non-commercial research purpose only" (verified on both Zenodo records). The uploader's CC-BY-3.0 label therefore can't be trusted: it conflicts with upstream.
  - The two Zenodo licence fields also contradict their own descriptions: HHD_gender = `other-pd`, HHD_age = `cc-by-4.0`.
- **Content:** Modern handwriting from volunteers aged 8 to late 60s:
  - about 819–850 forms, each a paragraph of about 62 words, in 50 form variants;
  - in sivan22, 5,093 isolated characters (3,965 train / 1,128 test, 28 classes).
  - Content type: `handwritten_modern`.
- **Text availability:**
  - sivan22 has a class label per character only, no page text.
  - The form datasets ship gender or age labels. Their page text is only implied by the 50 form templates. Whether per-form transcriptions ship is `Needs verification`.
- **Rights:**
  - Upstream: research-only, non-commercial.
  - The writers are living people, some of them minors. Consent and privacy terms are not stated publicly.
  - Proposed: `RESTRICTED-NONOPEN`; `restricted_review_only`; status `blocked` for HeOCR releases. HASH already rejects HHD_gender and HHD_v0. **HASH's sivan22 candidate should be moved to rejected** for the same reason.
- **Fixture feasibility:** Not rights-clean.
- **HeOCR value:** **Low** (characters only, or label-only forms, under conflicting licences).
- **Open questions:** Should anyone ask BGU (Rabaev) whether a CC-BY relicence of the full HHD is possible? They did release Pinkas as CC-BY.

## 10. HebHTR (GitHub, Lotemn102)

- **Identity:** https://github.com/Lotemn102/HebHTR (2019; last push 2023).
- **Why HASH rejected it** (now confirmed *(verified 2026-11-06)*):
  - **The repo has no data images at all.** It contains only model checkpoints, `corpus.txt` (a word list) and code, with no LICENSE file.
  - The README describes a private dataset of about 100k word images. About 50k are "real words, taken from students scanned exams", hand-labeled. About 50k are synthetic.
  - The private set is not published, and its consent and privacy status (student exams) is unknown.
  - The word-beam corpus was built from MILA, TheMarker and Knesset text, under their own licences.
- **Proposed:** `UNKNOWN`; `blocked`; status `blocked`. There is no data and no licence, and there are privacy concerns.
- **HeOCR value:** **None** as a data source.

## 11. Other Hugging Face Hebrew image-text datasets (search: "hebrew ocr", "htr", "handwrit", "manuscript", "geniza"; filters `language:he` + image modality, `language:yi`)

| Dataset | What it is | Licence (stated) | Verdict |
|---|---|---|---|
| `ivrit-ai/hebrew-handwriting-ocr-benchmark` | Lines and pages parquet; modern handwriting benchmark | `other`, **gated** (auto) | Card unreadable without login. `Needs verification`; maintainer could request access |
| `cyttic/matan-hebrew-handwriting-words` | 22,148 word crops from 491 writers, derived from a "matan" line-level corpus | `other`; card says "placeholder — set it to match" | **Provenance unknown → `UNKNOWN` / blocked** until "matan" is identified |
| `cyttic/pinkas-hebrew-lines` | Line crops of the BGU Pinkas Dataset | CC-BY-4.0 | Use the original (section 3) |
| `stanford-oval/churro-dataset` (CHURRO-DS) | About 99k historical pages, 46 language clusters; Hebrew handwriting is a reported metric slice (`benchmark_results.json`) | "use is permitted for research purposes only" | `RESTRICTED-NONOPEN` / review_only. The Hebrew subset's upstream sources are `Needs verification` (likely BiblIA, Pinkas etc.; datasets-server query failed) |
| `alexandersdata/hebocrbench-v1` (ex-`ssdataanalysis`) | 34,267 modern printed eval inputs | `other`; **"contains no transcription gold"** | Useless as GT; images only |
| `johnlockejrr/sam_gt` | Samaritan Pentateuch line images plus text | none | Samaritan script, out of scope |
| `VItaldob/viciebski-pralietaryj-yiddish` | 2,684 Yiddish newspaper blocks, Vitebsk 1930–33 | `other`; "No transcriptions" | Images only; Soviet-era rights unclear; low |
| `kilometraz/kilometraz-daf-images` | Vilna Shas page renders with highlights | CC0 | Derived renders, no GT; low |
| `AmitKabya/hebrew-doc-ocr-benchmark`, `youssefkhalil320/hebrew-ocr-doctags-dataset(_v2)`, `cyttic/heb-*`, `asafd60/heb-synthtiger-*`, `isaacmg/synthetic_*`, `jhonnyisaacc/hutter` | Synthetic or rendered (pptx, Ben-Yehuda texts rendered in fonts, diffusion handwriting) | various | **Synthetic, not real.** Out of this track (row checks *(verified 2026-11-06)*) |
| `bsesic/HebrewManuscripts`, `nfiowegeo42nf/cairo_genizah` | Letter-classification README only, or an empty repo | MIT / CC-BY-SA | No usable data |

No HF dataset of real scanned Hebrew pages with open-licensed human text exists apart from the Pinkas derivative *(verified 2026-11-06 for the searches above)*.

## 12. Printed-Hebrew OCR GT: other leads

- **No open human-GT dataset of modern or historical printed (square/Rashi) Hebrew scans was found** on Zenodo, HTR-United, GitHub or HF. The YidTakNL Yiddish print set (section 4) is the exception.
  - Zenodo queries: "hebrew print OCR ground truth", "hebrew page xml", "hebrew alto".
  - GitHub: `hebrew ocr`, `rashi ocr`, `yiddish ocr`, `hebrew tesstrain`.
- **HTR-United catalogue** (138 entries): BiblIA is the only Hebrew-script entry. OCR-D `gt_structure_text` (CC-BY-SA-4.0, 217 files, 1500–1900 prints) lists `heb` among its languages. Its Hebrew share is probably a few words inside German prints *(inferred)*. Low.
- **Tesseract `heb` training data** is rendered from text and fonts, not real-scan GT *(inferred; not re-checked)*.
- **HebOCRBench** withholds its gold (section 11). **CHURRO-DS** is research-only (section 11).
- **Kennicott-collation alignment** (Bambaci and Stökl Ben Ezra, CHR 2023, Zenodo 13739814) and the **Rashi textual-fluidity preprint** (Zenodo 22926125, Sept 2026, "Eighty-four comments were corrected by hand") are methods papers. They publish no GT data.
- **openmasorah/masoretic-benchmark** (GitHub): 96 verses from 4 folios of the Leningrad Codex. Text PD, annotations CC0. Images probably not included *(inferred)*. Low, medieval.

## 13. Tikkoun Sofrim and Scribes of the Cairo Geniza (crowdsourcing projects)

- **Tikkoun Sofrim** (Tanhuma-Yelamdenu manuscripts; HTR plus crowd correction; JOCCH 15(2), 2022):
  - No published dataset was found.
  - The repos `drore/tikkoun` (no licence) and `drore/ts2` (MIT) are app code.
  - `ajwecker/TS1218` has no licence. It contains raw line data for BnF héb. 150 and Geneva 146 (`WEB-INF/data/*.txt`, 1–3.7 MB) *(verified 2026-11-06)*.
  - Proposed `UNKNOWN`; review_only. Ask the authors (Wecker, Stökl Ben Ezra) whether the corrected Tanhuma lines are published anywhere.
- **Scribes of the Cairo Geniza** (Penn / Zooniverse):
  - The published "Sorting Phase" dataset is script-type classifications for 40,152 fragments, not transcriptions. Its licence is CC BY 4.0 per the Penn repository record (from search results, not loaded).
  - No transcription-phase dataset was found. Low.

---

## Gemini claims that do not hold

1. **"FGP and MiDRASH: tens of thousands of fragments with full, accurate transcription alongside the images."** False.
   - FGP is a login-only, no-download, research-only portal.
   - MiDRASH's corpus-wide transcriptions are self-described preliminary *automatic* HTR, published without images.
2. **"Researchers can get access to Ma'agarim's transcribed source files for research."** Overstated.
   - Full texts are sold for non-commercial research.
   - It is text-only, with all rights reserved.
3. **"Open eScriptorium/Kraken corpora from Bar-Ilan, Haifa, BGU and EPHE, fully transcribed in PAGE/ALTO."** Partly true.
   - EPHE (BiblIA, Sofer Mahir) and BGU (Pinkas) exist, but they are small or NC.
   - I found no open GT datasets from Bar-Ilan or Haifa (both are MiDRASH partners).
4. **Other catalogue errors:**
   - HTR-United lists BiblIA as CC-BY-SA 4.0; it is actually CC-BY-NC-SA 4.0.
   - The HASH doc points to a `github.com/MiDRASH-Project` org that does not exist.
   - HASH's sivan22 "CC-BY-3.0" label conflicts with the upstream NC terms.

## Ranked summary

| Rank | Source | Content (period) | Human GT + images? | Licence → proposed | Status | HeOCR value |
|---|---|---|---|---|---|---|
| 1 | Pinkas Dataset (BGU, Zenodo 3569694) | Cursive community records, c. 1500–1800 | Yes: PAGE word/line + 30 JPG | CC-BY-4.0 → `CC-BY-4.0`, open_with_attribution | allowed (verify scan provenance) | High |
| 2 | YidTakNL Vaybertaytsh GT (figshare 25422844) | Printed Yiddish, 1709–1781 | Yes (Transkribus GT; link-only bundle) | CC-BY-4.0 → `CC-BY-4.0` | allowed (verify bundle and scans) | Medium-high |
| 3 | BiblIA (Zenodo 5167263) | Medieval bookhands, 1000–1499 | Yes: ALTO lines + 132 BnF JPG (70 BAV links only) | CC-BY-NC-SA-4.0 → new value / `RESTRICTED-NONOPEN` | review_only | High for eval; NC |
| 4 | Sofer Mahir ALTO (GitHub) | 16 medieval Tannaitic codices | ALTO lines, human-corrected HTR; no images | CC BY-NC-SA → `RESTRICTED-NONOPEN` | review_only | Medium-high |
| 5 | Princeton Geniza Project (pgp-text) | Geniza documents, medieval | Human text, page-level, IIIF-linked | CC-BY-NC-4.0; images "fair use" → `RESTRICTED-NONOPEN` | review_only | Medium |
| 6 | MiDRASH automatic transcriptions (Zenodo 17734473) | Whole NLI Geniza | **HTR only**, no images | CC-BY-4.0 (text) | review_only (diagnostic) | Low-medium |
| 7 | CHURRO-DS Hebrew slice (HF) | Historical | Yes, mixed upstreams | Research-only → `RESTRICTED-NONOPEN` | review_only | Low-medium |
| 8 | ivrit-ai handwriting benchmark (HF) | Modern handwriting | Unknown (gated) | `other` → `UNKNOWN` | Needs verification | Unknown |
| 9 | HHD family / sivan22 | Modern forms or characters | Characters only, or labels only | NC research-only (conflicting labels) → `RESTRICTED-NONOPEN` | blocked | Low |
| 10 | matan words (HF) | Modern handwriting | Words + text | Placeholder `other` → `UNKNOWN` | blocked until provenance known | Unknown |
| — | Friedberg Genizah Project | Geniza | Login-only | All rights reserved → `RESTRICTED-NONOPEN` | blocked | None |
| — | Ma'agarim | Text corpus | No images | All rights reserved, paid → `RESTRICTED-NONOPEN` | blocked | Low |
| — | HebHTR | — | No data published | None → `UNKNOWN` | blocked | None |

**Suggested new controlled values:** `CC-BY-NC-SA-4.0` and `CC-BY-NC-4.0` (both mapped to `restricted_review_only`). Possibly also a script/language tag for Yiddish-in-Hebrew-script, and a `printed_historical` sub-tag for typeface (Vaybertaytsh, Rashi).
