# Mixed-script synthetic evaluation recipe (2026-11-03)

This project-authored corpus is released under this repository's MIT license. It
contains invented generic text and no source documents. Its SHA-256 is
`b325673476bce8c16f0a2731e5de1ec9b226b8274fc1e7dfb723dbccb3edf966`.
The evaluation is a seed/text holdout against the participating stage's
hand-authored tests; the generator's existing templates and fonts are shared.
It is not a held-out-template or real-document generalization test.

Generate from hocrsyngen revision `bc4394c` (S11b implementation), with
Python 3.12.11, Pillow 12.2.0, libraqm 0.10.3 and FreeType 2.14.3. Asset
bytes may vary with the rest of the imaging stack; compare hashes before
claiming an exact reproduction. From an installed checkout, set `CORPUS` to the
adjacent corpus file and `BATCH` to a fresh empty destination:

```sh
hocrsyngen generate --count 100 --seed 26110302 --output "$BATCH" \
  --template-id printed_letter --template-id handwritten_note \
  --template-id archive_card --template-id ledger --text-corpus "$CORPUS" \
  --emit-line-annotations --rendering-coverage-report --format json
hocrsyngen validate "$BATCH" --format json
```

The frozen manifest SHA-256 was
`5979ada50f085e91e6f2d43f9286daea3c4fe4acb0718bf5dfb1962b31b4cdbe`;
the line sidecar SHA-256 was
`5a6ba66ca8cba5a1a6071b95a0a7774e698f2c713dc304a48ed3b1f3e0994d3f`.
Manifest hashes bind the 100 image assets. The sidecar recorded 216 omitted
wrapped source segments and 90 lines with automated occlusion flags; gold
contains the drawn segments, not omitted text. This is not a human audit of
all 100 pages. The initial generation was discarded before scoring after visual
and independent review detected ledger collisions and a jitter edge case;
regeneration corrected those defects without using evaluation scores.

The local recognizer was Tesseract 5.5.3, `heb+eng`, PSM 3, 60 seconds per
page, 30 minutes total, serial, no network. Executable SHA-256:
`d3d15b31535c2dd88cbbb53ec54a16b9a739f4146e1648b4b6ad57cf5ce79f1d`.
Hebrew model SHA-256:
`11f9e43ab227f786352a50f75c94c2e9906f1baba86d93276da19da7ce0904db`;
English model SHA-256:
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
The candidate callable was heocr-engine commit
`1175cdd3a0fac06fc0d9130100bcfb44c0e9c11e`. The local run supplied no
prediction-side table geometry: all 100 correction calls abstained. No gold
geometry was passed to correction. With `evaluate-references` and `primary.v1`,
100 common pages yielded CER 15,780/27,443 and WER 4,201/5,813 for both
outputs. These values describe this synthetic recognizer baseline and safe
abstention interface only; they do not test correction effectiveness. Profiles
fold whitespace and other details as specified in `docs/reference_evaluation.md`;
report raw and optional secondary typography profiles separately.
