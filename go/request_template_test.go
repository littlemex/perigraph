package perigraph

import (
	"strings"
	"testing"
)

func TestTemplateRefinesInstructionIdentity(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "One word."},
			map[string]any{"role": "user", "content": "Headline: Stocks rise"},
		},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"Headline: ", ""}},
		}},
	}
	held := FromRequest(body, "shim", "1")
	payload := "2:6:system0:4:user2:10:Headline: 0:"
	templateDigest := handSHA(payload)
	if got := held.Parts["request_template"]; got.Sourcing != "in_the_request" ||
		got.Boundary != "model_visible" || got.Digest != templateDigest || got.Label != "" {
		t.Fatalf("template part = %+v", got)
	}
	instructionDigest := handSHA("One word.")
	want := handSHA("instruction=" + instructionDigest + ";request_template=" + templateDigest + ";")[:24]
	if held.HarnessIdentity != want {
		t.Fatalf("identity = %q, want %q", held.HarnessIdentity, want)
	}
	attributes := ToAttributes(held)
	if attributes["perigraph.spec_version"] != 3 ||
		attributes["perigraph.part.request_template.digest"] != templateDigest ||
		!strings.Contains(attributes["perigraph.collector_reaches"].(string), "request_template") {
		t.Fatal("template absent from version-3 wire record or manifest")
	}

	delete(body, "perigraph_template")
	without := FromRequest(body, "shim", "1")
	if without.HarnessIdentity == "" || without.HarnessIdentity == held.HarnessIdentity {
		t.Fatal("template did not refine the instruction identity")
	}
	if without.Absent["request_template"].Reason != "not_provided" {
		t.Fatal("missing template not reported")
	}
}

func TestTemplateAloneHasNoIdentity(t *testing.T) {
	body := map[string]any{
		"messages": []any{map[string]any{"role": "user", "content": "Q: item"}},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "user", "fixed": []any{"Q: ", ""}},
		}},
	}
	r := FromRequest(body, "shim", "1")
	if _, held := r.Parts["request_template"]; !held || r.HarnessIdentity != "" {
		t.Fatalf("template alone: %+v", r)
	}
	if _, present := ToAttributes(r)["perigraph.harness_identity"]; present {
		t.Fatal("emitted identity established by template alone")
	}
}

func TestContradictedTemplateWithdrawsIdentity(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Do not quote this."},
			map[string]any{"role": "user", "content": "Actual item"},
		},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"Do not quote this.", ""}},
		}},
	}
	r := FromRequest(body, "shim", "1")
	a := r.Absent["request_template"]
	if a.Reason != "extraction_failed" || !strings.Contains(a.Detail, "check 9") ||
		!strings.Contains(a.Detail, "messages[1]") ||
		strings.Contains(a.Detail, "Do not quote this.") || r.HarnessIdentity != "" {
		t.Fatalf("contradicted template: absence %+v, identity %q", a, r.HarnessIdentity)
	}
	if _, held := r.Parts["instruction"]; !held {
		t.Fatal("contradiction incorrectly withdrew the instruction part")
	}
}

func TestTemplatePrefixAndSuffixHaveDifferentDigests(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Answer."},
			map[string]any{"role": "user", "content": "AA"},
		},
	}
	makeTemplate := func(fixed []any) Record {
		body["perigraph_template"] = map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": fixed},
		}}
		return FromRequest(body, "shim", "1")
	}
	prefix := makeTemplate([]any{"A", ""})
	suffix := makeTemplate([]any{"", "A"})
	if prefix.Parts["request_template"].Digest == suffix.Parts["request_template"].Digest ||
		prefix.HarnessIdentity == suffix.HarnessIdentity ||
		prefix.HarnessIdentity == "" || suffix.HarnessIdentity == "" {
		t.Fatal("prefix and suffix placement were joined")
	}
}

func TestUnformattedEntriesAndByteLengths(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Answer."},
			map[string]any{"role": "developer", "content": "not named"},
			map[string]any{"role": "user", "content": "猫: item"},
		},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "developer"},
			map[string]any{"role": "user", "fixed": []any{"猫: ", ""}},
		}},
	}
	first := FromRequest(body, "shim", "1")
	payload := "3:6:system0:9:developer0:4:user2:5:猫: 0:"
	if first.Parts["request_template"].Digest != handSHA(payload) {
		t.Fatal("untemplated-entry framing or UTF-8 byte length is wrong")
	}
	body["messages"].([]any)[1].(map[string]any)["content"] = "changed, but still not named"
	second := FromRequest(body, "shim", "1")
	if second.Parts["request_template"].Digest != first.Parts["request_template"].Digest ||
		second.HarnessIdentity != first.HarnessIdentity {
		t.Fatal("untemplated content changed the identity")
	}
}

func TestEmptyTemplateChecksBeforeEmptiness(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Answer."},
			map[string]any{"role": "user", "content": "item"},
		},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"\u3000", ""}},
		}},
	}
	failed := FromRequest(body, "shim", "1")
	if failed.Absent["request_template"].Reason != "extraction_failed" ||
		failed.HarnessIdentity != "" {
		t.Fatal("unmatched whitespace-only template was treated as missing")
	}
	body["messages"].([]any)[1].(map[string]any)["content"] = "\u3000item"
	empty := FromRequest(body, "shim", "1")
	if empty.Absent["request_template"] != (Absence{Reason: "not_provided"}) ||
		empty.HarnessIdentity == "" {
		t.Fatal("verified whitespace-only template was not treated as missing")
	}
}

func TestTemplateValidationFailures(t *testing.T) {
	for _, tc := range []struct {
		name     string
		template any
		check    string
	}{
		{"not object", "private text", "check 1"},
		{"extra member", map[string]any{"messages": []any{}, "extra": "private text"}, "check 1"},
		{"wrong count", map[string]any{"messages": []any{}}, "check 2"},
		{"entry member", map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"", ""}, "extra": "private text"},
		}}, "check 3"},
		{"old entry member", map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "segments": []any{"", ""}},
		}}, "check 3"},
		{"role mismatch", map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "assistant"},
		}}, "check 4"},
		{"system fixed", map[string]any{"messages": []any{
			map[string]any{"role": "system", "fixed": []any{"private text"}},
			map[string]any{"role": "user"},
		}}, "check 5"},
		{"interior empty", map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"", "", ""}},
		}}, "check 6"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r := FromRequest(map[string]any{
				"messages": []any{
					map[string]any{"role": "system", "content": "Answer."},
					map[string]any{"role": "user", "content": "item"},
				},
				"perigraph_template": tc.template,
			}, "shim", "1")
			a := r.Absent["request_template"]
			if a.Reason != "extraction_failed" || !strings.Contains(a.Detail, tc.check) ||
				strings.Contains(a.Detail, "private text") || r.HarnessIdentity != "" {
				t.Fatalf("absence %+v, identity %q", a, r.HarnessIdentity)
			}
		})
	}
}

func TestTemplateOneFixedStringAndNonWhiteSpace(t *testing.T) {
	body := map[string]any{
		"messages": []any{
			map[string]any{"role": "system", "content": "Answer."},
			map[string]any{"role": "user", "content": "\uFEFF"},
		},
		"perigraph_template": map[string]any{"messages": []any{
			map[string]any{"role": "system"},
			map[string]any{"role": "user", "fixed": []any{"\uFEFF"}},
		}},
	}
	r := FromRequest(body, "shim", "1")
	if _, ok := r.Parts["request_template"]; !ok || r.HarnessIdentity == "" {
		t.Fatal("U+FEFF incorrectly treated as White_Space")
	}
	body["messages"].([]any)[1].(map[string]any)["content"] = "\uFEFFitem"
	r = FromRequest(body, "shim", "1")
	if r.Absent["request_template"].Reason != "extraction_failed" || r.HarnessIdentity != "" {
		t.Fatal("one fixed string incorrectly matched longer content")
	}
}

func TestKnownIdentityPartWithOtherSourcing(t *testing.T) {
	r := FromRequest(map[string]any{
		"messages": []any{map[string]any{"role": "system", "content": "Answer."}},
	}, "shim", "1")
	delete(r.Absent, "request_template")
	r.Parts["request_template"] = Part{
		Sourcing: "pushed_by_owner", Boundary: "model_visible", Digest: handSHA("claim"),
	}
	if got, want := harnessIdentity(r), identity(map[string]string{
		"instruction": r.Parts["instruction"].Digest,
	}); got != want {
		t.Fatalf("other sourcing: got %q, want %q", got, want)
	}
	delete(r.Parts, "request_template")
	if got := harnessIdentity(r); got != "" {
		t.Fatalf("unmentioned required part gave identity %q", got)
	}
}
