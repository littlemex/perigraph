package perigraph

import (
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"path"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"unicode/utf8"
)

//go:embed spec/vocabularies.json
var vocabularyFile embed.FS

// VocabularyJSON returns the embedded vocabulary document.
func VocabularyJSON() ([]byte, error) {
	return vocabularyFile.ReadFile("spec/vocabularies.json")
}

var (
	vocabularyOnce sync.Once
	vocabulary     map[string]any
	vocabularyErr  error
)

func loadVocabulary() {
	data, err := VocabularyJSON()
	if err != nil {
		vocabularyErr = err
		return
	}
	vocabularyErr = json.Unmarshal(data, &vocabulary)
}

func vocabularyValues(section string) ([]string, error) {
	vocabularyOnce.Do(loadVocabulary)
	if vocabularyErr != nil {
		return nil, vocabularyErr
	}
	entry, ok := vocabulary[section].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("missing vocabulary %q", section)
	}
	raw, ok := entry["values"].([]any)
	if !ok {
		return nil, fmt.Errorf("missing values for %q", section)
	}
	out := make([]string, 0, len(raw))
	for _, value := range raw {
		s, ok := value.(string)
		if !ok {
			return nil, fmt.Errorf("non-string value in %q", section)
		}
		out = append(out, s)
	}
	return out, nil
}

func inVocabulary(section, value string) bool {
	values, err := vocabularyValues(section)
	if err != nil {
		return false
	}
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}

func bindingMembers() map[string][]string {
	vocabularyOnce.Do(loadVocabulary)
	result := make(map[string][]string)
	if vocabularyErr != nil {
		return result
	}
	bindings, _ := vocabulary["bindings"].(map[string]any)
	binding, _ := bindings["openai_chat_completions"].(map[string]any)
	members, _ := binding["members"].(map[string]any)
	for name, raw := range members {
		list, _ := raw.([]any)
		for _, part := range list {
			if s, ok := part.(string); ok {
				result[name] = append(result[name], s)
			}
		}
		if _, ok := result[name]; !ok {
			result[name] = nil
		}
	}
	return result
}

// Part is a held harness fact. Digest is the full lowercase SHA-256 hex digest.
type Part struct {
	Sourcing       string
	Boundary       string
	Digest         string
	Label          string
	ReadLagSeconds *float64
}

// ModelPart is a held fact about the model that answered.
type ModelPart struct {
	Sourcing       string
	Digest         string
	Label          string
	ReadLagSeconds *float64
}

// Absence describes a missing part.
type Absence struct {
	Reason string
	Detail string
}

// ModelHalf describes the model parts. Its identities are empty when absent.
type ModelHalf struct {
	Parts            map[string]ModelPart
	Absent           map[string]Absence
	ModelIdentity    string
	ArtifactIdentity string
}

// Record describes one call. HasUnlisted distinguishes a non-object body from
// an object with no unlisted members.
type Record struct {
	SpecVersion      int
	Collector        string
	CollectorVersion string
	CollectorReaches []string
	Status           string
	Parts            map[string]Part
	Absent           map[string]Absence
	HarnessIdentity  string
	Model            ModelHalf
	HasUnlisted      bool
	Unlisted         []string
	UnlistedOmitted  int
}

func digest(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func identity(digests map[string]string) string {
	if len(digests) == 0 {
		return ""
	}
	names := make([]string, 0, len(digests))
	for name := range digests {
		names = append(names, name)
	}
	sort.Strings(names)
	var b strings.Builder
	for _, name := range names {
		b.WriteString(name)
		b.WriteByte('=')
		b.WriteString(digests[name])
		b.WriteByte(';')
	}
	return digest([]byte(b.String()))[:24]
}

func specWhiteSpace(r rune) bool {
	vocabularyOnce.Do(loadVocabulary)
	if vocabularyErr != nil {
		return false
	}
	definition, ok := vocabulary["white_space"].(map[string]any)
	if !ok {
		return false
	}
	points, ok := definition["code_points"].([]any)
	if !ok {
		return false
	}
	for _, point := range points {
		if n, ok := point.(float64); ok && rune(n) == r {
			return true
		}
	}
	return false
}

func trimSpecWhiteSpace(s string) string {
	return strings.TrimFunc(s, specWhiteSpace)
}

func parsed(value any) (Part, error) {
	// A parsed digest is collector-local.
	data, err := json.Marshal(value)
	if err != nil {
		return Part{}, err
	}
	return Part{Sourcing: "in_the_request", Boundary: "parsed", Digest: digest(data)}, nil
}

func jsonType(value any) string {
	switch value := value.(type) {
	case nil:
		return "null"
	case bool:
		return "boolean"
	case string:
		return "string"
	case []any:
		return "array"
	case map[string]any:
		if value == nil {
			return "null"
		}
		return "object"
	case json.Number, float64, float32, int, int8, int16, int32, int64,
		uint, uint8, uint16, uint32, uint64:
		return "number"
	default:
		return fmt.Sprintf("non-JSON value (%T)", value)
	}
}

func wrongType(where string, value any, expected string) Absence {
	return Absence{
		Reason: "extraction_failed",
		Detail: fmt.Sprintf("%s: found %s, expected %s", where, jsonType(value), expected),
	}
}

func failed(where string) Absence {
	return Absence{Reason: "extraction_failed", Detail: "could not encode " + where}
}

func requestRecord(collector, version string) Record {
	r := Record{
		SpecVersion:      4,
		Collector:        collector,
		CollectorVersion: version,
		CollectorReaches: []string{"instruction", "request_template", "tool_schemas", "generation_controls", "decoding"},
		Status:           "complete",
		Parts:            make(map[string]Part),
		Absent:           make(map[string]Absence),
		Model: ModelHalf{
			Parts:  make(map[string]ModelPart),
			Absent: make(map[string]Absence),
		},
	}
	for _, name := range []string{"checkpoint", "precision", "runtime", "answer_mode"} {
		r.Model.Absent[name] = Absence{Reason: "not_observable"}
	}
	for _, name := range []string{"loop", "turn_budget", "retry_policy", "readout", "context_partitioning", "tool_trace"} {
		r.Absent[name] = Absence{Reason: "not_provided"}
	}
	r.Absent["tool_extension"] = Absence{Reason: "not_observable"}
	return r
}

// FromRequest observes an already-decoded JSON object. A nil map represents
// JSON null. Use FromRequestJSON when the original JSON text is available.
func FromRequest(body map[string]any, collector, version string) Record {
	return FromRequestValue(body, collector, version)
}

// FromRequestValue observes a decoded value. Unlike FromRequestJSON it cannot
// detect an unpaired surrogate escape already replaced by the JSON decoder.
func FromRequestValue(body any, collector, version string) Record {
	return collectRequest(body, nil, collector, version)
}

// FromRequestJSON observes JSON text. Top-level members are decoded as raw
// messages so a canonical member's failure cannot fail another part. The last
// occurrence of a duplicate top-level member wins.
func FromRequestJSON(raw []byte, collector, version string) Record {
	bad := func() Record {
		r := requestRecord(collector, version)
		for _, name := range r.CollectorReaches {
			r.Absent[name] = Absence{Reason: "extraction_failed", Detail: "request body: invalid JSON"}
		}
		return r
	}
	if !utf8.Valid(raw) || len(raw) >= 3 && string(raw[:3]) == "\xef\xbb\xbf" {
		return bad()
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.UseNumber()
	var body any
	if err := decoder.Decode(&body); err != nil {
		return bad()
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return bad()
	}
	if _, ok := body.(map[string]any); !ok {
		return collectRequest(body, nil, collector, version)
	}
	var members map[string]json.RawMessage
	other := json.NewDecoder(strings.NewReader(string(raw)))
	other.UseNumber()
	if err := other.Decode(&members); err != nil {
		return bad()
	}
	return collectRequest(body, members, collector, version)
}

func unlistedNames(object map[string]any, r *Record) {
	r.HasUnlisted = true
	members := bindingMembers()
	vocabularyOnce.Do(loadVocabulary)
	rule, _ := vocabulary["unlisted_names"].(map[string]any)
	pattern, _ := rule["pattern"].(string)
	maximum, _ := rule["max"].(float64)
	re, err := regexp.Compile(pattern)
	if err != nil {
		return
	}
	names := make([]string, 0)
	for name := range object {
		if _, recognised := members[name]; !recognised {
			names = append(names, name)
		}
	}
	sort.Slice(names, func(i, j int) bool { return utf16Less(names[i], names[j]) })
	for _, name := range names {
		if re.MatchString(name) && len(r.Unlisted) < int(maximum) {
			r.Unlisted = append(r.Unlisted, name)
		} else {
			r.UnlistedOmitted++
		}
	}
}

func canonicalRequestPart(object map[string]any, raw map[string]json.RawMessage, name string) (Part, *Absence) {
	payload := make(map[string]any)
	labels := make([]string, 0)
	for member, parts := range bindingMembers() {
		reads := false
		for _, part := range parts {
			if part == name {
				reads = true
			}
		}
		value, present := object[member]
		if !reads || !present || value == nil {
			continue
		}
		var text string
		var err error
		if raw != nil {
			text, err = CanonicalJSON(raw[member])
		} else {
			text, err = canonicalValue(value)
		}
		if err != nil {
			a := Absence{Reason: "extraction_failed", Detail: member + " holds " + err.Error()}
			return Part{}, &a
		}
		// RawMessage preserves the canonical rendering while the containing
		// object is sorted and serialized by the same canonical writer.
		payload[member] = canonicalFragment(text)
		labels = append(labels, member)
	}
	if len(labels) == 0 {
		return Part{}, &Absence{Reason: "not_provided"}
	}
	sort.Strings(labels)
	text, err := canonicalValue(payload)
	if err != nil {
		a := Absence{Reason: "extraction_failed", Detail: "canonical object holds " + err.Error()}
		return Part{}, &a
	}
	return Part{
		Sourcing: "in_the_request", Boundary: "canonical_value",
		Digest: digest([]byte(text)), Label: strings.Join(labels, ","),
	}, nil
}

func collectRequest(body any, raw map[string]json.RawMessage, collector, version string) Record {
	r := requestRecord(collector, version)
	object, ok := body.(map[string]any)
	if !ok || object == nil {
		for _, name := range r.CollectorReaches {
			r.Absent[name] = wrongType("request body", body, "object")
		}
		return r
	}
	unlistedNames(object, &r)

	if part, absence := readRequestTemplate(object); absence != nil {
		r.Absent["request_template"] = *absence
	} else {
		r.Parts["request_template"] = part
	}

	if value := object["messages"]; value == nil {
		r.Absent["instruction"] = Absence{Reason: "not_provided"}
	} else if messages, ok := value.([]any); !ok {
		r.Absent["instruction"] = wrongType("messages", value, "array")
	} else {
		var structural *Absence
		for i, item := range messages {
			where := fmt.Sprintf("messages[%d]", i)
			m, ok := item.(map[string]any)
			if !ok || m == nil {
				a := wrongType(where, item, "object")
				structural = &a
				break
			}
			role, exists := m["role"]
			if !exists {
				a := Absence{"extraction_failed", where + ".role: missing; expected string"}
				structural = &a
				break
			}
			if _, ok := role.(string); !ok {
				a := wrongType(where+".role", role, "string")
				structural = &a
				break
			}
		}
		if structural != nil {
			r.Absent["instruction"] = *structural
		} else {
			var systems []string
			var failure *Absence
			for i, item := range messages {
				m := item.(map[string]any)
				if m["role"].(string) != "system" {
					continue
				}
				where := fmt.Sprintf("messages[%d]", i)
				content, exists := m["content"]
				if !exists {
					if failure == nil {
						a := Absence{"extraction_failed", where + ".content: missing; expected string"}
						failure = &a
					}
				} else if text, ok := content.(string); ok {
					systems = append(systems, text)
				} else if failure == nil {
					a := wrongType(where+".content", content, "string")
					failure = &a
				}
			}
			if failure != nil {
				r.Absent["instruction"] = *failure
			} else if len(systems) == 0 {
				r.Absent["instruction"] = Absence{Reason: "not_provided"}
			} else {
				instruction := strings.Join(systems, "\n")
				if trimSpecWhiteSpace(instruction) == "" {
					r.Absent["instruction"] = Absence{Reason: "not_provided"}
				} else {
					r.Parts["instruction"] = Part{
						Sourcing: "in_the_request", Boundary: "model_visible",
						Digest: digest([]byte(instruction)),
					}
				}
			}
		}
	}

	if value := object["tools"]; value == nil {
		r.Absent["tool_schemas"] = Absence{Reason: "not_provided"}
	} else if tools, ok := value.([]any); !ok {
		r.Absent["tool_schemas"] = wrongType("tools", value, "array")
	} else {
		var failure *Absence
		for i, item := range tools {
			where := fmt.Sprintf("tools[%d]", i)
			tool, ok := item.(map[string]any)
			if !ok || tool == nil {
				a := wrongType(where, item, "object")
				failure = &a
				break
			}
			if function, exists := tool["function"]; exists {
				if f, ok := function.(map[string]any); !ok || f == nil {
					a := wrongType(where+".function", function, "object")
					failure = &a
					break
				}
			}
		}
		if failure != nil {
			r.Absent["tool_schemas"] = *failure
		} else if len(tools) == 0 {
			r.Absent["tool_schemas"] = Absence{Reason: "not_provided"}
		} else if p, err := parsed(tools); err != nil {
			r.Absent["tool_schemas"] = failed("tools")
		} else {
			r.Parts["tool_schemas"] = p
		}
	}

	for _, name := range []string{"generation_controls", "decoding"} {
		if part, absence := canonicalRequestPart(object, raw, name); absence != nil {
			r.Absent[name] = *absence
		} else {
			r.Parts[name] = part
		}
	}
	r.HarnessIdentity = harnessIdentity(r)
	return r
}

// ToAttributes encodes the flat, scalar-valued version-4 wire form.
func ToAttributes(r Record) map[string]any {
	a := map[string]any{
		"perigraph.spec_version":      4,
		"perigraph.collector":         r.Collector,
		"perigraph.collector_version": r.CollectorVersion,
		"perigraph.status":            r.Status,
	}
	reaches := append([]string(nil), r.CollectorReaches...)
	sort.Strings(reaches)
	a["perigraph.collector_reaches"] = strings.Join(reaches, ",")
	if r.HasUnlisted {
		a["perigraph.request.unlisted"] = strings.Join(r.Unlisted, ",")
		a["perigraph.request.unlisted_omitted"] = r.UnlistedOmitted
	}
	if r.HarnessIdentity != "" {
		a["perigraph.harness_identity"] = r.HarnessIdentity
	}
	if r.Model.ModelIdentity != "" {
		a["perigraph.model_identity"] = r.Model.ModelIdentity
	}
	if r.Model.ArtifactIdentity != "" {
		a["perigraph.artifact_identity"] = r.Model.ArtifactIdentity
	}
	for name, part := range r.Parts {
		prefix := "perigraph.part." + name + "."
		a[prefix+"sourcing"] = part.Sourcing
		a[prefix+"boundary"] = part.Boundary
		a[prefix+"digest"] = part.Digest
		if part.Label != "" {
			a[prefix+"label"] = part.Label
		}
		if part.ReadLagSeconds != nil {
			a[prefix+"read_lag_seconds"] = *part.ReadLagSeconds
		}
	}
	for name, absent := range r.Absent {
		prefix := "perigraph.absent." + name + "."
		a[prefix+"reason"] = absent.Reason
		if absent.Detail != "" {
			a[prefix+"detail"] = absent.Detail
		}
	}
	for name, part := range r.Model.Parts {
		prefix := "perigraph.model." + name + "."
		a[prefix+"sourcing"] = part.Sourcing
		a[prefix+"digest"] = part.Digest
		if part.Label != "" {
			a[prefix+"label"] = part.Label
		}
		if part.ReadLagSeconds != nil {
			a[prefix+"read_lag_seconds"] = *part.ReadLagSeconds
		}
	}
	for name, absent := range r.Model.Absent {
		prefix := "perigraph.model_absent." + name + "."
		a[prefix+"reason"] = absent.Reason
		if absent.Detail != "" {
			a[prefix+"detail"] = absent.Detail
		}
	}
	return a
}

func validSHA256(s string) bool {
	if len(s) != 64 {
		return false
	}
	_, err := hex.DecodeString(s)
	return err == nil && s == strings.ToLower(s)
}

// CheckpointDigest hashes a sorted file manifest. The caller supplies SHA-256
// digests of the actual files, not digests of descriptions of those files.
func CheckpointDigest(files [][2]string) (string, error) {
	entries := append([][2]string(nil), files...)
	sort.Slice(entries, func(i, j int) bool { return entries[i][0] < entries[j][0] })
	var b strings.Builder
	for i, entry := range entries {
		p, sha := entry[0], entry[1]
		if p == "" || strings.ContainsAny(p, "\t\n") || strings.HasPrefix(p, "/") ||
			p == "." || p == ".." || strings.HasPrefix(p, "../") || path.Clean(p) != p {
			return "", fmt.Errorf("invalid relative POSIX artifact path %q", p)
		}
		if i > 0 && entries[i-1][0] == p {
			return "", fmt.Errorf("duplicate artifact path %q", p)
		}
		if !validSHA256(sha) {
			return "", fmt.Errorf("invalid file SHA-256 for %q", p)
		}
		b.WriteString(p)
		b.WriteByte('\t')
		b.WriteString(sha)
		b.WriteByte('\n')
	}
	return digest([]byte(b.String())), nil
}

// PrecisionDigest hashes the transform observed after loading.
func PrecisionDigest(fields map[string]string) (string, error) {
	if fields["device"] == "" || fields["quantisation"] == "" {
		return "", errors.New("precision requires device and quantisation")
	}
	names := make([]string, 0, len(fields))
	dtypes := 0
	for name, value := range fields {
		trimmedValue := trimSpecWhiteSpace(value)
		if strings.ContainsAny(name+value, "\r\n") || trimmedValue == "" ||
			strings.EqualFold(trimmedValue, "auto") {
			return "", fmt.Errorf("unresolved or invalid precision field %q", name)
		}
		switch {
		case name == "device", name == "quantisation":
		case strings.HasPrefix(name, "dtype.") && len(name) > len("dtype."):
			dtype := trimSpecWhiteSpace(strings.TrimPrefix(name, "dtype."))
			if dtype == "" || strings.EqualFold(dtype, "auto") {
				return "", fmt.Errorf("unresolved dtype in precision field %q", name)
			}
			if _, err := strconv.ParseUint(value, 10, 64); err != nil {
				return "", fmt.Errorf("invalid parameter count for %q: %w", name, err)
			}
			dtypes++
		default:
			return "", fmt.Errorf("unknown precision field %q", name)
		}
		names = append(names, name)
	}
	if dtypes == 0 {
		return "", errors.New("precision requires a resolved dtype")
	}
	sort.Strings(names)
	var b strings.Builder
	for _, name := range names {
		b.WriteString(name)
		b.WriteByte('=')
		b.WriteString(fields[name])
		b.WriteByte('\n')
	}
	return digest([]byte(b.String())), nil
}

// RuntimeDigest hashes the in-process distribution/version list.
func RuntimeDigest(packages map[string]string) (string, error) {
	names := make([]string, 0, len(packages))
	for name, version := range packages {
		if name == "" || version == "" || strings.ContainsAny(name+version, "\r\n") ||
			strings.Contains(name, "==") {
			return "", fmt.Errorf("invalid runtime package %q", name)
		}
		names = append(names, name)
	}
	sort.Strings(names)
	var b strings.Builder
	for _, name := range names {
		b.WriteString(name)
		b.WriteString("==")
		b.WriteString(packages[name])
		b.WriteByte('\n')
	}
	return digest([]byte(b.String())), nil
}

// Loaded stamps all four model parts as loaded_by_us.
func Loaded(checkpointDigest, precisionDigest, runtimeDigest, answerMode string) (ModelHalf, error) {
	for name, value := range map[string]string{
		"checkpoint": checkpointDigest, "precision": precisionDigest, "runtime": runtimeDigest,
	} {
		if !validSHA256(value) {
			return ModelHalf{}, fmt.Errorf("invalid %s digest", name)
		}
	}
	if !inVocabulary("answer_modes", answerMode) {
		return ModelHalf{}, fmt.Errorf("unknown answer mode %q", answerMode)
	}
	digests := map[string]string{
		"checkpoint":  checkpointDigest,
		"precision":   precisionDigest,
		"runtime":     runtimeDigest,
		"answer_mode": digest([]byte(answerMode)),
	}
	parts := make(map[string]ModelPart, len(digests))
	for name, d := range digests {
		parts[name] = ModelPart{Sourcing: "loaded_by_us", Digest: d}
	}
	return ModelHalf{
		Parts:         parts,
		Absent:        make(map[string]Absence),
		ModelIdentity: identity(digests),
		ArtifactIdentity: identity(map[string]string{
			"checkpoint": checkpointDigest,
		}),
	}, nil
}
