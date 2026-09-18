"""The injection: wrap what a sender already calls, and the record happens on the way past.

**Zero code change on either side is what decides whether this is usable at all**, and it is the one property already
solved by somebody else. A tracer's auto-instrumentation already wraps the client and already emits a span; all this adds
is attributes on a span that would have been emitted anyway.

**The tracer is optional and the collector is not.** A sender with no tracer still gets a record it can carry however it
likes -- writing it to a log line, attaching it to its own metrics, posting it somewhere. Making the tracer mandatory
would mean a sender has to adopt an observability stack before it can answer "what surrounded the model", and that is a
much bigger ask than the question deserves.

**What this deliberately does not do: fail the call.** A shim that can break the request it is describing is a shim
nobody will leave installed, and then there is no record at all. Every failure here degrades the record and lets the call
through, which is the same rule as the permissive half of the record itself -- and the degradation is recorded as
`collector_failed`, so the record cannot pass its own failure off as the sender's silence.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from perigraph.collect import from_request
from perigraph.record import Manifest, Record
from perigraph.wire import to_attributes

DEFAULT_COLLECTOR = "perigraph-python"
DEFAULT_VERSION = "0.1.0"


def _failed_record(collector: str, version: str) -> Record:
    """The record a collector produces when it could not produce one.

    A record rather than nothing, and this is the case the whole status vocabulary exists for: **a collector cannot
    record its own absence.** If a shim that crashed emitted nothing, the run would be indistinguishable from a run that
    never happened, and the absence of a record is exactly what nobody can notice.
    """
    from perigraph.collect import FROM_A_REQUEST
    return Record(manifest=Manifest(collector=collector, version=version, reaches=FROM_A_REQUEST),
                  status="collector_failed")


def observe(body: dict, *, collector: str = DEFAULT_COLLECTOR, version: str = DEFAULT_VERSION) -> Record:
    """Read a body into a record, and turn any failure into a `collector_failed` record rather than an exception.

    The exception is swallowed on purpose and the fact of it is not: the status says the collector did not finish, so a
    receiver refuses a verdict over it while a log keeps it. What is not acceptable is a record that looks complete.
    """
    try:
        return from_request(body, collector=collector, version=version)
    except Exception:
        return _failed_record(collector, version)


def emit(record: Record, *, span: Any | None = None) -> dict[str, str | int | float]:
    """Put a record's attributes on a span if there is one, and return them either way.

    `span` is passed in rather than looked up so that this function has no opinion about how a caller gets one. When it
    is omitted and OpenTelemetry is installed, the current span is used; when it is not installed, the attributes are
    returned and nothing else happens -- which is the whole of the optional-tracer promise.
    """
    attrs = to_attributes(record)
    target = span
    if target is None:
        try:  # pragma: no cover - depends on whether the optional extra is installed
            from opentelemetry import trace

            candidate = trace.get_current_span()
            if candidate is not None and candidate.is_recording():
                target = candidate
        except Exception:
            target = None
    if target is not None:
        for key, value in attrs.items():
            try:
                target.set_attribute(key, value)
            except Exception:
                # One rejected attribute must not cost the rest of the record. A tracer with a key-length limit or a
                # type restriction is a normal thing to meet, and losing the whole record to it would be the shim
                # breaking the observability it was added to improve.
                continue
    return attrs


def wrap(fn: Callable[..., Any], *, collector: str = DEFAULT_COLLECTOR, version: str = DEFAULT_VERSION,
         body_arg: str = "body", on_record: Callable[[Record], None] | None = None) -> Callable[..., Any]:
    """Wrap a callable that sends a request body, so calling it records what surrounded the model.

    This is the seam a sender uses when it does not have auto-instrumentation: one wrap at the client boundary, no change
    anywhere else. `on_record` is where a sender decides what to do with the record, and it defaults to `emit`.

    The body is found by keyword first and then by taking the first positional dict, because the two clients this has to
    fit call it `body`, `json`, or nothing at all. A body it cannot find yields a `collector_failed` record and the call
    goes through untouched -- never an exception, for the reason in the module docstring.
    """
    sink = on_record if on_record is not None else (lambda r: emit(r))

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        body = kwargs.get(body_arg) or kwargs.get("json")
        if body is None:
            body = next((a for a in args if isinstance(a, dict)), None)
        record = observe(body, collector=collector, version=version) if isinstance(body, dict) \
            else _failed_record(collector, version)
        try:
            sink(record)
        except Exception:
            pass
        return fn(*args, **kwargs)

    return wrapper
