# Proposal 0004: a backend states which harness parts its answer did not read

Status: draft, not yet a change to `spec/vocabularies.json`.

## What changed while every existing name stayed the same

A router in front of a Prismyra server replaced the system message between two runs. The harness identity, computed over the provider-bound bytes, changed with it, as it should. The answers did not: 60 of 60 were identical, with a probability difference of 0.0, because Prismyra's chat endpoint answers a learn-spec tag from the last user message alone and never shows the model a system message. The two runs are recorded as two harnesses, and a reader concludes the system prompt has no effect, when the truth is that it never arrived.

Prismyra now says so on every answer (`prismyra.read`, `prismyra.ignored`, and a strict mode that refuses instead). The record has no place to carry that statement.

## The change

A new absence reason, `not_read`, that only a stamper (the process that answers) may write, for a harness part present in the request that its answer mode does not read. A part marked `not_read` is excluded from the harness identity, and the set of parts marked `not_read` enters the identity in its place, so "the instruction was not read" and "there was no instruction" remain different identities.

## What a receiver does with it

`not_read` can key an identity only as described above, and only from a stamper. A collector in front of a backend never writes it: it holds the request, not the backend's behaviour, so its record keeps saying `in_the_request`, which makes no claim about what the model saw.

## Two records of one request

A collector in front of the backend and the backend's own stamper would then state different harness identities for one request: the collector's over everything it held, the stamper's over what its answer read. A receiver that joins them must not require both to agree. The stamper's is the one that describes what answered, so a receiver takes it, and uses the collector's record only to check that both held the same bytes.

## Whether it is breaking

Not for receivers of version 4 records, which never see the reason. A version that adds it is a minor version under SPEC section 7, since an identity computed by a stamper that writes `not_read` differs from one computed by a collector that does not.
