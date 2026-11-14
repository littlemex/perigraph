package perigraph

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCanonicalFixture(t *testing.T) {
	data, err := os.ReadFile(filepath.Join("..", "spec", "fixtures", "canonical_value.json"))
	if os.IsNotExist(err) {
		t.Skip("repository fixtures are not present")
	}
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name      string `json:"name"`
			JSON      string `json:"json"`
			Canonical string `json:"canonical"`
			SHA256    string `json:"sha256"`
			Fails     string `json:"fails"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) {
			got, err := CanonicalJSON([]byte(tc.JSON))
			if tc.Fails != "" {
				if err == nil || err.Error() != tc.Fails {
					t.Fatalf("got %q, %v; want failure %q", got, err, tc.Fails)
				}
				return
			}
			if err != nil || got != tc.Canonical || handSHA(got) != tc.SHA256 {
				t.Fatalf("got %q, %v; want %q (%s)", got, err, tc.Canonical, tc.SHA256)
			}
		})
	}
}

func TestR17bControls(t *testing.T) {
	makeBody := func(system bool, controls string) []byte {
		messages := `[{"role":"user","content":"Message: I lost my card"}]`
		if system {
			messages = `[{"role":"system","content":"Reply with exactly one intent name from the list and nothing else."},{"role":"user","content":"Message: I lost my card"}]`
		}
		return []byte(`{"messages":` + messages + `,` + controls + `}`)
	}
	h0 := FromRequestJSON(makeBody(true, `"max_tokens":32,"chat_template_kwargs":{"enable_thinking":false}`), "shim", "1")
	h3 := FromRequestJSON(makeBody(true, `"max_tokens":256,"chat_template_kwargs":{"enable_thinking":true}`), "shim", "1")
	if h0.HarnessIdentity == "" || h3.HarnessIdentity == "" || h0.HarnessIdentity == h3.HarnessIdentity {
		t.Fatal("H0 and H3 have the same identity")
	}
	reordered := FromRequestJSON(makeBody(true, `"chat_template_kwargs":{"enable_thinking":true},"max_tokens":256.0`), "shim", "1")
	if reordered.HarnessIdentity != h3.HarnessIdentity {
		t.Fatal("canonical controls split reordered or 256.0 request")
	}
	alone := FromRequestJSON(makeBody(false, `"max_tokens":256,"chat_template_kwargs":{"enable_thinking":true}`), "shim", "1")
	if alone.HarnessIdentity != "" || alone.Parts["generation_controls"].Digest == "" {
		t.Fatal("controls alone established an identity or were not recorded")
	}
}

func TestCanonicalFailuresArePartLocal(t *testing.T) {
	for _, value := range []string{"9007199254740993", "1e400", `"\ud800"`} {
		r := FromRequestJSON([]byte(`{"messages":[{"role":"system","content":"Answer."}],"max_tokens":`+value+`,"temperature":0}`), "shim", "1")
		a := r.Absent["generation_controls"]
		if a.Reason != "extraction_failed" || !strings.Contains(a.Detail, "max_tokens holds ") ||
			r.HarnessIdentity != "" || r.Parts["decoding"].Digest != handSHA(`{"temperature":0}`) {
			t.Fatalf("%s: control failure %+v, record %+v", value, a, r)
		}
	}
	r := FromRequestJSON([]byte(`{"messages":[{"role":"system","content":"Answer."}],"logit_bias":{"x":9007199254740993}}`), "shim", "1")
	if r.Absent["decoding"].Reason != "extraction_failed" || r.HarnessIdentity == "" {
		t.Fatal("decoding failure withdrew identity")
	}
}

func TestUnlistedRecognisedNowhereAndInvalidName(t *testing.T) {
	r := FromRequestJSON([]byte(`{"messages":[{"role":"system","content":"Answer."}],"seed":7,"vendor":null,"bad,name":1,"__proto__":2}`), "shim", "1")
	a := ToAttributes(r)
	if a["perigraph.request.unlisted"] != "__proto__,vendor" ||
		a["perigraph.request.unlisted_omitted"] != 1 {
		t.Fatalf("unlisted attributes: %v", a)
	}
}
