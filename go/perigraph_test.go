package perigraph

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"reflect"
	"strings"
	"testing"
)

func handSHA(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

func TestRequestInstructionAndAbsences(t *testing.T) {
	r := FromRequest(map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "日本語"},
			map[string]any{"role": "user", "content": "question"},
			map[string]any{"role": "system", "content": " second "},
		},
		"temperature": 0.0,
		"tools":       []any{},
	}, "shim", "1")
	content := handSHA("日本語\n second ")
	if got := r.Parts["instruction"].Digest; got != content {
		t.Fatalf("raw joined UTF-8 instruction digest: %s", got)
	}
	want := handSHA("instruction=" + content + ";")[:24]
	if r.HarnessIdentity != want {
		t.Fatalf("harness identity: got %s, want %s", r.HarnessIdentity, want)
	}
	if p := r.Parts["decoding"]; p.Boundary != "parsed" || p.Sourcing != "in_the_request" {
		t.Errorf("decoding: %+v", p)
	}
	if got := r.Absent["tool_schemas"]; got != (Absence{Reason: "not_provided"}) {
		t.Errorf("empty tools absence: %+v", got)
	}
	if got := r.Absent["request_template"]; got != (Absence{Reason: "not_provided"}) {
		t.Errorf("missing template absence: %+v", got)
	}
	if _, held := r.Parts["tool_schemas"]; held {
		t.Error("held an empty tools array")
	}
	if r.Absent["tool_extension"].Reason != "not_observable" ||
		r.Absent["tool_trace"].Reason != "not_provided" ||
		r.Absent["context_partitioning"].Reason != "not_provided" ||
		r.Absent["readout"].Reason != "not_provided" {
		t.Fatal("absence reasons or their attribution changed")
	}
	if r.Model.ModelIdentity != "" || len(r.Model.Absent) != 4 {
		t.Fatal("a request cannot observe the model")
	}
}

func TestPartialAndMalformedRequest(t *testing.T) {
	empty := FromRequest(map[string]any{}, "shim", "1")
	if empty.HarnessIdentity != "" || len(empty.Parts) != 0 ||
		len(empty.Absent) != 11 || empty.Status != "complete" {
		t.Fatalf("partial record not emitted: %+v", empty)
	}
	a := ToAttributes(empty)
	for _, name := range []string{
		"perigraph.harness_identity", "perigraph.model_identity",
		"perigraph.artifact_identity",
	} {
		if _, ok := a[name]; ok {
			t.Errorf("emitted empty identity %s", name)
		}
	}
	if a["perigraph.spec_version"] != 3 {
		t.Fatal("wrong spec version")
	}
	bad := FromRequest(map[string]any{"messages": "unreadable"}, "shim", "1")
	if a := bad.Absent["instruction"]; a.Reason != "extraction_failed" || a.Detail == "" {
		t.Fatalf("unexplained extraction failure: %+v", a)
	}
	if bad.Status != "complete" {
		t.Fatal("bad input must not prevent a record")
	}
}

func TestToolMessagesAreNotReadAsTrace(t *testing.T) {
	body := map[string]any{"messages": []any{
		map[string]any{"role": "system", "content": "Do it"},
		map[string]any{"role": "tool", "content": "one"},
	}}
	first := FromRequest(body, "shim", "1")
	body["messages"].([]any)[1] = map[string]any{"role": "tool", "content": "two"}
	second := FromRequest(body, "shim", "1")
	if first.Absent["tool_trace"].Reason != "not_provided" ||
		second.Absent["tool_trace"].Reason != "not_provided" ||
		first.HarnessIdentity != second.HarnessIdentity {
		t.Fatal("earlier tool messages must not be read as a trace")
	}
	if _, ok := ToAttributes(first)["perigraph.part.tool_trace.digest"]; ok {
		t.Fatal("transmitted an inferred trace")
	}
}

func TestModelDigestsAndIdentities(t *testing.T) {
	fileA := handSHA("a")
	fileB := handSHA("b")
	files := [][2]string{{"z.bin", fileB}, {"a.bin", fileA}}
	checkpoint, err := CheckpointDigest(files)
	if err != nil {
		t.Fatal(err)
	}
	manifest := "a.bin\t" + fileA + "\n" + "z.bin\t" + fileB + "\n"
	if checkpoint != handSHA(manifest) {
		t.Fatal("checkpoint serialization")
	}
	precision, err := PrecisionDigest(map[string]string{
		"quantisation": "none", "dtype.bfloat16": "3", "device": "cuda",
	})
	if err != nil {
		t.Fatal(err)
	}
	if precision != handSHA("device=cuda\ndtype.bfloat16=3\nquantisation=none\n") {
		t.Fatal("precision serialization")
	}
	runtime, err := RuntimeDigest(map[string]string{"torch": "2.1", "numpy": "1.0"})
	if err != nil {
		t.Fatal(err)
	}
	if runtime != handSHA("numpy==1.0\ntorch==2.1\n") {
		t.Fatal("runtime serialization")
	}
	m, err := Loaded(checkpoint, precision, runtime, "option_scores")
	if err != nil {
		t.Fatal(err)
	}
	modelBytes := "answer_mode=" + handSHA("option_scores") + ";" +
		"checkpoint=" + checkpoint + ";" +
		"precision=" + precision + ";" +
		"runtime=" + runtime + ";"
	if m.ModelIdentity != handSHA(modelBytes)[:24] ||
		m.ArtifactIdentity != handSHA("checkpoint=" + checkpoint + ";")[:24] {
		t.Fatal("model or artifact identity serialization")
	}
	for _, p := range m.Parts {
		if p.Sourcing != "loaded_by_us" {
			t.Fatal("model part not sourced from this load")
		}
	}
	r := FromRequest(map[string]any{}, "shim", "1")
	r.Model = m
	a := ToAttributes(r)
	if a["perigraph.model_identity"] != m.ModelIdentity ||
		a["perigraph.artifact_identity"] != m.ArtifactIdentity {
		t.Fatal("model identities omitted from wire form")
	}
	if _, ok := a["perigraph.model.answer_mode.boundary"]; ok {
		t.Fatal("model parts have no boundary")
	}
}

func TestRequiredSenderRefusals(t *testing.T) {
	sha := handSHA("bytes")
	for _, name := range []string{"x\ty", "x\ny", "../outside", "/absolute"} {
		if _, err := CheckpointDigest([][2]string{{name, sha}}); err == nil {
			t.Errorf("accepted bad path %q", name)
		}
	}
	// A backslash is a filename character, not a separator, in a POSIX path.
	if got, err := CheckpointDigest([][2]string{{"x\\y", sha}}); err != nil {
		t.Errorf("refused valid POSIX path: %v", err)
	} else if want := handSHA("x\\y\t" + sha + "\n"); got != want {
		t.Errorf("backslash path digest: got %s, want %s", got, want)
	}
	if _, err := CheckpointDigest([][2]string{{"same", sha}, {"same", sha}}); err == nil {
		t.Fatal("accepted duplicate file")
	}
	if _, err := PrecisionDigest(map[string]string{
		"dtype.bfloat16": "auto", "device": "cuda", "quantisation": "none",
	}); err == nil {
		t.Fatal("accepted unresolved precision")
	}
	if _, err := Loaded(sha, sha, sha, "another_mode"); err == nil {
		t.Fatal("accepted unknown answer mode")
	}
	if _, err := Loaded("short", sha, sha, "generated_text"); err == nil {
		t.Fatal("accepted truncated content digest")
	}
}

func TestVocabularyLists(t *testing.T) {
	expected := map[string][]string{
		"parts": {"instruction", "request_template", "tool_schemas", "tool_extension", "tool_trace",
			"loop", "turn_budget", "retry_policy", "readout", "decoding", "context_partitioning"},
		"model_parts":  {"checkpoint", "precision", "runtime", "answer_mode"},
		"answer_modes": {"generated_text", "option_scores", "classifier_output"},
		"sourcing": {"in_the_request", "loaded_by_us", "pulled_by_us",
			"pushed_by_owner", "not_observable"},
		"boundaries":                 {"transport", "parsed", "model_visible"},
		"never_identifying":          {"tool_trace"},
		"refines_only":               {"request_template"},
		"must_be_known_for_identity": {"instruction", "request_template"},
		"absence_reasons":            {"not_provided", "not_reachable", "extraction_failed", "redacted", "not_observable"},
		"status":                     {"complete", "aborted", "collector_failed"},
		"context_crossings":          {"nothing", "briefs_and_results", "whole_history"},
		"tool_determinism":           {"declared_deterministic", "known_to_vary", "unstated"},
		"billed_legs":                {"fresh_in", "cached_in", "cache_write", "generation"},
	}
	data, err := VocabularyJSON()
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if document["spec_version"] != float64(3) || document["namespace"] != "perigraph" {
		t.Fatal("wrong embedded vocabulary version or namespace")
	}
	for section, want := range expected {
		got, err := vocabularyValues(section)
		if err != nil || !reflect.DeepEqual(got, want) {
			t.Errorf("%s: got %v (%v), want %v", section, got, err, want)
		}
	}
	for _, name := range []string{"parts", "model_parts", "answer_modes"} {
		if inVocabulary(name, "not_in_the_spec") {
			t.Errorf("%s accepted an unknown value", name)
		}
	}
}

func TestWireManifestAndCollectorStatus(t *testing.T) {
	r := FromRequest(map[string]any{}, "collector", "v1")
	if !strings.Contains(strings.Join(r.CollectorReaches, ","), "request_template") {
		t.Fatal("request template missing from static manifest")
	}
	for _, name := range r.CollectorReaches {
		if name == "tool_trace" {
			t.Fatal("request collector claims to read a tool trace")
		}
	}
	r.CollectorReaches = nil
	r.Status = "collector_failed"
	a := ToAttributes(r)
	if a["perigraph.collector_reaches"] != "" ||
		a["perigraph.status"] != "collector_failed" {
		t.Fatal("incorrect empty manifest or terminal status")
	}
	for key, value := range a {
		if !strings.HasPrefix(key, "perigraph.") {
			t.Fatalf("unprefixed attribute %s", key)
		}
		switch value.(type) {
		case string, int, float64, bool:
		default:
			t.Fatalf("non-scalar attribute %s: %T", key, value)
		}
	}
}
