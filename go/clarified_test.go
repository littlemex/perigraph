package perigraph

import (
	"crypto/sha256"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEmbeddedVocabularyMatchesRepository(t *testing.T) {
	repositoryPath := filepath.Join("..", "spec", "vocabularies.json")
	repository, err := os.ReadFile(repositoryPath)
	if os.IsNotExist(err) {
		t.Skip("repository vocabulary is not present")
	}
	if err != nil {
		t.Fatal(err)
	}
	embedded, err := VocabularyJSON()
	if err != nil {
		t.Fatal(err)
	}
	if got, want := sha256.Sum256(embedded), sha256.Sum256(repository); got != want {
		t.Fatalf("embedded vocabulary SHA-256 %x differs from repository SHA-256 %x", got, want)
	}
}

func TestUnresolvedPrecision(t *testing.T) {
	for _, fields := range []map[string]string{
		{"dtype.auto": "1", "quantisation": "none", "device": "cuda"},
		{"dtype. AUTO ": "1", "quantisation": "none", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": " auto ", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": " \t ", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": "none", "device": " AUTO "},
		{"dtype.\u3000AuTo\u0085": "1", "quantisation": "none", "device": "cuda"},
		{"dtype.\u00A0\u202F": "1", "quantisation": "none", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": "\u3000AuTo\u0085", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": "\u1680\u205F", "device": "cuda"},
		{"dtype.bfloat16": "1", "quantisation": "none", "device": "\u2028AUTO\u2029"},
		{"dtype.bfloat16": "1", "quantisation": "none", "device": "\u3000\u0085"},
	} {
		if _, err := PrecisionDigest(fields); err == nil {
			t.Errorf("accepted unresolved precision fields: %#v", fields)
		}
	}
}

func TestPrecisionWhitespaceDoesNotChangeDigest(t *testing.T) {
	fields := map[string]string{
		"device":           "\u3000cuda\u0085",
		"dtype.\u00A0bf16": "1",
		"quantisation":     "\u202Fnone\u205F",
	}
	got, err := PrecisionDigest(fields)
	if err != nil {
		t.Fatal(err)
	}
	want := handSHA("device=\u3000cuda\u0085\n" +
		"dtype.\u00A0bf16=1\n" +
		"quantisation=\u202Fnone\u205F\n")
	if got != want {
		t.Errorf("precision digest = %s, want %s", got, want)
	}
}

func TestMalformedToolsFailOnlyToolSchemas(t *testing.T) {
	for _, tools := range []any{
		"x",
		[]any{"x"},
		[]any{map[string]any{"function": "x"}},
		[]any{map[string]any{"function": nil}},
	} {
		r := FromRequest(map[string]any{
			"messages": []any{map[string]any{"role": "system", "content": "Terse."}},
			"tools":    tools,
		}, "shim", "1")
		a := r.Absent["tool_schemas"]
		if a.Reason != "extraction_failed" || a.Detail == "" ||
			!strings.Contains(a.Detail, "tools") || strings.Contains(a.Detail, "Terse.") {
			t.Errorf("tools %#v: incorrect absence %+v", tools, a)
		}
		if _, ok := r.Parts["tool_schemas"]; ok {
			t.Errorf("held malformed tools %#v", tools)
		}
		if _, ok := r.Parts["instruction"]; !ok {
			t.Errorf("tools %#v affected instruction", tools)
		}
		if r.Status != "complete" {
			t.Errorf("tools %#v changed terminal status", tools)
		}
	}
}

func TestMalformedMessagesAndBody(t *testing.T) {
	for _, messages := range []any{
		"x",
		[]any{map[string]any{"role": "system", "content": "Terse."}, "x"},
	} {
		r := FromRequest(map[string]any{
			"messages": messages,
			"tools":    []any{},
		}, "shim", "1")
		for _, name := range []string{"instruction", "tool_trace"} {
			a := r.Absent[name]
			if a.Reason != "extraction_failed" || a.Detail == "" ||
				strings.Contains(a.Detail, "Terse.") {
				t.Errorf("%s: incorrect absence %+v", name, a)
			}
		}
		if got := r.Absent["tool_schemas"]; got != (Absence{Reason: "not_provided"}) {
			t.Errorf("malformed messages affected empty tools: %+v", got)
		}
	}

	r := FromRequest(map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Terse."},
			map[string]any{"role": "system", "content": []any{"secret"}},
		},
	}, "shim", "1")
	a := r.Absent["instruction"]
	if a.Reason != "extraction_failed" ||
		!strings.Contains(a.Detail, "messages[1].content") ||
		!strings.Contains(a.Detail, "array") ||
		strings.Contains(a.Detail, "secret") || r.HarnessIdentity != "" {
		t.Fatalf("non-string system content: %+v, identity %q", a, r.HarnessIdentity)
	}

	var nullObject map[string]any
	if err := json.Unmarshal([]byte("null"), &nullObject); err != nil {
		t.Fatal(err)
	}
	var emptyObject map[string]any
	if err := json.Unmarshal([]byte("{}"), &emptyObject); err != nil {
		t.Fatal(err)
	}
	if emptyObject == nil {
		t.Fatal("decoded empty object is nil")
	}

	for _, tc := range []struct {
		name string
		body any
	}{
		{"string", "x"},
		{"array", []any{}},
		{"null value", nil},
		{"decoded null map", nullObject},
	} {
		r := FromRequestValue(tc.body, "shim", "1")
		for _, name := range r.CollectorReaches {
			a := r.Absent[name]
			if a.Reason != "extraction_failed" || a.Detail == "" {
				t.Errorf("%s: %s: %+v", tc.name, name, a)
			}
			if _, ok := r.Parts[name]; ok {
				t.Errorf("%s: held %s", tc.name, name)
			}
		}
		if r.Status != "complete" {
			t.Errorf("%s changed terminal status", tc.name)
		}
	}

	r = FromRequest(nullObject, "shim", "1")
	for _, name := range r.CollectorReaches {
		a := r.Absent[name]
		if a.Reason != "extraction_failed" || a.Detail == "" {
			t.Errorf("FromRequest decoded null: %s: %+v", name, a)
		}
	}
	if r.Status != "complete" {
		t.Error("FromRequest decoded null changed terminal status")
	}

	r = FromRequest(emptyObject, "shim", "1")
	for _, name := range r.CollectorReaches {
		if a := r.Absent[name]; a.Reason != "not_provided" {
			t.Errorf("empty object: %s: %+v", name, a)
		}
	}
}

func TestEmptyInstructionConformanceVector(t *testing.T) {
	var body map[string]any
	if err := json.Unmarshal([]byte(`{"messages":[{"role":"system","content":"　\u0085\t"}],"temperature":0.0}`), &body); err != nil {
		t.Fatal(err)
	}
	r := FromRequest(body, "shim", "1")
	if got := r.Absent["instruction"]; got != (Absence{Reason: "not_provided"}) {
		t.Errorf("instruction absence = %+v", got)
	}
	if _, held := r.Parts["instruction"]; held {
		t.Error("held whitespace-only instruction")
	}
	if r.HarnessIdentity != "" {
		t.Errorf("whitespace-only instruction gave harness identity %q", r.HarnessIdentity)
	}
	if _, present := ToAttributes(r)["perigraph.harness_identity"]; present {
		t.Error("emitted identity attribute for whitespace-only instruction")
	}
	if got := r.Parts["decoding"].Digest; got != handSHA(`{"temperature":0}`) {
		t.Errorf("temperature was not held: digest %q", got)
	}
}

func TestEmptyToolsAndResponseFormatConformanceVector(t *testing.T) {
	var body map[string]any
	if err := json.Unmarshal([]byte(`{"messages":[{"role":"system","content":"Answer with the option letter only. Do not explain."}],"tools":[],"response_format":{}}`), &body); err != nil {
		t.Fatal(err)
	}
	r := FromRequest(body, "shim", "1")
	if r.HarnessIdentity != "eeb813c17bed213fe02c7100" {
		t.Errorf("harness identity = %q", r.HarnessIdentity)
	}
	for _, name := range []string{"tool_schemas", "readout", "decoding"} {
		if got := r.Absent[name]; got != (Absence{Reason: "not_provided"}) {
			t.Errorf("%s absence = %+v", name, got)
		}
		if _, held := r.Parts[name]; held {
			t.Errorf("held empty %s", name)
		}
		a := ToAttributes(r)
		if got := a["perigraph.absent."+name+".reason"]; got != "not_provided" {
			t.Errorf("%s wire reason = %v", name, got)
		}
		if _, present := a["perigraph.part."+name+".digest"]; present {
			t.Errorf("emitted digest for empty %s", name)
		}
	}
}

func TestWhitespaceInstructionUsesJoinedRawText(t *testing.T) {
	whiteSpace := "\u0009\u000A\u000B\u000C\u000D\u0020\u0085\u00A0\u1680" +
		"\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200A" +
		"\u2028\u2029\u202F\u205F\u3000"
	r := FromRequest(map[string]any{"messages": []any{
		map[string]any{"role": "system", "content": whiteSpace},
		map[string]any{"role": "system", "content": ""},
	}}, "shim", "1")
	if got := r.Absent["instruction"]; got != (Absence{Reason: "not_provided"}) ||
		r.HarnessIdentity != "" {
		t.Fatalf("joined whitespace instruction: absence %+v, identity %q", got, r.HarnessIdentity)
	}

	text := "\u3000Keep this.\u0085"
	r = FromRequest(map[string]any{"messages": []any{
		map[string]any{"role": "system", "content": text},
		map[string]any{"role": "system", "content": ""},
	}}, "shim", "1")
	raw := text + "\n"
	wantDigest := handSHA(raw)
	if got := r.Parts["instruction"].Digest; got != wantDigest {
		t.Errorf("instruction digest = %q, want digest of untrimmed joined text %q", got, wantDigest)
	}
	if want := handSHA("instruction=" + wantDigest + ";")[:24]; r.HarnessIdentity != want {
		t.Errorf("harness identity = %q, want %q", r.HarnessIdentity, want)
	}

	// U+200B is not in the specified White_Space property.
	r = FromRequest(map[string]any{"messages": []any{
		map[string]any{"role": "system", "content": "\u200B"},
	}}, "shim", "1")
	if r.Parts["instruction"].Digest != handSHA("\u200B") || r.HarnessIdentity == "" {
		t.Error("treated non-White_Space character as an empty instruction")
	}
}

func TestEmptyFormatDoesNotMaskSamplerOrMalformedFormat(t *testing.T) {
	r := FromRequest(map[string]any{
		"response_format": map[string]any{},
		"temperature":     0.0,
	}, "shim", "1")
	if got := r.Absent["readout"]; got != (Absence{Reason: "not_provided"}) {
		t.Errorf("empty readout absence = %+v", got)
	}
	if got := r.Parts["decoding"].Digest; got != handSHA(`{"temperature":0}`) {
		t.Errorf("decoding digest = %q, want sampler alone", got)
	}

	r = FromRequest(map[string]any{
		"response_format": []any{},
		"temperature":     0.0,
	}, "shim", "1")
	for _, name := range []string{"readout", "decoding"} {
		if got := r.Absent[name]; got.Reason != "extraction_failed" ||
			!strings.Contains(got.Detail, "response_format") {
			t.Errorf("malformed %s absence = %+v", name, got)
		}
	}
}
