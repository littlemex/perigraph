"""perigraph -- a record of what surrounded the model.

The public surface is small on purpose: read a body into a record, declare the parts a body cannot carry, flatten a
record for carriage, and wrap a client so the first two happen without the sender editing anything else.
"""
from perigraph.collect import FROM_A_REQUEST, REQUEST_BOUNDARIES, declare, from_request
from perigraph.instrument import emit, observe, wrap
from perigraph.record import Absence, Manifest, Part, Record, digest
from perigraph.vocab import SPEC_VERSION, Unidentified, conformance
from perigraph.wire import from_attributes, to_attributes

__version__ = "0.1.0"
__all__ = ["Absence", "FROM_A_REQUEST", "Manifest", "Part", "REQUEST_BOUNDARIES", "Record", "SPEC_VERSION",
           "Unidentified", "conformance", "declare", "digest", "emit", "from_attributes", "from_request", "observe",
           "to_attributes", "wrap"]
