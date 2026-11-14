"""perigraph -- a record of what surrounded the model.

The public surface is small on purpose: read a body into a record, declare the parts a body cannot carry, flatten a
record for carriage, and wrap a client so the first two happen without the sender editing anything else.
"""
from perigraph.arm import ArmAdmission, admit_arm
from perigraph.canonical import NotCanonical, canonical_digest
from perigraph.collect import FROM_A_REQUEST, REQUEST_BOUNDARIES, declare, from_request
from perigraph.instrument import emit, observe, wrap
from perigraph.model import Model, ModelAbsence, ModelPart
from perigraph.record import Absence, Manifest, Part, Record, digest
from perigraph.vocab import SPEC_VERSION, Unidentified, conformance
from perigraph.wire import from_attributes, to_attributes

__version__ = "0.2.1"
__all__ = ["Absence", "ArmAdmission", "NotCanonical", "admit_arm", "canonical_digest", "FROM_A_REQUEST", "Manifest", "Model", "ModelAbsence", "ModelPart", "Part", "REQUEST_BOUNDARIES", "Record", "SPEC_VERSION",
           "Unidentified", "conformance", "declare", "digest", "emit", "from_attributes", "from_request", "observe",
           "to_attributes", "wrap"]
