package perigraph

import (
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func decodeRequest(t *testing.T, text string) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal([]byte(text), &body); err != nil {
		t.Fatal(err)
	}
	return body
}

func TestNullOptionalFieldsConformanceVector(t *testing.T) {
	body := decodeRequest(t, `{"messages":[{"role":"system","content":"Answer with the option letter only. Do not explain."}],"tools":null,"response_format":null}`)
	r := FromRequest(body, "shim", "1")

	if r.HarnessIdentity != "eeb813c17bed213fe02c7100" {
		t.Errorf("harness identity = %q", r.HarnessIdentity)
	}
	if r.Status != "complete" {
		t.Errorf("status = %q", r.Status)
	}
	for _, name := range []string{"tool_schemas", "readout", "generation_controls", "decoding"} {
		if got := r.Absent[name]; got != (Absence{Reason: "not_provided"}) {
			t.Errorf("%s absence = %+v", name, got)
		}
		if _, held := r.Parts[name]; held {
			t.Errorf("held %s despite null input", name)
		}
		a := ToAttributes(r)
		if got := a["perigraph.absent."+name+".reason"]; got != "not_provided" {
			t.Errorf("%s wire reason = %v", name, got)
		}
		if _, detailed := a["perigraph.absent."+name+".detail"]; detailed {
			t.Errorf("%s wire absence has a detail", name)
		}
	}
}

func TestNullTopLevelFieldsEqualOmittedFields(t *testing.T) {
	nulls := FromRequest(decodeRequest(t, `{
		"messages":null,"tools":null,"response_format":null,
		"temperature":null,"top_p":null,"top_k":null,"seed":null,
		"frequency_penalty":null,"presence_penalty":null,"logit_bias":null
	}`), "shim", "1")
	omitted := FromRequest(map[string]any{}, "shim", "1")
	if !reflect.DeepEqual(nulls, omitted) {
		t.Fatalf("null optional fields differ from omitted fields:\nnull: %+v\nomitted: %+v", nulls, omitted)
	}
}

func TestNullFieldsDoNotMaskOtherFields(t *testing.T) {
	r := FromRequest(decodeRequest(t, `{
		"messages":[{"role":"system","content":"Keep this."}],
		"tools":null,"response_format":null,"temperature":0
	}`), "shim", "1")
	if r.HarnessIdentity != handSHA("instruction=" + handSHA("Keep this.") + ";")[:24] {
		t.Errorf("instruction did not identify the harness: %q", r.HarnessIdentity)
	}
	if r.Absent["tool_schemas"].Reason != "not_provided" ||
		r.Absent["readout"].Reason != "not_provided" ||
		r.Absent["generation_controls"].Reason != "not_provided" {
		t.Fatal("null fields were not marked not_provided")
	}
	if p := r.Parts["decoding"]; p.Boundary != "canonical_value" ||
		p.Digest != handSHA(`{"temperature":0}`) {
		t.Errorf("present temperature not recorded: %+v", p)
	}
}

func TestNestedNullAndWrongTypesRemainExtractionFailures(t *testing.T) {
	for _, tc := range []struct {
		body  string
		part  string
		where string
		found string
	}{
		{`{"messages":[null]}`, "instruction", "messages[0]", "null"},
		{`{"messages":[{"role":"system","content":null}]}`, "instruction", "messages[0].content", "null"},
		{`{"tools":[null]}`, "tool_schemas", "tools[0]", "null"},
	} {
		r := FromRequest(decodeRequest(t, tc.body), "shim", "1")
		a := r.Absent[tc.part]
		if a.Reason != "extraction_failed" ||
			!strings.Contains(a.Detail, tc.where) ||
			!strings.Contains(a.Detail, tc.found) {
			t.Errorf("%s: %s absence = %+v", tc.body, tc.part, a)
		}
		if r.Status != "complete" {
			t.Errorf("%s: status = %q", tc.body, r.Status)
		}
	}
	// Version 4 removes the response_format object type check and readout binding.
	r := FromRequest(decodeRequest(t, `{"response_format":[]}`), "shim", "1")
	if r.Absent["readout"] != (Absence{Reason: "not_provided"}) ||
		r.Parts["generation_controls"].Digest != handSHA(`{"response_format":[]}`) ||
		r.Status != "complete" {
		t.Errorf("array response_format: %+v", r)
	}
}
