package perigraph

import (
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"path"
	"sort"
	"strconv"
	"strings"
	"sync"
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

func vocabularyValues(section string) ([]string, error) {
	vocabularyOnce.Do(func() {
		data, err := VocabularyJSON()
		if err != nil {
			vocabularyErr = err
			return
		}
		vocabularyErr = json.Unmarshal(data, &vocabulary)
	})
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

// Part is a held harness fact. Digest is the full lowercase SHA-256 hex digest.
// ReadLagSeconds must be set exactly when Sourcing is pulled_by_us.
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

// Absence describes a missing part. Detail is required for not_reachable and
// extraction_failed, and forbidden for all other reasons.
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

// Record describes one run. CollectorReaches is the collector-version's static
// manifest, not a list inferred from the parts found in this particular run.
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

// specWhiteSpace implements the Unicode White_Space property as enumerated in
// section 1.2. Use it only to decide whether a value exists or is unresolved;
// identifying and precision digests retain the original bytes.
func specWhiteSpace(r rune) bool {
	switch {
	case r >= '\u0009' && r <= '\u000D',
		r == '\u0020',
		r == '\u0085',
		r == '\u00A0',
		r == '\u1680',
		r >= '\u2000' && r <= '\u200A',
		r == '\u2028',
		r == '\u2029',
		r == '\u202F',
		r == '\u205F',
		r == '\u3000':
		return true
	default:
		return false
	}
}

func trimSpecWhiteSpace(s string) string {
	return strings.TrimFunc(s, specWhiteSpace)
}

func parsed(value any) (Part, error) {
	// Parsed digests are collector-local. JSON encoding here is a convention
	// of this Go collector, not a model-visible rendering.
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
		SpecVersion:      2,
		Collector:        collector,
		CollectorVersion: version,
		CollectorReaches: []string{"instruction", "tool_schemas", "tool_trace", "readout", "decoding"},
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
	for _, name := range []string{"loop", "turn_budget", "retry_policy", "context_partitioning"} {
		r.Absent[name] = Absence{Reason: "not_provided"}
	}
	r.Absent["tool_extension"] = Absence{Reason: "not_observable"}
	return r
}

// FromRequest observes an already-decoded JSON object. Pass an allocated
// empty map for {}. A nil map represents JSON null, not an empty object.
// For other non-object bodies, use FromRequestValue.
func FromRequest(body map[string]any, collector, version string) Record {
	return FromRequestValue(body, collector, version)
}

// FromRequestValue also accepts malformed top-level bodies. It emits a record
// rather than refusing one, marking every manifest part extraction_failed when
// the body is not a JSON object (including nil and a nil map). Neither errors
// nor details quote request content.
func FromRequestValue(body any, collector, version string) Record {
	r := requestRecord(collector, version)
	object, ok := body.(map[string]any)
	if !ok || object == nil {
		for _, name := range r.CollectorReaches {
			r.Absent[name] = wrongType("request body", body, "object")
		}
		return r
	}

	if raw := object["messages"]; raw == nil {
		r.Absent["instruction"] = Absence{Reason: "not_provided"}
		r.Absent["tool_trace"] = Absence{Reason: "not_provided"}
	} else if messages, ok := raw.([]any); !ok {
		a := wrongType("messages", raw, "array")
		r.Absent["instruction"], r.Absent["tool_trace"] = a, a
	} else {
		// The array's shape and each role are shared by both readers. Check
		// every entry before extracting either part: an unreadable entry
		// might have supplied either one.
		var structural *Absence
		for i, item := range messages {
			where := fmt.Sprintf("messages[%d]", i)
			m, ok := item.(map[string]any)
			if !ok {
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
			r.Absent["instruction"], r.Absent["tool_trace"] = *structural, *structural
		} else {
			var systems []string
			var trace []any
			var instructionFailure, traceFailure *Absence
			for i, item := range messages {
				m := item.(map[string]any)
				where := fmt.Sprintf("messages[%d]", i)
				switch m["role"].(string) {
				case "system":
					content, exists := m["content"]
					if !exists {
						if instructionFailure == nil {
							a := Absence{"extraction_failed", where + ".content: missing; expected string"}
							instructionFailure = &a
						}
					} else if text, ok := content.(string); ok {
						systems = append(systems, text)
					} else if instructionFailure == nil {
						a := wrongType(where+".content", content, "string")
						instructionFailure = &a
					}
				case "tool":
					trace = append(trace, m)
				case "assistant":
					if calls, exists := m["tool_calls"]; exists {
						if array, ok := calls.([]any); !ok {
							if traceFailure == nil {
								a := wrongType(where+".tool_calls", calls, "array")
								traceFailure = &a
							}
						} else {
							for j, call := range array {
								if _, ok := call.(map[string]any); !ok && traceFailure == nil {
									a := wrongType(fmt.Sprintf("%s.tool_calls[%d]", where, j), call, "object")
									traceFailure = &a
								}
							}
							trace = append(trace, calls)
						}
					}
					if call, exists := m["function_call"]; exists {
						if _, ok := call.(map[string]any); !ok {
							if traceFailure == nil {
								a := wrongType(where+".function_call", call, "object")
								traceFailure = &a
							}
						} else {
							trace = append(trace, call)
						}
					}
				}
			}
			if instructionFailure != nil {
				r.Absent["instruction"] = *instructionFailure
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
			if traceFailure != nil {
				r.Absent["tool_trace"] = *traceFailure
			} else if len(trace) == 0 {
				r.Absent["tool_trace"] = Absence{Reason: "not_provided"}
			} else if p, err := parsed(trace); err != nil {
				r.Absent["tool_trace"] = failed("messages tool trace")
			} else {
				r.Parts["tool_trace"] = p
			}
		}
	}

	if raw := object["tools"]; raw == nil {
		r.Absent["tool_schemas"] = Absence{Reason: "not_provided"}
	} else if tools, ok := raw.([]any); !ok {
		r.Absent["tool_schemas"] = wrongType("tools", raw, "array")
	} else {
		var failure *Absence
		for i, item := range tools {
			where := fmt.Sprintf("tools[%d]", i)
			tool, ok := item.(map[string]any)
			if !ok {
				a := wrongType(where, item, "object")
				failure = &a
				break
			}
			if function, exists := tool["function"]; exists {
				if _, ok := function.(map[string]any); !ok {
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

	format := object["response_format"]
	hasFormat := format != nil
	if !hasFormat {
		r.Absent["readout"] = Absence{Reason: "not_provided"}
	} else if formatObject, ok := format.(map[string]any); !ok {
		r.Absent["readout"] = wrongType("response_format", format, "object")
	} else if len(formatObject) == 0 {
		r.Absent["readout"] = Absence{Reason: "not_provided"}
		hasFormat = false
	} else if p, err := parsed(format); err != nil {
		r.Absent["readout"] = failed("response_format")
	} else {
		r.Parts["readout"] = p
	}

	sampler := make(map[string]any)
	for _, key := range []string{
		"temperature", "top_p", "top_k", "seed", "frequency_penalty",
		"presence_penalty", "logit_bias",
	} {
		if value := object[key]; value != nil {
			sampler[key] = value
		}
	}
	if hasFormat {
		sampler["response_format"] = format
	}
	if hasFormat && r.Absent["readout"].Reason == "extraction_failed" {
		r.Absent["decoding"] = r.Absent["readout"]
	} else if len(sampler) == 0 {
		r.Absent["decoding"] = Absence{Reason: "not_provided"}
	} else if p, err := parsed(sampler); err != nil {
		r.Absent["decoding"] = failed("decoding fields")
	} else {
		r.Parts["decoding"] = p
	}

	identifying := make(map[string]string)
	for name, p := range r.Parts {
		if p.Sourcing == "in_the_request" && p.Boundary == "model_visible" &&
			!inVocabulary("never_identifying", name) {
			identifying[name] = p.Digest
		}
	}
	r.HarnessIdentity = identity(identifying)
	return r
}

// ToAttributes encodes the flat, scalar-valued version-2 wire form.
// Identity keys are omitted, rather than emitted as empty strings, when absent.
func ToAttributes(r Record) map[string]any {
	version := r.SpecVersion
	if version == 0 {
		version = 2
	}
	a := map[string]any{
		"perigraph.spec_version":      version,
		"perigraph.collector":         r.Collector,
		"perigraph.collector_version": r.CollectorVersion,
		"perigraph.status":            r.Status,
	}
	reaches := append([]string(nil), r.CollectorReaches...)
	sort.Strings(reaches)
	a["perigraph.collector_reaches"] = strings.Join(reaches, ",")
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

// PrecisionDigest hashes the transform observed after loading. Fields must
// include device, quantisation, and at least one dtype.<name> parameter count.
// An unresolved field is returned as an error; a collector recording that
// observation must report the precision part as extraction_failed.
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

// Loaded stamps all four model parts as loaded_by_us. It must only be called
// in the process that loaded and observed the model during this load.
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
