# Proposal NNNN: title

Copy this file to `docs/proposals/NNNN-short-name.md`, using the next free number, and open a pull request. SPEC section 13.1 lists what a proposal must contain; each heading below is one of those items.

## What changed while every existing name stayed the same

The measured case: what was run, what changed, which existing parts, values or attributes all stayed the same across the change, and what the change did to a result. Link the data at a pinned commit. A proposal without a measured case is not considered, because a value nobody needed is a value every implementation must still carry.

## The change to spec/vocabularies.json

The diff, and the new SPEC.md sentences that use the value. Run `tools/gen_schema.py` and `tools/requirements.py` and include their output in the pull request.

## Cases a non-conforming implementation fails

The fixtures or conformance cases added (`conformance/README.md`), and for each one which behaviour it rules out. Say which implementations in `IMPLEMENTATIONS.md` pass them.

## What a receiver does with it

Whether the value may key an identity and why, whether it can trigger a refusal, and confirmation that it can never lift one (SPEC section 1.1a).

## Whether it is breaking

The answer under SPEC section 7, with the reason.
