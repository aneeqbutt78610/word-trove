# How Our Word List Works

Canonical: [How Our Word List Works](https://wordtrove.app/how-our-word-list-works/)

Locale: en

Purpose: Source, filtering, scoring method, counts and limits of the word list

Content updated: 2026-10-24

Source revision: build-2026-10-24

Maintenance owner: WordTrove editorial team

[Topic map](https://wordtrove.app/llm/topics/about-site.md) · [Complete scoped map](https://wordtrove.app/sitemap.md)

## Quick answer

WordTrove uses the SCOWL-based Hunspell en_US dictionary (Debian release 2020.12.07, size 70). We expand its root words into plurals and other inflected forms, keep lowercase words of 3 to 8 letters, and remove proper nouns, abbreviations and offensive words. The result is 54,779 words.

## Source dictionary

The list starts from [SCOWL](https://wordlist.aspell.net/), the Spell Checker Oriented Word Lists maintained by Kevin Atkinson, as packaged for Hunspell en_US by Debian (release 2020.12.07, size 70). Size 70 includes common and moderately rare words but leaves out the most obscure entries.

## How we filter it

- Expand each root word with the dictionary's own affix rules, such as plural -s and past tense -ed.
- Keep only words written in lowercase letters a to z, which removes proper nouns, abbreviations and words with apostrophes.
- Keep words from 3 to 8 letters long.
- Remove a short list of slurs and profanity.

## Word counts

| Length | Words | Highest scoring |
|---|---|---|
| 3 letters | 1,061 | XXX (24) |
| 4 letters | 3,386 | JAZZ (29) |
| 5 letters | 6,543 | PZAZZ (34) |
| 6 letters | 10,871 | JAZZED (32) |
| 7 letters | 15,481 | PIZZAZZ (45) |
| 8 letters | 17,437 | QUIZZING (36) |

## How scores are calculated

Each word's score is the sum of standard English Scrabble tile values: A, E, I, L, N, O, R, S, T and U are 1; D and G are 2; B, C, M and P are 3; F, H, V, W and Y are 4; K is 5; J and X are 8; Q and Z are 10. Board bonuses are not included.

## How "common first" ordering works

Words are ranked by how often they appear in an English text corpus of about 50 MB of software documentation and manual pages. This ranks everyday words first but leans slightly toward technical vocabulary. Words that never appear in that corpus are listed alphabetically after it.

## Limits

- This is not the official Scrabble dictionary (NWL or Collins) or the Wordle answer list. A word we list may not be accepted by a given game, and some game words are missing.
- Words longer than 8 letters are not included.

Updated 2026-10-24. Report a missing or wrong word on the [contact page](https://wordtrove.app/contact/).
