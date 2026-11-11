# Copyright in Knesset committee protocols (and bills), 1976 onward: legal-risk analysis (received 2026-11-11)

> **Status: adopted in part.** On 2026-11-11 the maintainer (Shay Palachy Affek) based a decision on this analysis. The decision record is `planning/decisions/2026-11-11-knesset-protocols-training-vs-release.md`.
>
> **Provenance.**
> - The text below is Google Gemini's answer to the prompt in `docs/legal/2026-11-11_knesset_protocols_prompt.md`.
> - It is copied verbatim, sha256 `7c93b64d2a3f5b7deacfda00b7ed23efda4a53c828d248e123b4d80995688b98` of the received file. Typos and formatting are kept as received.
> - It is a legal-risk analysis, not legal advice. Its case and statute citations, names and email addresses have not been independently verified.
> - Before any citation is quoted in a public NOTICE, or any address is written to, check it against the primary source.
> - The analysis covers committee protocols. It does not separately analyse bills (הצעות חוק), which the prompt also asked about.

---

## **1\. Deliverable 1: Short Answer & Confidence Levels**

Whether HeOCR may copy, process, and publicly release Knesset committee protocols (*פרוטוקולים של ועדות הכנסת*) depends on a critical distinction between **(A) training OCR models and releasing Apache-2.0 weights** versus **(B) republishing the underlying line-image crops and transcriptions under CC0 or CC BY-SA**, as well as the **period in which the protocol was created**.

| Period | Activity A: Training OCR Models & Releasing Apache-2.0 Weights | Activity B: Publishing Line Crops & Transcriptions as a CC0 / CC BY-SA Dataset |
| :---- | :---- | :---- |
| **1\. Up to December 31, 1975** *(and 1976 protocols starting Jan 1, 2027\)* | **YES** *(Confidence: High — 95%)* | **YES** (for Knesset/state content and mechanical transcripts; exclude attached third-party private documents where author died less than 70 years ago) *(Confidence: High — 90%)* |
| **2\. January 1, 1976 – May 24, 2008** *(Pre-2007 Act effective date)* | **YES** (via Section 19 Fair Use & 2022 MoJ AI Opinion) *(Confidence: High — 90%)* | **UNCERTAIN / NO without permission** (unless a court construes *"דברי הכנסת"* in Section 6 broadly or holds verbatim stenography unoriginal; narrow workarounds exist) *(Confidence: Medium-High — 80% that ambiguity blocks strict CC0/CC BY-SA rules)* |
| **3\. May 25, 2008 – Present** *(Under the Copyright Act, 2007\)* | **YES** (via Section 19 Fair Use & 2022 MoJ AI Opinion) *(Confidence: High — 90%)* | **UNCERTAIN / NO without permission** (Knesset website Terms of Use assert copyright over site text; Section 6's scope over committee protocols is untested in court) *(Confidence: High — 85% that Knesset's formal position currently conflicts with unlicensed CC0 release)* |

**Core Takeaway:**

* **For training OCR models and releasing Apache-2.0 weights:** You may use committee protocols from **all three periods** (including 1976–present). Even if post-1975 committee protocols are protected by State copyright, non-expressive ingestion to train OCR weights falls within Israel's Fair Use doctrine (Section 19 of the Copyright Act, 2007 and the Israeli Ministry of Justice's December 2022 Legal Opinion on Machine Learning).  
* **For releasing a CC0 or CC BY-SA dataset of line crops and transcriptions from 1976 onward:** You face an unresolved statutory ambiguity in **Section 6 of the Copyright Act, 2007**. In formal Israeli parliamentary nomenclature, *"דברי הכנסת"* (*Divrei HaKnesset*) is the technical statutory title of the **plenary** record, distinct from *"פרוטוקולים של דיוני הוועדות"* (committee protocols). Furthermore, the Knesset's website Terms of Use explicitly claim copyright in all text on the site unless stated otherwise, permitting only "fair use" and reasonable quotation with attribution. Under HeOCR's strict rule against releasing datasets whose upstream terms cast doubt on downstream commercial reuse, **you should not release post-1975 committee line crops under CC0/CC BY-SA without either (a) a written clarification/waiver from the Knesset, or (b) relying on a synthetic/cropped single-word or character-level approach that does not reproduce expressive speech.** (Note: **1976** protocols enter the public domain in seven weeks, on **January 1, 2027**).

## **2\. Deliverable 2: Detailed Legal Reasoning (Section by Section)**

### **A. Section 6 of the Copyright Act, 2007: Does "דברי הכנסת" Include Committee Protocols?**

#### **1\. Statutory Text and Legislative History**

Section 6 of the Copyright Act, 2007 ([Sefer HaChukim 2119](https://fs.knesset.gov.il/17/law/17_lsr_300007.pdf); [Wikisource text](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D)), titled *"פרסומים רשמיים"* (Official Publications), provides:  
**"על אף הוראות סעיף 4, לא תהא זכות יוצרים בחוקים, בתקנות, בדברי הכנסת ובהחלטות שיפוטיות של בית משפט או של כל רשות שלטונית המפעילה סמכות שפיטה על פי דין."**  
*(Notwithstanding the provisions of Section 4, there shall be no copyright in laws, regulations, Divrei HaKnesset \[Knesset proceedings\], and judicial decisions of a court or of any governmental authority exercising adjudicative power by law.)*  
In the predecessor draft—Section 5 of the [2003 Ministry of Justice Copyright Bill Memorandum (*תזכיר חוק זכות יוצרים, התשס"ד-2003*)](https://www.psakdin.co.il/kannex/nws_ndis_1.pdf) and Section 6 of the 2005 Government Bill (*הצעת חוק זכות יוצרים, התשס"ה-2005*, ה"ח הממשלה 196, מיום 20.7.2005)—the Explanatory Notes (*דברי הסבר*) stated that the exclusion of laws, regulations, *Divrei HaKnesset*, and judicial decisions is grounded in the recognition that *"מסמכים אלה נועדו להפצה לציבור"* ("these documents are intended for dissemination to the public") and rest on fundamental democratic principles of free public access to the law and the workings of the legislature and judiciary.

#### **2\. The Textual Problem: Formal vs. Purposive Interpretation of "דברי הכנסת"**

There is no published Israeli Supreme Court or District Court ruling directly deciding whether *"דברי הכנסת"* in Section 6 encompasses Knesset committee protocols. Two competing interpretations exist:

* **The Formal / Narrow Reading (Your Working Assumption):** Within the Knesset's own statutory framework and administrative structure, *"דברי הכנסת"* is a term of art referring specifically to the official stenographic record of **Knesset plenary sittings** (*ישיבות המליאה*).  
  * The Knesset maintains a specific department called *"מערכת דברי הכנסת"* (*Divrei HaKnesset* Editorial Department) responsible for editing the plenary transcripts.  
  * On the Knesset website and in the Knesset Rules of Procedure (*תקנון הכנסת*), plenary records are titled *"דברי הכנסת"*, whereas committee transcripts are separately categorized as *"פרוטוקולים של דיוני הוועדות"* (Protocols of Committee Deliberations).  
  * Similarly, Israel's Uniform Legal Citation Rules (*כללי האזכור האחיד בכתיבה משפטית*) distinguish between citing *"דברי הכנסת"* (plenary) and citing *"פרוטוקול ישיבה מס' ... של ועדת ..."* (committee protocols).  
  * Because Section 6 is drafted as a closed list of specific official publications (unlike Section 36, which broadly covers all other State works), a strict textualist reading holds that anything outside the four enumerated items falls back into Section 36 (50-year State copyright).  
* **The Purposive (*תכליתית*) Reading:** Israeli copyright scholars (such as Tony Greenman in *זכויות יוצרים* and Prof. Michael Birnhack) note that the rationale of Section 6—democratic transparency, citizens' right to know how laws are enacted, and the absence of any need for economic copyright incentives to induce parliamentary deliberation—applies with equal force to public committee protocols, which are the primary source of legislative history in Israel. Moreover, Section 21 of the Copyright Act, 2007 ([Wikisource](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D)) separately permits copying works deposited for public inspection under an enactment (*"העתקה של יצירה המופקדת לעיון הציבור לפי חיקוק, מותרת למטרה שלשמה הועמדה לעיון הציבור, ובהיקף המוצדק בשים לב למטרה זו"*).  
* **Why You Cannot Rely on the Purposive Reading Alone for a CC0 Dataset:** Even under Section 21, copying is permitted only *"for the purpose for which it was made available for public inspection, and to the extent justified having regard to that purpose"*—not necessarily for bulk commercial redistribution as an OCR training dataset under CC0. Because the narrow reading of *"דברי הכנסת"* is textually grounded in Knesset terminology and backed by the Knesset's website Terms of Use, treating post-1975 committee protocols as potentially outside Section 6 is the legally prudent assumption.

### **B. State Copyright (Section 36), Term (Sections 42–43), and Transitional Law (Section 78 & 1911 Act)**

If committee protocols are not exempt under Section 6, they fall under Chapter E of the Copyright Act, 2007:

#### **1\. Ownership of State Works (Section 36\)**

Section 36 of the Copyright Act, 2007 ([Wikisource](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D)) states:  
**"המדינה היא הבעלים הראשון של זכות היוצרים ביצירה שנוצרה או שהוזמנה על ידה או על ידי עובד המדינה עקב עבודתו ובמהלכה, אלא אם כן הוסכם אחרת; לעניין זה, 'עובד המדינה' – לרבות חייל, שוטר, וכל נושא משרה או בעל תפקיד על פי חיקוק במוסד ממוסדות המדינה."**  
*(The State is the first owner of copyright in a work created or commissioned by it or by a State employee in consequence of and during the course of their employment, unless agreed otherwise; for this purpose, "State employee" includes a soldier, police officer, and any officeholder or functionary under an enactment in an institution of the State.)*  
The Knesset is undoubtedly an "institution of the State" (*מוסד ממוסדות המדינה*), and Knesset employees and Members of Knesset are officeholders/functionaries under an enactment (*בעל תפקיד על פי חיקוק*).

#### **2\. Term of Protection and the Exact Year Boundary (Sections 42 and 43\)**

* **Section 42 (*תקופת זכות יוצרים ביצירה של המדינה*):"זכות יוצרים ביצירה שהמדינה היא הבעלים הראשון של זכות היוצרים בה לפי הוראות פרק ה', תהא לתקופה של חמישים שנים ממועד יצירתה."**  
  *(Copyright in a work of which the State is the first owner of copyright under Chapter E shall last for a period of fifty years from the date of its creation.)*  
* **Section 43 (*סיום תקופת זכות יוצרים*):"תקופת זכות היוצרים ביצירה תסתיים ב־31 בדצמבר של השנה שבמהלכה אמורה לפקוע הזכות לפי הוראות פרק זה."**  
  *(The period of copyright in a work shall end on December 31 of the year during which the right is due to expire under the provisions of this Chapter.)*

**Testing Your Year Boundary (as of November 11, 2026):**

* For a protocol created at any time in **1975**: 50 years from creation fell in 2025, and copyright expired on **December 31, 2025**. Thus, all protocols created up to **December 31, 1975** are in the public domain today.  
* For a protocol created in **1976**: 50 years from creation falls in 2026, and copyright expires on **December 31, 2026** (less than two months from today). On **January 1, 2027**, the entire 1976 cohort enters the public domain.

#### **3\. Does the Predecessor Law (1911 Act, Section 18\) or Transitional Provision (Section 78\) Change the 1975/1976 Boundary?**

This is a subtle and important point where the predecessor law differed from the 2007 Act:

* **Under Section 18 of the British Mandate Copyright Act, 1911** ([Wikisource](https://he.wikisource.org/wiki/%D7%97%D7%95%D7%A7_%D7%96%D7%9B%D7%95%D7%AA_%D7%99%D7%95%D7%A6%D7%A8%D7%99%D7%9D,_1911); [TGLaw text](https://www.tglaw.co.il/index.php?dir=site&page=content&cs=65)):*"בלא לפגוע בכל זכויות או בזכויות המיוחדות של הכתר הרי אם הוכנה או נתפרסמה איזו יצירה ע"י הוד מלכותו או ע"י כל מחלקה ממשלתית או עפ"י הוראתם או בפיקוחם, בין לפני תאריך חוק זה ובין לאחריו, תהא זכות-היוצרים ביצירה שייכת להוד מלכותו, בהתחשב עם כל הסכם שייעשה עם המחבר, ובענין זה תהא זכות-היוצרים קיימת למשך **חמישים שנה מעת הפרסום הראשון של היצירה**."*  
  Notice the difference: Section 18 of the 1911 Act measured the 50-year term from **first publication** (*מעת הפרסום הראשון*), whereas Section 42 of the 2007 Act measures 50 years from **creation** (*ממועד יצירתה*). Many pre-2000 Knesset committee protocols sat typed in the Knesset Archives for decades and were only "published" to the general public when uploaded to the Knesset website in the 2000s or 2010s.  
* **How Section 78 of the 2007 Act Resolves This in Your Favor:** Under **Section 78(a)** of the Copyright Act, 2007 ([TGLaw text](https://www.tglaw.co.il/index.php?dir=site&page=content&cs=54)):**"(א) הוראות חוק זה יחולו גם לגבי יצירה שנוצרה לפני יום התחילה, בכפוף להוראות סעיפים קטנים (ב) עד (י)."**  
  *(The provisions of this Law shall also apply to a work created before the commencement date \[May 25, 2008\], subject to subsections (b) through (j).)*  
  Subsections 78(b) through (j) contain specific transitional exceptions—for example, Section 78(b) ensures a work already in the public domain before May 25, 2008 is not revived, and Section 78(i) preserves the 50-year term for pre-2008 photographs. Crucially, **Section 78 contains no exception preserving the 1911 Act's "50 years from publication" rule for State works.** Therefore, by virtue of Section 78(a), **Section 42's rule ("50 years from creation") applies retroactively to all pre-2008 State works.** Even if a 1975 committee protocol was only scanned and published on the Knesset website in 2018, its State copyright expired 50 years after creation—on December 31, 2025\.

### **C. Authorship, Outsourced Transcription Contractors, and Third-Party Speakers**

A Knesset committee protocol involves three potential layers of authorship: (1) the stenographer or external transcription contractor; (2) Members of Knesset and state officials speaking in the committee; and (3) private citizens, academics, or lobbyists testifying before the committee or submitting documents.

#### **Layer 1: The Stenographer / Outsourced Transcription Contractor**

> 1. **No Originality in Verbatim Stenography:** Under Section 4(a)(1) of the 2007 Act and the Supreme Court's landmark ruling in **CA 513/89 *Interlego A/S v. Exin-Lines Bros. S.A.*, PD 48(4) 133 (1994)**, copyright requires minimal creative expression; mechanical skill, speed, effort, and "sweat of the brow" do not confer copyright. A stenographer or court/committee transcriber whose duty is to record oral statements verbatim—without adding independent literary expression—is not the "author" of an original literary work (analogous to the House of Lords decision in *Walter v. Lane* \[1900\] AC 539, which Israeli scholars note does not survive modern originality requirements under *Interlego*).  
> 2. **Outsourced Contractors Are Covered by Section 36 Anyway:** You asked whether it matters that the Knesset outsourced committee transcription to private contractors (such as Yifat or other transcription firms). **It does not change the ownership analysis.** Unlike ordinary commissioned works under Section 35(a) (where copyright defaults to the contractor unless agreed otherwise), **Section 36** explicitly vests first ownership in the State for any work *"שנוצרה **או שהוזמנה** על ידה"* ("created **or commissioned** by it") unless agreed otherwise. Even under the pre-2008 regime (Section 18 of the 1911 Act), Crown/State copyright vested in any work prepared *"על פי הוראתם או בפיקוחם"* ("under the direction or control of His Majesty or any Government department"). Moreover, standard Knesset procurement contracts for transcription services assign all intellectual property rights to the Knesset. Thus, no transcription contractor holds copyright in Knesset protocols.

#### **Layer 2: Members of Knesset and State Employees Speaking in Committee**

When an MK or civil servant speaks in a committee meeting, their speech is fixed in writing simultaneously by the Knesset's stenographer (satisfying the fixation requirement of Section 4(a)(1)). Because MKs and civil servants speak *"עקב עבודתו ובמהלכה"* (in consequence of and during the course of their official duties as officeholders in a State institution), any copyright in their oral remarks belongs to the State under **Section 36** and expires 50 years after creation under **Section 42**.

#### **Layer 3: Third-Party Witnesses, Experts, and Private Speakers (The Hidden Trap)**

This is a genuine legal nuance that your screening pipeline must account for:

* **Prepared Written Statements, Position Papers, and Quoted Documents:** If an academic, NGO representative, or private citizen reads a prepared text or submits a written document/letter that is appended to or quoted at length in the protocol, that person (or their employer) owns a private copyright in that work under Section 33, lasting for the **life of the author plus 70 years** (Section 38)—**not** 50 years from creation\!  
* **Extemporaneous Oral Testimony by Private Citizens:** Does a spontaneous oral answer by a witness in a committee hearing attract private copyright (life \+ 70 years)?  
  * *Unoriginal short remarks:* Short factual answers, interruptions, or routine dialogue lack sufficient literary originality under Section 4(a).  
  * *Extended structured testimony:* A lengthy, structured oral presentation by an outside expert could cross the originality threshold of a "lecture" or literary work once fixed in the transcript. (Israeli law has not definitively decided whether fixation under Section 4(a)(1) must be performed by or under the authority of the speaker, as required in the U.S. under 17 U.S.C. § 101, though appearing at a public committee hearing known to be transcribed implies consent to fixation).  
  * *Statutory Exceptions (Sections 20 & 21):* While the Knesset itself is clearly authorized to record and publish witness statements (and Section 20 permits use in administrative/legislative proceedings, while Section 21 permits copying works deposited for public inspection by law), neither Section 20 nor Section 21 gives a downstream dataset publisher a blanket CC0 license to commercially redistribute a third party's lengthy copyrighted testimony.  
  * **Impact on Your Pipeline:** Because HeOCR crops **individual text lines** (typically 5 to 12 words per line), an isolated single-line crop from an oral statement will almost never constitute a "substantial part" (*חלק מהותי* under Section 11\) of a third party's speech, **provided you shuffle or sample lines rather than releasing contiguous multi-page blocks of a private witness's testimony.**

### **D. The Knesset's Own Position, Website Terms of Use, Statutory Rules, and Open Data**

> 1. **The Knesset Website Terms of Use (termsofuse.aspx):** On the official [Knesset Terms of Use page](https://main.knesset.gov.il/About/pages/termsofuse.aspx), under the heading *"קניין רוחני וזכות יוצרים"* (Intellectual Property and Copyright), the Knesset states:  
   * All copyrights in the site's content belong to the State of Israel / the Knesset, covering *"טקסט, תמונות, איורים, מפות, קטעי צליל, קטעי וידיאו, גרפיקה ויישומי תוכנה (להלן: החומר המוגן), אלא אם כן צוין באופן מפורש כי זכויות היוצרים בחומר המוגן שייכות לגורם אחר"* ("text, images, illustrations, maps, sound clips, video clips, graphics, and software applications (hereinafter: the Protected Material), unless explicitly stated that copyright belongs to another party").  
   * Regarding permitted use, the Terms state: *"המשתמש רשאי לעשות 'שימוש הוגן' בחומר המוגן, לפי הכללים הקבועים בדין, וכן ציטוט מתוך החומר המוגן באופן סביר. המצטט כאמור חייב על פי דין לציין כי מקור המידע הוא מאתר הכנסת. כמו כן, אסור למשתמש לעשות בחומר המוגן כל סילוף, פגימה או שינוי אחר..."* ("The user may make 'fair use' of the Protected Material, according to the rules set by law, as well as quote from the Protected Material in a reasonable manner. One who quotes as aforesaid is obligated by law to state that the source of the information is the Knesset website...").  
   * Notice that the Knesset's Terms of Use **do not carve out committee protocols as public domain under Section 6**, nor do they apply a CC0 or CC-BY license to website text.  
> 2. **Knesset Rules of Procedure (*תקנון הכנסת*) and Mandatory Publication:** Under the Knesset Rules of Procedure (Part C — Committees), committee meetings are open to the public by default (unless the committee votes to hold a classified/closed session), and protocols of open committee meetings are published on the Knesset website. However, under Israeli law, the fact that a document is created and published pursuant to a statutory or procedural duty does **not** automatically strip it of State copyright under Section 36 unless it falls within the four categories of Section 6 (or is used within the bounds of Section 21's public-inspection exception).  
> 3. **Knesset Open Data (OData API) vs. Executive Branch Open Data (data.gov.il):**  
   * The Israeli Government (Executive Branch) adopted Government Resolution 1933 (2016) and ICT Authority (*מערך הדיגיטל הלאומי*) guidelines releasing datasets on data.gov.il under an open license (similar to CC-BY).  
   * **Does this bind the Knesset?** **No.** Under Israel's constitutional separation of powers (*חוק-יסוד: הכנסת* and *חוק הכנסת, התשנ"ד-1994*), the Knesset is the legislative authority, administratively independent of the Government (the executive branch). Government Resolutions bind government ministries, not the Knesset.  
   * While the Knesset operates an exemplary public OData API (KNS\_CommitteeSession, providing metadata and links to .doc/.pdf protocol files) and cooperates closely with civic-tech projects like *Open Knesset* (*כנסת פתוחה*, run by HaSadna L'Yeda Tziburi), the Knesset has done so through informal administrative cooperation and API access rather than by publishing a formal CC0 or CC-BY waiver over post-1975 protocol texts.

### **E. Comparative Law Context & Privacy Considerations**

* **Comparative Law (UK and US):**  
  * **United Kingdom:** Under the Copyright, Designs and Patents Act 1988 (s. 165), bills and parliamentary proceedings (including Select Committee transcripts and *Hansard*) are subject to **Parliamentary Copyright** (distinct from Crown Copyright), lasting 50 years from the end of the calendar year in which the work was made. However, to enable open reuse, the UK Parliament proactively releases *Hansard* and non-confidential committee transcripts under the **Open Parliament Licence (OPL)**, which is equivalent to CC-BY 3.0 and expressly allows commercial and non-commercial reuse. Israel modeled its 1911/2007 50-year State copyright term on the UK tradition, but the Knesset has not yet adopted a formal equivalent to the UK's Open Parliament Licence.  
  * **United States:** Under **17 U.S.C. § 105**, works of the U.S. Government (including Congressional committee hearings printed by the GPO) are entirely in the public domain from creation. Israeli courts and the drafters of the 2007 Act explicitly considered the U.S. § 105 model during the drafting of the 2003–2007 bill, adopting the U.S. rule **only** for the four categories in Section 6 while retaining the UK 50-year State copyright model in Sections 36 and 42 for all other official works.  
* **Privacy Law (*חוק הגנת הפרטיות, התשמ"א-1981*, including Amendment 13):**  
  * Does privacy law alter the **copyright** analysis? **No.** Privacy and copyright are orthogonal legal regimes.  
  * Does privacy law create an independent risk if you publish line crops containing sensitive personal data of private citizens who testified in committees (e.g., regarding health, welfare, disability, debt, or minors)? **Yes.** While open committee protocols are lawfully published by the Knesset, compiling and redistributing searchable datasets of identifiable private individuals' sensitive personal data can trigger obligations under the Protection of Privacy Law (especially after Amendment 13, enacted in August 2024). Your existing plan to screen and exclude protocols/lines containing private individuals' names or personal testimony is therefore essential for privacy compliance—and has the added copyright benefit of eliminating third-party private speakers\!

### **F. Fair Use (Section 19): Model Training vs. Dataset Publication**

* **Training OCR Models and Releasing Apache-2.0 Weights:**Under Section 19 of the Copyright Act, 2007 and the **Ministry of Justice Legal Opinion of December 18, 2022** (*שימוש בתכנים מוגנים בזכויות יוצרים לצורך למידת מכונה*), copying copyrighted works to extract non-expressive statistical patterns (such as pixel-to-character mappings in an OCR model) is a transformative Fair Use. Because the trained Apache-2.0 weights do not contain or reproduce the expressive text of the Knesset protocols, **training on post-1975 protocols and releasing the weights under Apache-2.0 is lawful.**  
* **Releasing the Line-Crop Dataset under CC0 or CC BY-SA:** Fair Use under Section 19 is an affirmative defense evaluated case-by-case based on the user's specific purpose (research, self-study, etc.). **Fair Use does not convert a copyrighted work into the public domain (CC0), nor does it empower a user to re-license a copyrighted work to the world under CC BY-SA for arbitrary commercial republication.** Therefore, Section 19 cannot make a public CC0/CC BY-SA release of copyrighted full-sentence or multi-line protocol excerpts clean unless the excerpts are either (1) in the public domain (pre-1976, or covered by Section 6), (2) licensed by the Knesset, or (3) reduced to de-contextualized single words or character glyphs that are too short to contain copyrightable expression.

## **3\. Deliverable 3: The Practical Risk Picture**

If HeOCR were to publish line crops of post-1975 Knesset committee protocols without explicit permission, who could realistically object and what would happen?

| Potential Objector | Legal Standing / Plausible Claim | Likelihood of Objection | Realistic Consequence for HeOCR |
| :---- | :---- | :---- | :---- |
| **1\. The Knesset** (via Knesset Legal Adviser / Website Administration) | Breach of Knesset Website Terms of Use; infringement of State copyright under Section 36 (arguing Section 6 covers only plenary *Divrei HaKnesset*). | **Low** (The Knesset has tolerated *Open Knesset* mirroring all committee protocols for 15+ years, though *Open Knesset* is civic transparency rather than a CC0 commercial dataset). | A polite administrative request or cease-and-desist letter asking you to remove post-1975 committee crops from Hugging Face/Zenodo or change the license. Almost zero chance of a lawsuit for statutory damages against an Israeli open-source project. |
| **2\. The State / Ministry of Justice** | First owner of State copyright under Section 36\. | **Negligible** (MoJ generally favors open access to parliamentary materials and authored the pro-ML 2022 Fair Use opinion). | None independently of the Knesset. |
| **3\. Outsourced Transcription Contractors** | None. Section 36 vests commissioned works in the State, and verbatim stenography lacks originality. | **Zero / Frivolous** | No valid legal claim. |
| **4\. Private Speakers / Witnesses** | Copyright in lengthy prepared oral testimony or submitted written papers (life \+ 70 years under Section 38); privacy or moral rights claims. | **Low** (if single lines are cropped and private individuals are screened out); **Medium** (if full pages or contiguous paragraphs of private citizens' testimony are published). | Takedown request for specific lines/pages; eliminated if you screen out private witnesses and only use single disconnected lines. |

## **4\. Deliverable 4: Narrowest Paths to Permission (Technical & Institutional)**

Because your project policy requires that *"no input may enter the training pipeline if its terms would later cast doubt on releasing the derived data or models openly, including for commercial use,"* you have **three concrete paths** for 1976–present protocols:

### **Path 1 (Immediate, Zero-Dependency Technical Path): Pre-1976 Full Lines \+ Post-1975 Single-Word / Glyph Crops**

* **For protocols up to December 31, 1975 (and 1976 protocols starting January 1, 2027):** Release full line crops and transcriptions under **CC0**, screening out any attached third-party documents.  
* **For protocols from 1977 onward:**  
  1. Use the full line crops **internally** to train your Apache-2.0 OCR models (completely lawful under Section 19 Fair Use and the 2022 MoJ AI Opinion).  
  2. In your **publicly released CC0 dataset**, instead of releasing full sentence/line crops from post-1976 protocols, release **isolated word crops (1–2 words) or character/glyph crops** shuffled out of sentence order. Under Israeli copyright law, isolated single words and short 2-word lexical fragments contain **zero original literary expression** under Section 4(a) and cannot constitute a "substantial part" (*חלק מהותי*, Section 11\) of any speech, while still providing high-value real-world visual training data for OCR\!

### **Path 2 (Institutional Path): Request Written Clarification / Open-Data Waiver from the Knesset**

To release full line crops (or full pages) of 1976–present committee protocols under CC0 or CC-BY, write directly to:

> 1. **The Legal Adviser to the Knesset (*היועצת המשפטית לכנסת*, Adv. Sagit Afik)** — lishka-mishpatit@knesset.gov.il  
> 2. **The Knesset Archives & Knesset Open Data / Digital Team (*ארכיון הכנסת / צוות אתר הכנסת*)** — archion@knesset.gov.il

**What to ask for:** Ask first for confirmation that the Knesset views open committee protocols as part of *"דברי הכנסת"* under Section 6 of the Copyright Act, 2007 (and thus free of copyright); alternatively, request written confirmation that HeOCR may publish cropped text-line images and transcriptions from open committee protocols as an open-source OCR dataset under CC0 / CC-BY.

#### **Draft Request in Hebrew**

Plaintext  
לכבוד  
עו"ד שגית אפיק, היועצת המשפטית לכנסת  
ומנהל/ת ארכיון הכנסת ומאגרי המידע הפתוחים  
כנסת ישראל, ירושלים

שלום רב,

הנדון: הבהרה משפטית / אישור לשימוש בשורות טקסט מפרוטוקולים גלויים של ועדות הכנסת לצורכי מחקר ופיתוח מערכת זיהוי כתב (OCR) עברית בקוד פתוח (פרויקט HeOCR)

אנו פונים אליכם מטעם פרויקט HeOCR – מיזם מחקרי-ציבורי בקוד פתוח (ללא מטרות רווח) המפתח מודלים ומאגרי נתונים פתוחים לזיהוי אופטי של תווים (OCR) בשפה העברית, לטובת חוקרים, ארכיונים, ספריות והציבור הרחב.

במסגרת הפרויקט, ברצוננו לשלב גזירים של שורות טקסט בודדות (Line Crops) מתוך פרוטוקולים מודפסים וגלויים של ועדות הכנסת (משנת 1976 ואילך) המפורסמים באתר הכנסת, לצד התמליל שלהן, כחלק ממאגר אימון ובדיקה פתוח לציבור (תחת רישיון פתוח מסוג CC0 או CC-BY). מובהר כי אנו מסננים מראש פרוטוקולים הכוללים פרטים אישיים או עדויות של אזרחים פרטיים, ומתמקדים בטקסטים רשמיים בלבד.

סעיף 6 לחוק זכות יוצרים, התשס"ח-2007, קובע כי "לא תהא זכות יוצרים בחוקים, בתקנות, בדברי הכנסת ובהחלטות שיפוטיות". לצד זאת, תנאי השימוש הכלליים באתר הכנסת מציינים כי זכויות היוצרים בטקסטים שבאתר שמורות לכנסת אלא אם צוין אחרת.

נודה מאוד לקבלת עמדתכם או אישורכם בכתב באחת משתי החלופות הבאות:  
1\. הבהרה כי לעמדת הכנסת, פרוטוקולים גלויים של ועדות הכנסת המפורסמים לציבור על פי דין חוסים תחת הוראת סעיף 6 לחוק זכות יוצרים, התשס"ח-2007 ("דברי הכנסת"), ולפיכך הם נחלת הכלל;  
2\. לחלופין, אישור כי אין לכנסת התנגדות לכך שפרויקט HeOCR יעשה שימוש בגזירי שורות מתוך פרוטוקולים גלויים של ועדות הכנסת לצורך פרסום מאגר נתונים פתוח (תחת רישיון CC0 או CC-BY, תוך מתן קרדיט מתאים לאתר הכנסת כמקור המידע) ואימון מודלי OCR פתוחים לציבור.

נשמח לעמוד לרשותכם לכל הבהרה נוספת, ולהעמיד את תוצרי הפרויקט גם לרשות ארכיון הכנסת לצורך שיפור הדיגיטציה וההנגשה של מסמכי הכנסת ההיסטוריים.

בכבוד רב,  
\[שם מלא\]  
מוביל פרויקט HeOCR  
\[פרטי התקשרות\]

## **5\. Deliverable 5: Audit of Your Initial Assumptions & Lawyer Sign-Off Checklist**

### **Testing Your Four Initial Assumptions**

> 1. **Assumption 1 (Section 6 & "דברי הכנסת"):** *Mostly right as a conservative risk assumption, though unsettled.* In formal Knesset parlance, *"דברי הכנסת"* refers to the plenary record while committee records are called *"פרוטוקולים של דיוני הוועדות"*. While a purposive argument exists that Section 6 should cover committee protocols, no court has ruled on it, and the Knesset's website Terms of Use claim copyright over site text.  
> 2. **Assumption 2 (Section 36, Section 42, the 1975/1976 boundary, and Section 78 transitional rules):**  
   * *Right on the 50-year term and boundary:* Under Sections 42 and 43, State copyright expires on December 31 of the 50th year from creation. Protocols through **December 31, 1975** are in the public domain now (November 2026), and **1976** protocols enter the public domain on **January 1, 2027**.  
   * *Refinement on Section 78 / 1911 Act:* You wondered whether the 1911 Act's transitional rules complicate pre-2008 protocols. In fact, Section 18 of the 1911 Act measured the 50-year term from *first publication*, which would have been dangerous for older committee protocols that were only published online in the 2000s. Fortunately, **Section 78(a) of the 2007 Act** applies the new law's "50 years from **creation**" rule (Section 42\) to all pre-2008 State works, eliminating the unpublished-protocol trap.  
> 3. **Assumption 3 (Authorship & Outsourced Transcription Contractors):** *Needs correction in your favor.* Even after the Knesset outsourced transcription to private contractors, (a) verbatim stenography lacks creative originality under Section 4(a), and (b) **Section 36** explicitly vests State copyright in works **commissioned by** (*שהוזמנה על ידה*) the State. Contractors hold no copyright in the protocols.  
> 4. **Assumption 4 (Third-Party Content — Witnesses, Experts, Attached Documents):** *Crucial catch.* Private individuals who submit written statements or deliver lengthy, original prepared testimony are **not** State employees under Section 36; any copyright in their original literary contributions lasts **life \+ 70 years** (Section 38), even in pre-1976 protocols. Screening out private speakers and avoiding contiguous multi-line blocks of witness testimony solves both this copyright issue and your privacy obligations.

### **What Still Needs a Licensed Israeli Copyright Lawyer's Sign-Off**

> 1. **Whether Section 6 ("דברי הכנסת") can be relied upon without Knesset confirmation:** If you decide you want to publish full-line crops from 1977–present committee protocols under CC0 *without* waiting for the Knesset Legal Adviser's reply, a licensed Israeli IP litigator should provide a formal written opinion on whether a court would interpret *"דברי הכנסת"* in Section 6 to include committee protocols.  
> 2. **Threshold of "Substantial Part" (*חלק מהותי*, Section 11\) for Disconnected Single-Line Crops:** If you use single-line or 1–2 word crops from post-1976 protocols without Knesset permission, counsel should sign off on the maximum token/word length per crop that safely falls below the *de minimis* / substantial-part threshold under Israeli case law.  
> 3. **Privacy Law Compliance (Amendment 13 to the Protection of Privacy Law):** Counsel should review your automated PII/speaker-filtering heuristics to ensure that no identifiable private individual's sensitive testimony enters the public dataset.