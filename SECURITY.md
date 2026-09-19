# Security

## What this project is and is not, in security terms

**perigraph records what surrounded a model. It does not authenticate anything.**

A record says where each fact came from — `in_the_request`, `pulled_by_us`, `pushed_by_owner`, `not_observable` — and a
receiver uses that to decide what the fact may support. **None of it is a signature.** A `pushed_by_owner` part is the
owner's word and the spec says so; an `in_the_request` digest proves only that the sender held those bytes, not that
anybody else can verify it did.

If you need non-repudiation, the borrowed shape is SCITT (RFC 9943) and it belongs **around** a perigraph record rather
than inside one. The project deliberately stops short of it: a format that looked authenticated while carrying a hash
nobody signed would be worse than one that is plainly unsigned.

## The one place a digest is load-bearing, and its limits

An identity is a truncated sha256 — **the first 24 hex characters**, which is 96 bits. That is chosen for a grouping
key, not against an adversary. It is adequate against accident and is **not** a commitment: an attacker who can choose
instruction text can look for a collision far more cheaply than against the full digest.

**Do not use `perigraph.identity` as an authorisation decision or a content commitment.** Use the full
`perigraph.part.instruction.digest` if you need one, and sign it with something built for that.

## Handling records

A record can contain the full text of a system prompt's **digest** but never the prompt itself, and never a user
message. That is by construction rather than by policy — the wire form carries digests and labels.

**A `label` is free text supplied by whoever built the record.** Treat it as untrusted input: it is meant for a human
reader, it is explicitly not a key, and nothing validates its contents.

A `tool_trace` is different: an implementation that stores response bytes rather than a digest is storing whatever a
tool returned, which may include anything a tool had access to. The reference implementations store digests only.

## Reporting

Open a GitHub issue. If it should not be public, say so in a one-line issue with no detail and a maintainer will follow
up privately.

**There is no security release process yet**, because there is no release with users. When there is, this file will say
what it is rather than implying one exists.
