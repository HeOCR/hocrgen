# Modern Handwritten Acquisition Policy

`F3a` defines the rights-clean policy foundation for modern handwritten Hebrew intake, including contributor consent, public-use release terms, scanning/upload standards, mixed-language coverage, and typed intake manifests. F3b implements the bounded operator manifest workflow against this policy. It does not collect samples, does not add broad upload/acquisition automation, does not add a default public-profile source, and does not claim public beta readiness.

## Scope

This policy covers contributor-supplied or institutionally coordinated contemporary handwriting samples intended for possible future HeOCR public-profile use. It applies before a modern handwriting source, upload batch, or source adapter can affect `profile_open_v1`.

It does not cover:

- historical public-domain or institutionally licensed sources such as NLI, Pinkas, or BiblIA
- synthetic or generated samples from `hocrsyngen` or future synthetic providers
- broad live crawling, public upload portals, or automated acquisition
- public beta publication or release-candidate export

## Intake Boundary

Modern real handwriting must remain a distinct source family from historical public sources and synthetic data.

Historical public-source rights and synthetic-provider manifests do not satisfy modern contributor-consent requirements.

| Source family | Examples | Required boundary |
| --- | --- | --- |
| Modern real handwriting | contributor scans, coordinated classroom or volunteer writing batches | explicit contributor consent, release terms, privacy screening, and operator review before public-profile eligibility |
| Historical public sources | NLI, Pinkas, BiblIA, other archives | upstream rights/provenance evidence and existing source-adapter gates; no assumption that historical permissions apply to living contributors |
| Synthetic data | `hocrsyngen` manifest batches, future provider outputs | synthetic disclosure, provider manifest validation, caps, and synthetic-only boundaries; never substitutes for real contributor consent |

Mixed-source batches must be split into separate source ids or manifest records so each item keeps the correct rights, privacy, and review policy.

## Contributor Consent And Release Terms

Modern handwriting may be accepted only when every contributor has consented before collection.

Minimum consent requirements:

- contributor is an adult; minor participation is out of scope for F3a/F3b and must remain blocked unless a future explicit minor-participant policy is approved
- contributor understands that accepted samples may be included in an open dataset and redistributed through future HeOCR public releases
- contributor grants a broad, irrevocable public reuse license compatible with `profile_open_v1`, or the item remains blocked/review-only
- consent covers the handwriting image, any transcription prompt text written on the page, and non-sensitive metadata needed for dataset composition reporting
- consent records are retained in a private maintainer record or typed operator manifest, not exposed as public personal data
- contributors receive a takedown/removal contact path before submitting material

The preferred public-profile rights posture is project-owned or contributor-granted open reuse with attribution avoided unless attribution can be made non-identifying and release-portable. Ambiguous consent, workplace/school ownership ambiguity, third-party forms, minor-participant material, or any uncertainty about who owns the handwritten page must block public-profile use.

## Rights Provenance And Public-Profile Use

Every modern handwriting item must carry rights provenance before it can enter review:

- consent artifact id or institutional batch agreement id
- date of consent or batch agreement
- collector/operator id
- declared release terms and normalized license candidate
- confirmation that the contributor wrote the sample or was authorized to release it
- statement that the page does not copy restricted third-party text beyond approved prompts

`profile_open_v1` eligibility requires rights classification compatible with public release, clear provenance, and no unresolved rights-review issue. Unknown, restricted, expired, withdrawn, or disputed rights must remain blocked or review-only.

## Contemporary Privacy Screening

Modern handwriting is high privacy risk by default. Public-profile candidates must pass conservative contemporary privacy screening even when the rights license is open.

Operators must reject or route to private review when a page includes:

- full names, signatures, addresses, phone numbers, email addresses, identity numbers, account numbers, medical details, grades, employment details, or other personal identifiers
- sensitive religious, political, health, financial, school, workplace, immigration, or family information about a living person
- third-party personal data written by the contributor
- faces, identifiable people, location clues, or non-document background content in the scan
- private correspondence, diary-like material, or personal notes not created specifically for the dataset

Accepted writing prompts should use neutral text supplied by the project or public-domain/open text cleared for reuse. Operators should prefer pages created specifically for HeOCR rather than repurposed private documents.

## Scanning And Upload Standards

F3b requires operator-visible scan metadata and technical checks before review. Minimum standards:

- one page per image unless a multi-page record is explicitly modeled
- JPEG or PNG input that can be normalized by the existing technical QA path
- full page visible, right-side-up, uncropped text, no hands or identifying background
- no absolute local path exposure in public manifests
- stable batch id, page id, source item id, and checksum before review
- capture resolution high enough for OCR/HTR evaluation, preferably at least 300 DPI or an equivalent clear smartphone scan
- color or grayscale accepted; aggressive filters, beautification, and perspective distortion should be avoided
- prompts, page type, script style, language mix, and collection context recorded as metadata rather than inferred later

Upload implementation remains out of scope. Modern handwriting samples should enter this repository only through review-only F3b operator manifests and explicit review decisions.

## Operator Review Requirements

Modern handwriting must require manual operator review before public-profile eligibility.

Review must verify:

- consent/provenance link exists and matches the batch/item
- rights classification and normalized license are public-profile compatible
- privacy screening found no unresolved contemporary personal data
- scan quality is usable and not manipulated beyond allowed normalization
- content type, period, language, and page-type labels are plausible
- item is not an exact duplicate, near-duplicate, or split-leakage risk
- benchmark or holdout use does not conflict with existing benchmark stability and leakage policy
- public release payload remains bounded by existing rights, privacy, review, dedupe, split, benchmark, synthetic-cap, and export-portability gates

No modern handwriting source should default into public release without review decisions or an equivalent typed accepted policy record.

## Composition Targets

F3b should treat composition as a target for balanced collection, not as permission to bypass gates. Early batches should report:

- demographic bands only when collected with consent and stored without identifying contributors
- script style: block print, cursive-like modern Hebrew, mixed print/cursive, and writer-specific natural variation
- page type: prompted lines, paragraph prose, list/table-like forms, envelopes/labels, and mixed printed-plus-handwritten pages when rights-clean
- language mix: Hebrew-only, Hebrew with Arabic numerals, Hebrew with Latin fragments, and carefully reviewed mixed Hebrew/English
- page conditions: clean scan, mild skew, varied writing instruments, lined/plain paper, and normal smartphone capture variation

Composition metadata must not claim sensitive identity attributes, infer protected classes, or publish contributor-level profiles. Aggregate reporting should be sufficient for dataset balance.

## Takedown And Removal Workflow

Modern handwriting contributors, source owners, or affected third parties must have a removal path. Because public-profile material is expected to use broad public reuse terms, takedown is prospective for hocrgen/HeOCR-controlled distribution: it removes or blocks affected items from future project releases, but it cannot promise to revoke already distributed public copies or downstream reuse that happened under valid release terms.

Minimum handling:

1. receive the concern through a public issue when non-sensitive, or through a private maintainer/security channel when rights or privacy details are sensitive
2. identify affected source ids, item ids, consent artifact ids, release versions, and benchmark membership
3. block future public promotion through review decisions, source status, or config changes while investigating
4. remove affected items from future public payloads when the concern is valid or unresolved
5. document that removal applies to future hocrgen/HeOCR releases and does not revoke already distributed public copies
6. preserve release-relative export behavior and document the change in release diffs, changelogs, release notes, and PR metadata where disclosure is safe
7. keep the full sensitive evidence in private maintainer records rather than public manifests

If a benchmark item is affected, benchmark stability policy still applies: the replacement/removal must be deliberate, documented, and versioned.

## Typed Manifest Expectations

F3b introduces a typed operator intake shape before any sample collection. The shape includes:

- batch id, source id, operator id, collection date, and collection method
- contributor eligibility class, with adult contributor as the only F3b public-profile-eligible class
- consent artifact id or institutional agreement id stored as a private-record reference
- consent/release terms version, consent effective date, consent scope, and normalized license id
- normalized rights candidate and public-profile eligibility state
- private evidence locator for consent/provenance records, without public personal data
- privacy-screening status, reviewer id, review timestamp, and unresolved-risk flags
- source-relative asset paths and checksums only
- prompt/page type, script style, language mix, and composition metadata
- takedown/removal status, takedown request date when applicable, and affected future release versions
- public-release inclusion state and the first/last release versions in which the item appears

The manifest must remain compatible with existing public export portability rules and must not publish absolute local filesystem paths or private consent records. Configured modern intake sources must use `status: review_only`, `requires_manual_review: true`, `default_public_release: false`, and `HEOCR-CONSENT-OPEN`.
