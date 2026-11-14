# Proposal 0005: one generation control under two member names

Status: draft, not yet a change to `spec/vocabularies.json`.

## What changed while every existing name stayed the same

The same 20 requests were sent to a vLLM 0.27.1 server directly and through vLLM Semantic Router at `8396cbbe`, with no decision plugin changing them. The router re-encodes `max_tokens` as `max_completion_tokens`. The perigraph collector inside the vLLM server recorded `generation_controls` labelled `max_tokens` for the direct requests and `max_completion_tokens` for the routed ones, so the two arms got different harness identities (`b4f1e1197cc726e5f94f78ef` against `d3cc13ffb19bd4d3b63e898a`) while vLLM applied the same output limit to both.

## The question

The split is the safe direction (SPEC 2.1): it never merges two runs that differed. It is also a split that every router in front of a backend will cause, so an arm measured directly and the same arm measured through a router are never comparable. Two options:

| option | what it does | what it risks |
|---|---|---|
| keep the split | nothing changes | arms on routed and direct paths never compare |
| a closed alias table in the OpenAI binding, `max_completion_tokens` and `max_tokens` read as one control | the two arms above get one identity | a backend that treats the two members differently would be merged with one that does not |
| keep the split, and let a receiver's operator declare two harness identities one arm | no spec change; the declaration is the operator's and is printed with the result | a declaration nobody checked; it can only be offered as a claim, which may refuse and never lift (SPEC 1.1a) |

## What a receiver does with it

Nothing new: an alias table changes what the collector digests, and the identity rules are unchanged.

## Whether it is breaking

Yes for the binding: the `generation_controls` digest of every request that sends either member changes, so it is a major version under SPEC section 7.
