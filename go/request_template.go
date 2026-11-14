package perigraph

import (
	"fmt"
	"strconv"
	"strings"
	"unicode/utf8"
)

type templateEntry struct {
	role  string
	fixed []string
}

func templateFailure(check int, where string) *Absence {
	return &Absence{
		Reason: "extraction_failed",
		Detail: fmt.Sprintf("perigraph_template check %d: %s", check, where),
	}
}

func scalarString(s string) bool {
	return utf8.ValidString(s)
}

func templateMatches(content string, fixed []string) bool {
	if len(fixed) == 1 {
		return content == fixed[0]
	}
	if !strings.HasPrefix(content, fixed[0]) {
		return false
	}
	at := len(fixed[0])
	for _, interior := range fixed[1 : len(fixed)-1] {
		found := strings.Index(content[at:], interior)
		if found < 0 {
			return false
		}
		at += found + len(interior)
	}
	suffix := fixed[len(fixed)-1]
	return len(content)-len(suffix) >= at && strings.HasSuffix(content, suffix)
}

func templatePayload(entries []templateEntry) string {
	var b strings.Builder
	b.WriteString(strconv.Itoa(len(entries)))
	b.WriteByte(':')
	for _, entry := range entries {
		b.WriteString(strconv.Itoa(len(entry.role)))
		b.WriteByte(':')
		b.WriteString(entry.role)
		b.WriteString(strconv.Itoa(len(entry.fixed)))
		b.WriteByte(':')
		for _, fixed := range entry.fixed {
			b.WriteString(strconv.Itoa(len(fixed)))
			b.WriteByte(':')
			b.WriteString(fixed)
		}
	}
	return b.String()
}

func readRequestTemplate(body map[string]any) (Part, *Absence) {
	raw := body["perigraph_template"]
	if raw == nil {
		return Part{}, &Absence{Reason: "not_provided"}
	}
	template, ok := raw.(map[string]any)
	if !ok || template == nil || len(template) != 1 {
		return Part{}, templateFailure(1, "perigraph_template object or members")
	}
	rawEntries, present := template["messages"]
	if !present {
		return Part{}, templateFailure(1, "perigraph_template.messages missing")
	}
	entries, ok := rawEntries.([]any)
	if !ok {
		return Part{}, templateFailure(2, "perigraph_template.messages array")
	}
	messages, ok := body["messages"].([]any)
	if !ok {
		return Part{}, templateFailure(2, "messages array")
	}
	if len(entries) != len(messages) {
		return Part{}, templateFailure(2, fmt.Sprintf("messages[%d] length", min(len(entries), len(messages))))
	}

	read := make([]templateEntry, 0, len(entries))
	nonempty := false
	for i, rawEntry := range entries {
		where := fmt.Sprintf("messages[%d]", i)
		entry, ok := rawEntry.(map[string]any)
		if !ok || entry == nil {
			return Part{}, templateFailure(3, where+" template entry object")
		}
		_, hasFixed := entry["fixed"]
		if len(entry) != 1 && !(len(entry) == 2 && hasFixed) {
			return Part{}, templateFailure(3, where+" template entry members")
		}
		roleValue, hasRole := entry["role"]
		if !hasRole {
			return Part{}, templateFailure(3, where+" template entry role missing")
		}
		message, ok := messages[i].(map[string]any)
		if !ok || message == nil {
			return Part{}, templateFailure(4, where+" message object")
		}
		role, ok := roleValue.(string)
		if !ok {
			return Part{}, templateFailure(4, where+" template role string")
		}
		messageRole, ok := message["role"].(string)
		if !ok || role != messageRole {
			return Part{}, templateFailure(4, where+" role mismatch")
		}
		if !scalarString(role) || !scalarString(messageRole) {
			return Part{}, templateFailure(8, where+" role scalar values")
		}
		if role == "system" && hasFixed {
			return Part{}, templateFailure(5, where+" system fixed")
		}

		result := templateEntry{role: role}
		if hasFixed {
			rawFixed, ok := entry["fixed"].([]any)
			if !ok || len(rawFixed) == 0 {
				return Part{}, templateFailure(6, where+" fixed non-empty array")
			}
			for j, value := range rawFixed {
				location := fmt.Sprintf("%s.fixed[%d]", where, j)
				fixed, ok := value.(string)
				if !ok {
					return Part{}, templateFailure(6, location+" string")
				}
				if !scalarString(fixed) {
					return Part{}, templateFailure(8, location+" scalar values")
				}
				if j > 0 && j < len(rawFixed)-1 && fixed == "" {
					return Part{}, templateFailure(6, location+" empty interior fixed string")
				}
				if trimSpecWhiteSpace(fixed) != "" {
					nonempty = true
				}
				result.fixed = append(result.fixed, fixed)
			}
			content, ok := message["content"].(string)
			if !ok {
				return Part{}, templateFailure(7, where+".content string")
			}
			if !scalarString(content) {
				return Part{}, templateFailure(8, where+".content scalar values")
			}
			if !templateMatches(content, result.fixed) {
				return Part{}, templateFailure(9, where+".content fixed-string match")
			}
		}
		read = append(read, result)
	}
	if !nonempty {
		return Part{}, &Absence{Reason: "not_provided"}
	}
	return Part{
		Sourcing: "in_the_request", Boundary: "model_visible",
		Digest: digest([]byte(templatePayload(read))),
	}, nil
}

func harnessIdentity(r Record) string {
	required, err := vocabularyValues("must_be_known_for_identity")
	if err != nil {
		return ""
	}
	vocabularyOnce.Do(loadVocabulary)
	if vocabularyErr != nil {
		return ""
	}
	definition, ok := vocabulary["must_be_known_for_identity"].(map[string]any)
	if !ok {
		return ""
	}
	knownAbsentAs, ok := definition["known_when_absent_as"].(string)
	if !ok {
		return ""
	}
	keying, _ := vocabulary["keying_boundary"].(map[string]any)
	boundaries, _ := keying["parts"].(map[string]any)
	for _, name := range required {
		if held, ok := r.Parts[name]; ok {
			if boundary, listed := boundaries[name].(string); !listed ||
				held.Sourcing != "in_the_request" || held.Boundary != boundary {
				return ""
			}
			continue
		}
		if absent, found := r.Absent[name]; !found || absent.Reason != knownAbsentAs {
			return ""
		}
	}

	refines, err := vocabularyValues("refines_only")
	if err != nil {
		return ""
	}
	refinement := make(map[string]bool, len(refines))
	for _, name := range refines {
		refinement[name] = true
	}

	identifying := make(map[string]string)
	established := false
	for name, part := range r.Parts {
		boundary, listed := boundaries[name].(string)
		if !listed || part.Sourcing != "in_the_request" || part.Boundary != boundary ||
			inVocabulary("never_identifying", name) {
			continue
		}
		identifying[name] = part.Digest
		if !refinement[name] {
			established = true
		}
	}
	if !established {
		return ""
	}
	return identity(identifying)
}
