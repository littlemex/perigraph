# Governance

perigraph is maintained by its author, [littlemex](https://github.com/littlemex), who decides what is merged. This document says how decisions are made today, and what will change when there is more than one maintainer.

## How a change is decided

| change | where it starts | what it needs before merge |
|---|---|---|
| a new value in a closed vocabulary, a new part or a new attribute | a proposal from `docs/proposals/0000-template.md` (SPEC section 13.1) | a measured case, the vocabulary diff, cases that a non-conforming implementation fails, and every implementation in `IMPLEMENTATIONS.md` passing them |
| a wording fix to SPEC.md that changes no behaviour | a pull request | the generated files current (`tools/gen_schema.py --check`, `tools/requirements.py --check`) and CI green |
| a clarification that changes what an implementation emits | an issue first, saying which reading each implementation takes | a conformance case or fixture pinning the chosen reading, and all implementations passing it |
| a new binding under `spec/bindings/` | a pull request | a field-to-part table and at least one example record |

A change that is breaking under SPEC section 7 is not merged into the current version.

## Disagreements

A disagreement about what the text means is settled by adding a case, never by a comment in a thread: the case records the decision where every implementation runs into it. When two implementations disagree, the text is presumed defective until shown otherwise.

## What is not in place yet

- A formal versioning and compatibility policy (SPEC section 7.1).
- More than one maintainer. When there are several, this document will say how they decide, and decisions about the specification will need agreement from someone who did not write the change.
- A process for registering vendor names under `perigraph.ext.` (SPEC section 13.2). Until there is one, a vendor name is a domain or project name its author controls.

Security reports follow `SECURITY.md`.
