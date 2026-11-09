# Decision 2026-11-09: non-Google library scans on the Internet Archive may be used for training

- **Date:** 2026-11-09
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Status:** accepted
- **Applies to:** pairing Project Ben-Yehuda (PBY) texts with Internet Archive (IA) scans of the same printed edition
  (F8f, the PBY ↔ scan alignment), for training and dev

**Context.** The NLI rights gate (F8c, `decide_nli_rights`) accepts only `public-domain-free-use` scans. The
maintainer decided the same day that non-commercial-only scans, including NLI's Google-class scans, stay out of
training for now. That left few NLI scans before 1900. A metadata-only scouting pass then found non-Google scans of 55
PBY edition groups on IA, made by university libraries such as Toronto, Duke, Columbia and Michigan. 24 of them are
from before 1900. None of these IA items carries an explicit licence. Some carry `possible-copyright-status:
NOT_IN_COPYRIGHT`. IA's site terms describe access as being for scholarship and research.

## Decision

> "Yes, allow them" (Shay Palachy Affek, 2026-11-09), on the conditions below, as proposed.

An IA scan may be used when all of these hold:

1. **The book is in the public domain.** The edition is the one a PBY text was typed from, and PBY carries only
   public-domain works.
2. **The scan is a library scan, not a Google scan.** Reject an item when its scanner, contributor, sponsor or
   collection names Google, when its id starts with `bub_gb_`, or when its description says it was derived from
   Google Books. A public-domain mark on such an item does not change this.
3. **The source is known.** Anonymous uploads with no known scanning library are excluded.
4. **No other source's terms apply.** Files that came from NLI, for example through Wikimedia Commons, stay under
   NLI's gate.
5. **Nothing restrictive is attached to the item**, such as a non-commercial licence or a rights statement that
   restricts reuse.

IA's site terms of use (access for scholarship and research) govern use of the website. They are not read as a
licence restriction on the public-domain book.

## Consequences

- IA becomes a second scan source for the F8f alignment. It has its own rights gate implementing the conditions
  above, and that gate records its evidence for each item. The NLI gate is unchanged.
- Every pair stays silver (`not_adjudicated`, `reference_eligible: false`), as for NLI scans.
- Any other new scan source still needs the maintainer's approval first.
