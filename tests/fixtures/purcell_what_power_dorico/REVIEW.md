# Dorico fixture verification record

Reviewed on 2026-11-15.

## Scope

This fixture verifies a one-page, treble-clef part exported directly from Dorico 5.1. It does not claim compatibility with every Dorico version, scanned scores, or PDFs post-processed by another publishing application.

## Source verification

- The PDF and companion MusicXML were downloaded from the same pinned upstream commit.
- Their SHA-256 digests are fixed in `manifest.json` and checked by the test suite.
- The PDF metadata reports `Creator: Dorico 5.1.60.2187` and `Producer: Qt 6.5.0`.
- The MusicXML reports `Dorico 5.1.81.2225` as its encoding software. The different versions are recorded separately rather than treated as identical exports.

## Semantic verification

The `P1` (`Violino 1`) part in the upstream MusicXML is used as an independent semantic oracle for the PDF parser:

- 36 measures
- 281 notes
- 78 notes whose sounding pitch contains a flat or sharp
- 281/281 detected PDF notes match the MusicXML note order, letter, octave, and effective accidental
- 78 true positives, 0 false positives, and 0 false negatives
- fixture precision: 100%
- fixture recall: 100%

The tests also check the note count in every measure and the expected marked-note ordinal in every system. This avoids treating the implementation's current output as its own ground truth.

## Visual verification

The original and annotated PDFs were rendered to PNG for review. The single output page preserves the source layout and fonts, and all 78 annotation circles are centered on the intended noteheads. Generated annotated files are review artifacts and are not committed.

## Regression found by this fixture

Before the Dorico stem fix, the parser detected all 281 pitches but marked 87 notes. Nine E-natural notes were false positives because Dorico stems were mistaken for barlines, resetting accidental state within measures. This fixture reproduces that failure and requires the corrected 78-note result.
