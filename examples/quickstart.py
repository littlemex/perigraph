"""Record a request, carry the record as flat attributes, and read it back as a receiver would."""
import json

from perigraph import collect, wire

body = {
    "model": "example-model",
    "messages": [
        {"role": "system", "content": "Answer in one word."},
        {"role": "user", "content": "Which colour is the sky?"},
    ],
    "temperature": 0,
}

record = collect.from_request(body, collector="quickstart", version="1")
attributes = wire.to_attributes(record)
print(json.dumps(attributes, indent=2))

received = wire.from_attributes(attributes)
print("harness identity:", received.identity)
print("verdict:", "admitted" if received.admissible_to_a_verdict() else "refused")
