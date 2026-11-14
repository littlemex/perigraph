# Proposal 0002: one harness identity per arm

## What changed while every existing name stayed the same

In R17a ([proposal 0001](0001-request-template.md)), one byte-identical checkpoint answered 0.8983 with no instruction, 0.8608 with the instruction as a system message (3.75 points apart), and 0.8525 with the instruction in the user message (4.58 points). tierbook's `check-observations` accepted H0 and H1 under one arm name, because the arm's model identity was the same. Version 2 already refused a verdict over H0's records one by one, since they have no harness identity, so a receiver following it would not have pooled them; tierbook did not, because it read no harness identity at all. Version 2 refuses an arm whose records carry more than one model identity and has no rule for the harness. R17a contains the case {one identity, some without}; the case {X, Y}, two identities under one name, is what two wrappers under one system message would give, and is not measured.

## The change to spec/vocabularies.json

`receiver_obligations.must_refuse` gains:

> A verdict over records grouped as one arm when the distinct harness identities derived from them number more than one, or number one while some record has none.

SPEC section 4 states it with the identities a receiver derives (section 6), requires a receiver that gives a verdict over the records of one identity within the arm to say how many it left out, and names the arms it refuses. The wording is a set rule rather than a copy of the model-identity sentence: a record with no harness identity is already refused on its own, so "some with one and some without" has to say what happens to the others.

## Cases a non-conforming implementation fails

None portable yet. Arm membership is not on the wire (SPEC 6.1), and the conformance adapter has no group operation; the README roadmap lists one, with cases for arms of {X, X}, {X, Y}, {X, none} and {none, none}. tierbook implements the rule over its own observation files, as an opaque `arm_harness` string per row, in its own repository.

## What a receiver does with it

It can only refuse. Two records with the same derived identity are not thereby admitted to anything they were not admitted to before.

## Whether it is breaking

Yes: an entry in `must_refuse` (SPEC 7). It ships in version 3 with proposal 0001.
