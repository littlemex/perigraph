# What the second implementation found

A spec with one implementation has not been tested as a spec. `SPEC.md` said so, and this is the result of testing it:
**a TypeScript implementation written from the spec, and every sentence that read two ways.**

Five ambiguities, of which **one was fatal to interoperability** and one was silently wrong in a way no test on either
side would have caught. All five are now fixed in `spec/vocabularies.json`, and the fixes are pinned by
`spec/fixtures/identity.json`, which both implementations test against — so the next divergence is a test failure on
both sides rather than something discovered by comparing two records in production.

## The measured result before the fixes

Same request body, both implementations, 24 wire attributes:

| | |
|---|---|
| attributes that agreed | **22** |
| attributes that disagreed | **2** — `part.tool_schemas.digest` and `part.decoding.digest` |
| **the identity** | agreed — **by luck, not by specification** |

The identity agreed only because the second implementer had read the first implementation's source. **From the spec
alone it could not have.**

## 1. Fatal: the identity's serialisation was never specified

`SPEC.md` section 2 said the identity is *"a digest over its identifying parts, sorted by part name"*. That leaves
undefined:

- how the parts are **joined** — the first implementation writes `<part_name>=<digest>;` per part and concatenates;
- that the result is **truncated** to 24 hex characters;
- what bytes a **string** has, for the payload digests underneath.

Two implementations disagreeing on an identity **cannot group anything**, which is the only thing the identity is for.
A record from each of two conformant senders would have looked like two different harnesses for the same run.

**Fixed:** `digest.algorithm`, `digest.encoding`, `digest.identity_length`, `digest.identity_serialisation`.

## 2. Silently wrong: the encoding, and why the fixture set contains Japanese

Nothing said `utf-8`. UTF-8 is the only defensible reading, and **an implementation choosing UTF-16 would have produced
a different identity for every non-ASCII instruction while passing every test it wrote for itself** — because a test
suite written in English never exercises the difference.

That is why `spec/fixtures/identity.json` includes an instruction in Japanese. It is not decoration: it is the only case
in the set that can fail for this reason.

## 3. Unfixable, and now stated: `parsed` digests are collector-local

The two digests that disagreed are both `parsed`. The cause is not a bug on either side:

| | renders `0.0` as |
|---|---|
| Python `repr` | `0.0` |
| JavaScript `JSON.stringify` | `0` |

There is no neutral serialisation to legislate here that would not amount to picking one language's conventions, so the
spec now says the true thing instead: **a `parsed` digest is comparable only against another digest from the same
collector and the same collector version.**

Nothing that matters was lost — a `parsed` digest can never key an identity. What was at risk before saying it is
**somebody comparing two and concluding the harnesses differed**, which is exactly the false positive this protocol
exists to prevent. A receiver must now refuse that comparison.

## 4. The instruction join was collector-local and must not be

With several system messages, nothing said how they combine. The first implementation joins with one newline.

This one **cannot** be left local, because the instruction digest **keys the identity**: two collectors choosing
differently would produce two identities for one request. Now normative.

## 5. An empty manifest crashed the second implementation on its first empty record

`collector_reaches` is *"comma-separated part names"*, and nothing said what an empty manifest looks like on the wire.
Splitting `""` on `","` yields `[""]` in both languages — a manifest claiming a part named empty-string — and `Manifest`
then refuses the whole record.

The first implementation filtered the empty entry out, in a line that reads like defensive habit rather than a decision.
The second hit it as a crash. The behaviour is now pinned by a test on both sides.

## What this says about the method, not the protocol

Four of the five were **invisible from inside one implementation**. The Python side had tests for all of the behaviour
that mattered, and every one of them passed both before and after these fixes: a test written against an implementation
cannot find a sentence that implementation happened to interpret one way.

The one thing that found them was **writing it again from the document**. That is the whole argument for a second
implementation, and it is worth more than any feature that could have been added in the same time.

**Still not tested:** everything a second implementation shares with the first by accident of being written by the same
author. A third implementation by somebody else remains the real test.
