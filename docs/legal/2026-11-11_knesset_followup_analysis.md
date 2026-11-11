# Knesset bills, and open points on committee protocols: follow-up legal-risk analysis (received 2026-11-11)

> **Status: adopted.** On 2026-11-11 the maintainer (Shay Palachy Affek) adopted this analysis's recommendations and suggestions: "as usual, I ascribe to his recommendations and suggestions". The decision record is `planning/decisions/2026-11-11-knesset-protocols-training-vs-release.md`, Part 2.
>
> **Provenance.**
> - The text below is Google Gemini's answer to the follow-up prompt in `docs/legal/2026-11-11_knesset_followup_prompt.md`, sent in the same conversation as `docs/legal/2026-11-11_knesset_protocols_analysis.md`.
> - It is copied verbatim, sha256 `06c30ee6f21754eb489a55a57187d37d88805861a5420c711b9e7746fd9da186` of the received file. Typos and formatting are kept as received.
> - It is a legal-risk analysis, not legal advice, and its citations, quotes and contact addresses have not been independently verified.
> - It corrects the first analysis's Knesset email address.

---

## **Summary Matrix: Knesset Bills (*הצעות חוק*) by Type, Period, and Activity**

In the table below, **Activity A** is training OCR models and releasing weights under Apache-2.0; **Activity B** is publicly releasing cropped text-line images and their transcriptions under CC0 or CC BY-SA.

| Bill Type | Period | Activity A: Train & Release Apache-2.0 Weights | Activity B: Publish Line Crops & Transcriptions (CC0 / CC BY-SA) |
| :---- | :---- | :---- | :---- |
| **(i) Government Bills** (*הצעות חוק הממשלה*, published in *Reshumot*) | **1\. Up to Dec 31, 1975** *(1976 on Jan 1, 2027\)* | **YES** *(Confidence: High — 95%)* | **YES** — 50-year State copyright expired under §§ 36, 42–43, 78(a). *(Confidence: High — 95%)* |
| **(i) Government Bills** (*הצעות חוק הממשלה*, published in *Reshumot*) | **2\. Jan 1, 1976 – May 24, 2008** | **YES** — via § 19 Fair Use & 2022 MoJ ML Opinion. *(Confidence: High — 90%)* | **UNCERTAIN / NO without permission for Explanatory Notes (*דברי הסבר*) or un-enacted draft text; YES for clauses enacted verbatim into law.** *(Confidence: High — 85%)* |
| **(i) Government Bills** (*הצעות חוק הממשלה*, published in *Reshumot*) | **3\. May 25, 2008 – Present** | **YES** — via § 19 Fair Use & 2022 MoJ ML Opinion. *(Confidence: High — 90%)* | **UNCERTAIN / NO without permission for Explanatory Notes (*דברי הסבר*) or un-enacted draft text; YES for clauses enacted verbatim into law.** *(Confidence: High — 85%)* |
| **(ii) Private Members' Bills** (*הצעות חוק פרטיות*, Knesset PDFs / *Reshumot*) | **1\. Up to Dec 31, 1975** *(1976 on Jan 1, 2027\)* | **YES** *(Confidence: High — 95%)* | **YES** for bills drafted by MKs/Knesset staff (§ 36 State works); **CAUTION** if drafted by an outside private party whose author died less than 70 years ago (§ 38). *(Confidence: Medium-High — 80%)* |
| **(ii) Private Members' Bills** (*הצעות חוק פרטיות*, Knesset PDFs / *Reshumot*) | **2 & 3\. Jan 1, 1976 – Present** | **YES** — via § 19 Fair Use & 2022 MoJ ML Opinion. *(Confidence: High — 90%)* | **NO / UNCERTAIN** — Not "laws" (*חוקים*) under § 6; potentially subject to 50-year State copyright (§ 36\) or 70-year p.m.a. private copyright (§ 38\) if externally drafted. *(Confidence: High — 85%)* |
| **(iii) Committee Bills** (*הצעות חוק של ועדה*, Knesset / *Reshumot*) | **1\. Up to Dec 31, 1975** *(1976 on Jan 1, 2027\)* | **YES** *(Confidence: High — 95%)* | **YES** — Drafted by Knesset committee legal staff; 50-year State copyright expired under §§ 36, 42–43. *(Confidence: High — 95%)* |
| **(iii) Committee Bills** (*הצעות חוק של ועדה*, Knesset / *Reshumot*) | **2 & 3\. Jan 1, 1976 – Present** | **YES** — via § 19 Fair Use & 2022 MoJ ML Opinion. *(Confidence: High — 90%)* | **UNCERTAIN / NO without permission for Explanatory Notes or un-enacted changes; YES for clauses enacted verbatim into law.** *(Confidence: High — 85%)* |

## **Part 1: Bills (*הצעות חוק*) from 1976 Onward**

### **Question 1: Section 6 vs. Section 36, and Differences Across Bill Types (i), (ii), and (iii)**

* **Short Answer:** Bills (*הצעות חוק*) and their explanatory notes (*דברי הסבר*) are **not** *"חוקים"* (laws) under Section 6 of the Copyright Act, 2007, nor are standalone bill booklets part of *"דברי הכנסת"* (the plenary record). Unless a purposive judicial interpretation expands Section 6, bills created by civil servants, MKs, or Knesset legal advisers fall under **Section 36 (State works)** with a **50-year term from creation** under Section 42\. However, Type (ii) Private Members' Bills carry an extra risk: when an outside NGO, academic, lobbyist, or private law firm drafts the bill text or explanatory notes for an MK without assigning copyright to the State, that contribution may attract a **life \+ 70 years** private copyright under Sections 33 and 38\.  
* **Confidence Level:** **High (85%)** that Section 6 does not textually cover standalone bills/explanatory notes; **High (90%)** on the distinction between Types (i)/(iii) and externally drafted Type (ii) bills.

#### **Reasoning & Primary Sources**

> 1. **Established Law — Statutory Definitions Distinguish a "Law" (*חוק*) from a "Bill" (*הצעת חוק*):**  
   * Section 6 of the Copyright Act, 2007 exempts *"חוקים, בתקנות, בדברי הכנסת ובהחלטות שיפוטיות..."*.  
   * Under Section 3 of the **Interpretation Law, 1981** (*חוק הפרשנות, התשמ"א-1981*), *"חוק"* (law) means a legislative act enacted by the Knesset (or a Mandate ordinance). Similarly, the **Transition Law, 1949** (*חוק המעבר, התש"ט-1949*, § 10\) and the **Government and Law Arrangements Ordinance** distinguish between enacted laws published in *Sefer HaChukim* (*ספר החוקים*) and bills published in the *Hatza'ot Hok* (*הצעות חוק*) series of *Reshumot*.  
   * In Israeli policy discussions surrounding the establishment of the National Legislation Database (*מאגר החקיקה הלאומי*), civil society submissions—such as the Israeli Digital Rights Movement's position paper to the Knesset—explicitly noted that while Section 6 exempts *"חוקים"*, **explanatory notes (*דברי הסבר*) in *Hatza'ot Hok* are not expressly listed in Section 6**.  
> 2. **Comparison of the Three Bill Types:**  
   * **(i) Government Bills (*הצעות חוק הממשלה*):** Drafted by Ministry of Justice legislative counsel (*מחלקת ייעוץ וחקיקה*) and ministry legal advisers in the course of their state employment. Both the proposed statutory clauses and the explanatory notes (*דברי הסבר*) are unambiguously **State works under Section 36** (*"יצירה שנוצרה או שהוזמנה על ידה או על ידי עובד המדינה עקב עבודתו ובמהלכה"*), protected for **50 years from creation** (Section 42).  
   * **(iii) Committee Bills (*הצעות חוק מטעם ועדה*):** Authorized under the Knesset Law and the Knesset Rules of Procedure (regarding Basic Laws, Knesset laws, State Comptroller laws, etc.) and drafted by the Knesset Committee's legal adviser (*הייעוץ המשפטי לוועדה*). Because Knesset legal advisers are State employees, Type (iii) bills are likewise pure **Section 36 State works** (50 years from creation).  
   * **(ii) Private Members' Bills (*הצעות חוק פרטיות*):**  
     * *When drafted by the MK, the MK's parliamentary assistants, or the Knesset Legal Department:* An MK is an *"officeholder or functionary under an enactment in an institution of the State"* (*נושא משרה או בעל תפקיד על פי חיקוק במוסד ממוסדות המדינה*) under Section 36, so the bill is a State work (50 years from creation).  
     * *The Outside-Drafter Trap:* In Israel, a significant proportion of Private Members' Bills (and their explanatory notes) are drafted *verbatim* by external civil-society associations (NGOs), university legal clinics, labor unions, or private law firms and handed to an MK to table. Because the State neither employed nor formally commissioned the NGO or clinic for consideration, **Section 36 does not transfer ownership of the NGO's draft to the State**. Unless the outside drafter assigned copyright or dedicated it to the public domain, the explanatory notes (and un-enacted draft text) remain subject to **regular copyright (life of the author \+ 70 years under Section 38\)**.

### **Question 2: The "Dropped Clause" in the 2003 Memorandum and 2005 Government Bill**

* **Short Answer:** Your team's recollection is close, with one critical refinement: **the broader phrasing was not dropped from the operative statutory clause—rather, the operative clause was narrow from the start, while the broader phrasing appeared only in the Explanatory Notes (*דברי הסבר*).** In both the 2003 Memorandum (Section 5\) and the 2005 Government Bill (Section 6), the operative statutory text listed the exact same four items enacted in 2007 (*חוקים, תקנות, דברי הכנסת והחלטות שיפוטיות*). It was the **Explanatory Notes** that used open-ended language: *"מוצע לקבוע במפורש כי לא תהיה זכות היוצרים בחוקים, פסקי דין, **ומסמכים דומים**"* (2003 Memorandum) and *"לגבי דברי חקיקה, פסקי דין **וכיו"ב פרסומים רשמיים** מוצע שלא להקנות זכות יוצרים (ר' סעיף 6 המוצע)"* (2005 Bill).  
* **Confidence Level:** **Very High (95%)** — verified directly against the primary texts of the 2003 Memorandum and the 2005 Bill.

#### **Reasoning & Primary Sources**

> 1. **Verified Primary Text — 2003 Ministry of Justice Memorandum (*תזכיר חוק זכות יוצרים, התשס"ד-2003*):**  
   * **Operative Clause (Section 5):***"5. על אף הוראות סעיף 3, לא תהיה זכות-יוצרים בחוקים, תקנות, דברי הכנסת והחלטות שיפוטיות של בית משפט או של כל רשות שלטונית המפעילה סמכות שפיטה על פי דין."*  
   * **Explanatory Note to Section 5 ([2003 Memorandum PDF](https://www.psakdin.co.il/kannex/nws_ndis_1.pdf)):***"מוצע לקבוע במפורש כי לא תהיה זכות היוצרים בחוקים, פסקי דין, **ומסמכים דומים**, וזאת מתוך הכרה בכך שמסמכים אלה נועדו להפצה לציבור."*  
> 2. **Verified Primary Text — 2005 Government Bill (*הצעת חוק זכות יוצרים, התשס"ה-2005*, ה"ח הממשלה 196, מיום 20.7.2005, עמ' 1116, 1122):**  
   * **Operative Clause (Section 6, [Hatza'ot Hok 196 text](https://www.copyrights.org.il/index.php?module=article&article=233&)):***"6. על אף הוראות סעיף 4, לא תהא זכות יוצרים בחוקים, בתקנות, בדברי הכנסת ובהחלטות שיפוטיות של בית משפט או של כל רשות שלטונית המפעילה סמכות שפיטה על פי דין."*  
   * **Explanatory Note to Chapter E ([Knesset Tracker / Bill 196 Archive](https://knesset-tracker.co.il/knesset/17/law/113653)):***"יצוין כי לגבי דברי חקיקה, פסקי דין **וכיו"ב פרסומים רשמיים** מוצע שלא להקנות זכות יוצרים (ר' סעיף 6 המוצע)."*  
> 3. **Interpretive Significance under Israeli Law (Established Law vs. Inference):**  
   * *Because the Knesset did not delete a "similar documents" clause from the operative bill text* (it was never in the operative text), there is **no negative legislative history of a rejected amendment** (where the Knesset votes down a broader clause).  
   * Instead, you have a tension between a **closed statutory list** in Section 6 (four specific items) vs. **broad purposive language in the Explanatory Notes** (*"ומסמכים דומים"*, *"וכיו"ב פרסומים רשמיים"*), alongside Chapter E (Sections 36 and 42), which intentionally retained a 50-year State copyright for general government works to allow the State to recoup costs or prevent commercial hijacking of certain state publications (like official maps or central bureau of statistics books).  
   * *Inference:* Under Israeli purposive interpretation (*פרשנות תכליתית*, **CA 165/82 *Kibbutz Hatzor v. Rehovot Assessing Officer***), a court cannot easily add a fifth unenumerated category to Section 6 when the text is specific and Chapter E provides the default rule for all other State works. However, the phrase *"דברי חקיקה... וכיו"ב פרסומים רשמיים"* in the Explanatory Notes strongly supports reading *"דברי הכנסת"* and *"חוקים"* generously to cover materials integral to the legislative process. Still, because no court has issued such a ruling, a risk-averse open-source project cannot treat post-1975 bills or explanatory notes as clearly exempt under Section 6\.

### **Question 3: Bills That Became Law & the Status of Explanatory Notes (*דברי הסבר*)**

* **Short Answer:**  
  1. **Statutory clauses in a bill that were enacted into law without change:** **YES, free of copyright under Section 6\.** Because copyright protects the abstract literary expression (*היצירה*) rather than the specific PDF/print issue in which it was printed, once a statutory clause is enacted as a *"חוק"* (law), Section 6 extinguishes copyright in that exact statutory wording—including where that identical wording appeared earlier in the *Hatza'ot Hok* bill booklet.  
  2. **Rejected/amended draft clauses and Explanatory Notes (*דברי הסבר*):** **NO / UNCERTAIN.** Explanatory notes are never enacted into the law in *Sefer HaChukim*; they remain a distinct literary commentary authored by civil servants (or MKs) explaining the background and purpose of the bill. They remain subject to Section 36 (50 years from creation).  
* **Confidence Level:** **High (85%)** on enacted statutory clauses losing copyright; **High (90%)** on Explanatory Notes remaining separate works outside *"חוקים"*.

#### **Reasoning & Primary Sources**

* **Merger / Extinguishment for Enacted Clauses:** Section 6 states *"לא תהא זכות יוצרים בחוקים"* ("there shall be no copyright in laws"). If Clause 4 of a 1995 Government Bill is identical to Section 4 of the enacted 1995 Law, copying a line from Clause 4 of the bill copies the text of the law itself. Neither the State nor the Knesset could sue a user for reproducing the text of an enacted statute merely because the image was scanned from the *Hatza'ot Hok* issue rather than *Sefer HaChukim* (as the typographic layout of standard *Reshumot* legislation is unoriginal).  
* **Why Explanatory Notes Are Separate Works:** In Israeli legislative practice, the Knesset votes only on the statutory clauses, never on the *דברי הסבר* (Explanatory Notes). When the law is published in *Sefer HaChukim*, the Explanatory Notes are omitted. As documented in the Digital Rights Movement's submission on the National Legislation Database, *דברי הסבר* are separate prose works that are not part of the enacted *"חוק"*. Unless 50 years have elapsed from their creation (i.e., pre-1976), they are protected by State copyright under Section 36\.

### **Question 4: Bills Read or Printed in the Plenary Record (*Divrei HaKnesset*)**

* **Short Answer:** **YES.** When the text of a bill (or a portion of it) is read aloud on the Knesset floor or printed as an official appendix (*נספח*) inside the official plenary record (*דברי הכנסת*), that copy—as part of *Divrei HaKnesset*—is expressly exempt from copyright under the plain text of **Section 6** (*"לא תהא זכות יוצרים... בדברי הכנסת"*).  
* **Confidence Level:** **High (85%)** for bill texts printed inside *Divrei HaKnesset* (with the caveat to avoid third-party private works if any were read into the record).

#### **Reasoning & Primary Sources**

* **Plain Text of Section 6:** Section 6 unconditionally exempts *"דברי הכנסת"*. In Knesset practice, bills presented for First Reading (*קריאה ראשונה*) or Preliminary Reading (*קריאה טרומית*) have historically been printed in the appendices (*נספחים*) to the plenary sitting in *Divrei HaKnesset* or read into the plenary record.  
* **No Internal Carve-Out in Section 6:** Unlike committee protocols (where the dispute is whether the document series itself is part of *Divrei HaKnesset*), the plenary record and its integral legislative appendices **are** literally *Divrei HaKnesset*. For Government, Committee, or MK-authored bills printed inside the plenary *Divrei HaKnesset* volumes, the State is the sole rightsholder and has statutorily waived copyright over the entire publication in Section 6\. (The only theoretical exception would be if an MK read a private third party's copyrighted poem or NGO treatise into the record without the third party's authorization, as Section 6 is intended to waive public/official copyright rather than expropriate unrelated private authors).

### **Question 5: Publication by Law in *Reshumot* (Section 6 and Section 21\)**

* **Short Answer:** Mandatory statutory publication in *Reshumot* does **not** automatically bring a document under Section 6 (since *Reshumot* also publishes trademark notices, patent applications, and government announcements that are not listed in Section 6). Nor does **Section 21** (works deposited for public inspection) authorize bulk commercial republication under CC0, because Section 21 limits copying to *"the purpose for which it was made available for public inspection, and to the extent justified having regard to that purpose"*.  
* **Confidence Level:** **High (90%)**.

#### **Reasoning & Primary Sources**

* **Section 21 of the Copyright Act, 2007 ([Wikisource](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D)):***"21. (א) העתקה של יצירה המופקדת לעיון הציבור לפי חיקוק, מותרת למטרה שלשמה הועמדה לעיון הציבור, ובהיקף המוצדק בשים לב למטרה האמורה."*  
* Section 21 is designed for documents deposited by law in public registries (such as building plans in municipal planning committees, company articles of association in the Companies Registrar, or environmental impact statements) so citizens can inspect and copy them for civic participation, objections, or legal review. It is a targeted **permitted use** (*שימוש מותר*), not a public-domain dedication, and does not grant a downstream license to repackage post-1975 explanatory notes under CC0 for commercial redistribution.

### **Question 6: Website Terms of Use (gov.il / *Reshumot* and knesset.gov.il) & Government Open-Data Policy (Resolution 1933\)**

* **Short Answer:**  
  1. **gov.il (Ministry of Justice / *Reshumot*) and knesset.gov.il Terms of Use:** Both websites have standard browse-wrap Terms of Use asserting State/Knesset copyright over all text and graphics on the site ("the Protected Material" / *החומר המוגן*) and prohibiting copying or distribution without prior written permission, subject to Fair Use and exceptions in law. Neither imposes an extra click-wrap contract for downloading PDFs, and **neither restricts Activity A (Fair Use ML training)** because both explicitly defer to statutory Fair Use. For **Activity B (publishing post-1975 datasets)**, both sets of terms confirm that neither the Ministry of Justice nor the Knesset has granted a blanket CC0 waiver over copyrighted site text.  
  2. **Government Resolution 1933 and data.gov.il:** While Government Resolution 1933 (August 30, 2016\) binds executive branch ministries (including the Ministry of Justice, which publishes *Reshumot*), the open license on [data.gov.il/terms-of-use](https://data.gov.il/terms-of-use) applies **only to datasets actually published on the** data.gov.il **portal**—and even that license is a custom attribution/no-endorsement license, **not CC0**.  
* **Confidence Level:** **High (95%)**.

#### **Reasoning & Primary Sources**

> 1. **National Digital Agency / gov.il Terms of Use ([https\://www\.gov.il/he/pages/terms\_of\_use](https://www.gov.il/he/pages/terms_of_use), published Oct 25, 2022; updated Nov 8, 2026):**  
   * Explicitly states that copyright in site content belongs to the State of Israel: *"זכויות יוצרים אלו חולשות, בין השאר, על טקסט, תמונות, איורים, מפות, קטעי צליל, קטעי וידיאו, גרפיקה ויישומי תוכנה (להלן: החומר המוגן), אלא אם כן נקבע באופן מפורש כי זכויות היוצרים בחומר המוגן שייכות לגורם אחר"*.  
   * Like the Knesset site, gov.il permits Fair Use (*שימוש הוגן*) as defined by law and reasonable quotation with attribution. Because it is a passive browse-wrap notice that expressly incorporates statutory copyright exceptions, it adds **no contractual bar to Activity A (training)** or to **Activity B for public-domain works (pre-1976 bills or Section 6 enacted laws)**.  
> 2. **Why data.gov.il Does Not Make Post-1975 *Reshumot* Bills CC0:**  
   * Under the [data.gov.il Terms of Use](https://data.gov.il/terms-of-use) (updated August 30, 2025), users may create "Value Added Products" (*מוצר ערך מוסף*), but the terms state: *"אולם, זכויות היוצרים במידע שבו נעשה שימוש לפי רישיון זה, הכלול במוצר ערך מוסף, ככל שהן קיימות, יהיו שייכות למדינת ישראל, כאשר השימוש במידע יהיה בכפוף לרישיון שימוש זה"*. Thus, even if a dataset is hosted on data.gov.il, its underlying copyrighted text cannot be relicensed under **CC0** (which waives all copyright and attribution requirements globally).

## **Part 2: Open Points on Committee Protocols & Citation Verifications**

### **Question 7: Internal Evaluation Use in an Access-Restricted Repository & Publishing Summary Scores**

* **Short Answer:** **YES.** Keeping line crops and transcriptions from 1976–present committee protocols (or bills) inside a **private, access-restricted evaluation repository** to benchmark your OCR models—and publishing **only the resulting numerical summary metrics** (e.g., Character Error Rate / Word Error Rate)—is lawful on the exact same Fair Use and non-expressive-use grounds as training (Activity A).  
* **Confidence Level:** **Very High (95%)**.

#### **Reasoning & Primary Sources**

> 1. **Internal Evaluation Copies Are Protected by Section 19 (Fair Use):**  
   * Under Section 19(a) of the Copyright Act, 2007, Fair Use is expressly permitted for **research (*מחקר*), self-study (*לימוד עצמי*), and review/testing**.  
   * Under the four factors of Section 19(b)—(1) purpose and character of the use, (2) nature of the work, (3) amount/substantiality, and (4) market effect—holding an internal, non-public benchmark of governmental transcripts to measure OCR accuracy is completely transformative, non-substitutive, and has zero impact on any potential market for the work.  
   * The Ministry of Justice's [2022 Opinion on Machine Learning](https://www.gov.il/he/pages/machine-learning) encompasses the entire machine-learning development lifecycle (training, validation, and testing/evaluation) as transformative Fair Use, provided the copyrighted validation/test corpus itself is not redistributed to the public as a competing content product.  
> 2. **Publishing Summary Scores (CER / WER) Infringes Nothing:**  
   * Under **Section 5 of the Copyright Act, 2007**, copyright does not extend to facts or data (*"עובדות או נתונים"*). Aggregate evaluation metrics (such as "HeOCR-v2 CER on 1980–2020 Knesset Committee Benchmark: 1.42%") are pure mathematical facts about model performance and reproduce zero expression from the underlying protocols.

### **Question 8: Model Weights That Memorise Training Text — Legal Effect & Technical Mitigations**

* **Short Answer:** The Israeli Ministry of Justice's December 18, 2022 Opinion explicitly warns that **its Fair Use conclusion for ML training does not protect models whose outputs reproduce copyrighted training works (or substantial parts thereof) verbatim**. However, for **visual OCR models** (such as Tesseract LSTM tessdata\_best or Kraken), this risk is **virtually zero** if you apply three simple engineering guardrails: (1) do not bundle an explicit lexicon/word-list or n-gram language model extracted from post-1975 protocols; (2) train strictly on **single-line crops** rather than multi-sentence blocks; and (3) keep the decoder's implicit character/token window local.  
* **Confidence Level:** **High (90%)**.

#### **Reasoning & Practical Mitigations**

> 1. **The Legal Caveat in the 2022 MoJ Opinion:**  
   * As summarized on the official Ministry of Justice page ([https\://www\.gov.il/he/pages/machine-learning](https://www.gov.il/he/pages/machine-learning)): *"לצד קביעה עקרונית זו, חוות הדעת כוללת גם סייגים"* ("Alongside this principled determination, the opinion also includes caveats")—most notably that if a generative model memorizes and outputs a substantial part of a protected training work, the *output* (and potentially a model weight file that functions as a compressed database of the work) can infringe under Sections 11 and 12\.  
> 2. **Why Visual OCR Architectures Are Fundamentally Different from Generative LLMs:**  
   * Unlike an autoregressive LLM that generates paragraphs from a text prompt, an optical character recognition model (Tesseract's Conv-BiLSTM-CTC or Kraken's CNN-BiLSTM-CTC) is conditioned on **dense visual pixel features** at each horizontal frame and uses a Connectionist Temporal Classification (CTC) loss. Without a visual image of the line, a CTC-based OCR network cannot spontaneously recite paragraphs of Knesset protocols.  
   * Even if a modern seq2seq/Transformer OCR decoder (e.g., TrOCR) has an autoregressive text decoder, any memorization is bounded by the **maximum context length of a single training sample** (one cropped text line of \~6–12 words). Under Israeli copyright law (Section 11), reproducing an isolated 8-word factual phrase from a committee hearing does not cross the threshold of copying an original *"substantial part"* (*חלק מהותי*) of a copyrighted work.  
> 3. **Recommended Engineering Mitigations (to keep Activity A 100% clean):**  
   * **Mitigation 1 (Which you already adopted):** Never ship a DAWG dictionary (heb.wordlist, heb.punc, or KenLM n-gram model) built from post-1975 protocol text inside your Apache-2.0 release. Build any shipped dictionary exclusively from pre-1976 public-domain texts, Project Ben-Yehuda, or Wikipedia/Wiktionary frequency lists.  
   * **Mitigation 2 (Single-Line Horizon):** Never train the OCR model on multi-line or full-paragraph crops of post-1975 protocols; restrict training inputs strictly to **single-line crops** so the model's weights can never learn cross-line or paragraph-level sequence transitions.  
   * **Mitigation 3 (Deduplication & Blank-Image Probe):** Deduplicate identical lines in the training set (since memorization in neural networks scales super-linearly with exact duplication), and run a quick sanity test before release by feeding blank/noise/salt-and-pepper line images into the trained model to verify that it outputs empty strings or gibberish rather than hallucinating memorized phrases.

### **Question 9: Verifications of Primary Citations, Quotes, and Contact Channels**

Here are the four requested verifications, confirmed directly against official primary sources:

#### **1\. Ministry of Justice Opinion on Machine Learning (Exact Title, Date, and URLs)**

* **Exact Hebrew Title:** חוות דעת: שימושים בתכנים מוגנים בזכויות יוצרים לצורך למידת מכונה  
* **Issuing Body:** Ministry of Justice — Counseling and Legislation Department (Civil Law Cluster) (משרד המשפטים – ייעוץ וחקיקה, המחלקה למשפט אזרחי)  
* **Publication Date:** **December 18, 2022** (18.12.2022; page metadata last updated 11.05.2025)  
* **Official Landing Page URL:** [Ministry of Justice Opinion Page (gov.il)](https://www.gov.il/he/pages/machine-learning)  
* **Official Full PDF URL:** [Ministry of Justice Full Opinion PDF (gov.il)](https://www.gov.il/BlobFolder/legalinfo/machine-learning/he/machine-learning.pdf)

#### **2\. Current Wording and Date of the Knesset Website Terms of Use (termsofuse.aspx)**

* **Official URL:** [Knesset Website Terms of Use (termsofuse.aspx)](https://main.knesset.gov.il/About/pages/termsofuse.aspx)  
* **Date Status:** The Knesset's termsofuse.aspx page does not display a visible "Last Updated" timestamp in its body text. However, the Knesset updated the structure of this page from its older unnumbered prose format to a numbered clause format (1.1 through 8.2), while keeping the substantive copyright rules intact.  
* **Current Verbatim Wording (Section 4 — Intellectual Property and Copyright, and Section 6 — Photographs):קניין רוחני וזכות יוצרים**  
  4.1 כל התכנים באתר, לרבות טקסטים, תמונות, סמלים, ועיצובים המופיעים באתר, הם קניינה של הכנסת או של צדדים שלישיים אשר העניקו לכנסת זכות שימוש בהם, ומוגנים על ידי דיני זכויות יוצרים של מדינת ישראל ואמנות בינלאומיות. 4\.**2** חל איסור על העתקה, הפצה, פרסום או ביצוע פעולה אחרת בתכנים האמורים ללא אישור מראש ובכתב מהכנסת.  
  **4.3** זכויות היוצרים בפרסומי הכנסת, כולל אלו המתפרסמים באתר זה, שייכות לכנסת. זכויות יוצרים אלו חולשות, בין השאר, על טקסט, תמונות, איורים, מפות, קטעי צליל, קטעי וידיאו, גרפיקה ויישומי תוכנה (להלן: החומר המוגן), אלא אם כן צוין באופן מפורש כי זכויות היוצרים בחומר המוגן שייכות לגורם אחר.  
  *(Followed by the fair-use / quotation clause)*: המשתמש רשאי לעשות "שימוש הוגן" בחומר המוגן, לפי הכללים הקבועים בדין, וכן ציטוט מתוך החומר המוגן באופן סביר...

#### **3\. Verification of Section 78(a)–(j) of the Copyright Act, 2007 (Transitional Provisions)**

* **Official / Primary Text URLs:** [Wikisource — Copyright Act, 2007](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D); [Full Consolidated Statute Text (israel-law.co)](https://israel-law.co/%D7%AA%D7%97%D7%95%D7%9E%D7%99-%D7%A2%D7%99%D7%A1%D7%95%D7%A7/%D7%97%D7%A7%D7%99%D7%A7%D7%94/%D7%97%D7%95%D7%A7-%D7%96%D7%9B%D7%95%D7%99%D7%95%D7%AA-%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D/).  
* **Confirmation:** I confirm that **none of subsections 78(b) through 78(j)** preserves Section 18 of the 1911 Act ("50 years from first publication") for State works. Here is the complete breakdown of what each subsection of Section 78 covers:  
  * **§ 78(a) (General Retroactive Application):** *"הוראות חוק זה יחולו גם לגבי יצירה שנוצרה לפני יום התחילה, בכפוף להוראות סעיפים קטנים (ב) עד (י)."* (Applies the 2007 Act—including § 42's "50 years from creation" rule—to all pre-May 25, 2008 works, subject only to (b)–(j)).  
  * **§ 78(b) (No Revival of Expired Rights):** A work that was not protected immediately prior to May 25, 2008 is not revived by the new Act.  
  * **§ 78(c) (Pre-Commencement Infringing Acts):** Acts committed before May 25, 2008 are governed by the old law regarding infringement and remedies.  
  * **§ 78(d) (Copies Lawfully Made Before Commencement):** Copies lawfully made under the old law before May 25, 2008 may continue to be used.  
  * **§ 78(e) (Pre-Commencement Contracts & Assignments):** Ownership transfers and contracts made before May 25, 2008 remain valid.  
  * **§ 78(f) & (g) (Reversionary Interest under Section 5(2) of the 1911 Act):** Transitional rules for the 25-year post-mortem reversionary proviso in Section 5(2) of the 1911 Act.  
  * **§ 78(h) (Sound Recordings):** Section 41 of the 2007 Act does not apply to sound recordings created before May 25, 2008\.  
  * **§ 78(i) (Photographs):** For photographs created before May 25, 2008, the old law continues to govern authorship and term (50 years from creation of the negative under Section 21 of the 1911 Act).  
  * **§ 78(j) (Typefaces / Fonts):** For fonts (*גופנים*), the 2007 Act applies only to fonts published on or after May 25, 2008\.  
  * **Result:** Because State works (*יצירות המדינה*, §§ 36, 42\) are omitted from the exceptions in §§ 78(b)–(j), **§ 78(a) governs**, and every pre-2008 State work expires **50 years from the end of the year of its creation**.

#### **4\. Official Contact Channels for the Legal Adviser to the Knesset (Confirmed on knesset.gov.il)**

*(Correction to my previous draft: Do **not** use lishka-mishpatit@knesset.gov.il; use the official addresses published on the Knesset Legal Department's contact page below).*

* **Official Contact Page URL:** [Knesset Legal Department — Contact Us (ldcontact.aspx)](https://main.knesset.gov.il/About/Departments/pages/leg/ldcontact.aspx)  
* **Verified Official Email Addresses & Phone Numbers on that Page:**  
  1. **Public Inquiries on Legal Matters Concerning the Knesset and the Knesset Legal Department** (*"לפניות ציבור בעניינים משפטיים הנוגעים לכנסת, לעבודת הכנסת ולעבודת הייעוץ המשפטי בכנסת"*):  
     * **Email:** mishpatit@knesset.gov.il  
  2. **Secretariat of the Knesset Legal Department** (*"מזכירות הלשכה המשפטית"*):  
     * **Email:** hdept@knesset.gov.il \| **Tel:** 02-6408809 / 02-6408636 \| **Fax:** 02-6496802  
  3. **Legal Advice to the Knesset Administration** (*"הייעוץ המשפטי למינהל הכנסת"*, which handles Knesset contracts, website terms, and administrative property) ([ldadvice.aspx](https://main.knesset.gov.il/About/Departments/pages/leg/ldadvice.aspx)):  
     * **Email:** minhal.law@knesset.gov.il \| **Tel:** 02-6408604  
  4. **National Legislation Database Team** (*"מאגר החקיקה הלאומי"*, within the Knesset Legal Department) ([ldlaw.aspx](https://main.knesset.gov.il/About/Departments/pages/leg/ldlaw.aspx)):  
     * **Email:** Legislation@knesset.gov.il \| **Tel:** 02-6408489

## **Audit of Your Adopted Decision: Is Anything Wrong or Riskier Than You Assume?**

Your three-part decision for committee protocols—(1) training and releasing Apache-2.0 weights on all three periods, (2) publishing CC0 / CC BY-SA line crops only for Period 1 (up to December 31, 1975, rolling forward every January 1), and (3) not publishing single-word or glyph crops from post-1975 protocols—is **exceptionally sound and conservative**. By dropping single-word/glyph crops from post-1975 protocols, you completely eliminate any debate over where the *de minimis* / "substantial part" boundary lies under Section 11\.  
However, there are **two subtle edge cases** in your decision (and its extension to bills) where the risk is slightly higher than a simple date check assumes:

> 1. **The Pre-1976 Third-Party Speaker / Outside-Drafter Trap (Applies to Activity B in Period 1):**  
   * Even in a **pre-1976** committee protocol or a **pre-1976** Private Member's Bill, the 50-year clock in Section 42 applies **only to works created or commissioned by the State or by a State employee/MK in the course of their duties** (Section 36).  
   * If a private citizen, university professor, or NGO representative testified at length in a 1974 committee hearing (or submitted a written memorandum appended to the 1974 protocol) and died in, say, 1990, their private copyright lasts until **December 31, 2060** (70 years *post mortem auctoris* under Section 38).  
   * **Simple Fix for Period 1 Activity B:** Since you are already screening out private individuals from committee protocols for privacy reasons, ensure your Period 1 filter keeps **only lines spoken by the Committee Chair, MKs, Ministers, civil servants, or Knesset staff** (and for pre-1976 bills, prefer Government Bills and Committee Bills over Private Members' Bills unless MK authorship is clear). That guarantees 100% of your Period 1 line crops fall under expired Section 36 State copyright.  
> 2. **An Easy Win You Might Be Leaving on the Table for Post-1975 Bills (Activity B):**  
   * While you should exclude post-1975 **Explanatory Notes (*דברי הסבר*)** from Activity B (public dataset release) because they are prose commentaries protected by 50-year State copyright, any **statutory clause in a post-1975 bill that was subsequently enacted verbatim into law** is exempt under Section 6 (*"חוקים"*). Even simpler: if you want post-1975 legislative typography for your public CC0 dataset without the hassle of diffing bills against enacted laws, **use scans of *Sefer HaChukim* (enacted laws), *Kovetz HaTakanot* (regulations), and plenary *Divrei HaKnesset* from 1976–present**—all three share the exact same *Reshumot* / Knesset fonts and layouts as bills and committee protocols, and all three are **100% exempt from copyright on day one under the plain text of Section 6**.