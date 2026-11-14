# Binding: JSON Lines files

Normative for a collector or forwarder that writes records to a file, and for a receiver that reads them (SPEC section 0.2).

Each line is one JSON object, in UTF-8, whose members are a record's attributes, exactly as SPEC section 6 names them, with string, number or boolean values. Members outside the `perigraph.` prefix MAY be present and are not part of the record. A file holds records of one `perigraph.spec_version` or several; the version is read per line.

```json
{"perigraph.spec_version": 3, "perigraph.collector": "example-gateway", "perigraph.collector_version": "3.1.0", "perigraph.collector_reaches": "instruction,request_template,tool_schemas,readout,decoding", "perigraph.status": "complete", "perigraph.harness_identity": "c8f8edc45e222f663d8d70ac", "perigraph.model_reaches": "", "perigraph.model_absent.checkpoint.reason": "not_observable", "perigraph.model_absent.precision.reason": "not_observable", "perigraph.model_absent.runtime.reason": "not_observable", "perigraph.model_absent.answer_mode.reason": "not_observable", "perigraph.part.instruction.sourcing": "in_the_request", "perigraph.part.instruction.digest": "bc08b15e1d666817a85deb76df71182f5b17ee4ea314f8635a98fe14b17b4ad3", "perigraph.part.instruction.boundary": "model_visible", "perigraph.absent.request_template.reason": "not_provided", "perigraph.absent.tool_schemas.reason": "not_provided", "perigraph.absent.readout.reason": "not_provided", "perigraph.absent.decoding.reason": "not_provided", "perigraph.absent.loop.reason": "not_provided", "perigraph.absent.turn_budget.reason": "not_provided", "perigraph.absent.retry_policy.reason": "not_provided", "perigraph.absent.context_partitioning.reason": "not_provided", "perigraph.absent.tool_extension.reason": "not_observable", "perigraph.absent.tool_trace.reason": "not_provided"}
```

A blank line is ignored. A line that is not a JSON object is not a record, and a receiver MUST count it as a lost record rather than skip it silently: SPEC section 1.1 reads a loss nobody reported as `unknown`, and a skipped line is a loss nobody reported. A line that is an object and fails the checks of SPEC section 6 is rejected like any other record.

Each line can be checked on its own against `spec/schema/record.schema.json`.
