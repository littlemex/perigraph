package perigraph

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"
)

const (
	invalidScalar = "a string that is not a sequence of Unicode scalar values"
	unsafeInteger = "an integer whose magnitude exceeds 9007199254740991"
	nonfinite     = "a number that is not finite"
)

type canonicalFragment string

// CanonicalJSON parses JSON text and returns digest.canonical_value_serialisation.
// Unlike encoding/json's value decoder, it detects unpaired surrogate escapes
// and leaves an overflowing number's failure local to the value being read.
func CanonicalJSON(raw []byte) (string, error) {
	if !utf8.Valid(raw) || len(raw) >= 3 && string(raw[:3]) == "\xef\xbb\xbf" {
		return "", errors.New("invalid JSON text")
	}
	s := valueScanner{data: raw}
	value, err := s.value()
	if err != nil {
		return "", err
	}
	s.space()
	if s.at != len(raw) {
		return "", errors.New("invalid JSON text")
	}
	return canonicalValue(value)
}

type valueScanner struct {
	data []byte
	at   int
}

func (s *valueScanner) space() {
	for s.at < len(s.data) && strings.ContainsRune(" \t\n\r", rune(s.data[s.at])) {
		s.at++
	}
}

func (s *valueScanner) quoted() (string, error) {
	start := s.at
	if s.at >= len(s.data) || s.data[s.at] != '"' {
		return "", errors.New("invalid JSON text")
	}
	s.at++
	for s.at < len(s.data) {
		c := s.data[s.at]
		if c == '"' {
			s.at++
			var text string
			if err := json.Unmarshal(s.data[start:s.at], &text); err != nil {
				return "", errors.New("invalid JSON text")
			}
			return text, nil
		}
		if c < 0x20 {
			return "", errors.New("invalid JSON text")
		}
		if c != '\\' {
			s.at++
			continue
		}
		s.at++
		if s.at >= len(s.data) {
			return "", errors.New("invalid JSON text")
		}
		if s.data[s.at] != 'u' {
			if !strings.ContainsRune(`"\/bfnrt`, rune(s.data[s.at])) {
				return "", errors.New("invalid JSON text")
			}
			s.at++
			continue
		}
		code, err := s.hexEscape()
		if err != nil {
			return "", err
		}
		if code >= 0xdc00 && code <= 0xdfff {
			return "", errors.New(invalidScalar)
		}
		if code >= 0xd800 && code <= 0xdbff {
			if s.at+2 > len(s.data) || string(s.data[s.at:s.at+2]) != `\u` {
				return "", errors.New(invalidScalar)
			}
			second, err := s.hexEscape()
			if err != nil || second < 0xdc00 || second > 0xdfff {
				return "", errors.New(invalidScalar)
			}
		}
	}
	return "", errors.New("invalid JSON text")
}

// hexEscape consumes a backslash-u escape at s.at, or the 'u' after an
// already-consumed backslash.
func (s *valueScanner) hexEscape() (int64, error) {
	if s.at < len(s.data) && s.data[s.at] == '\\' {
		s.at++
	}
	if s.at+5 > len(s.data) || s.data[s.at] != 'u' {
		return 0, errors.New("invalid JSON text")
	}
	n, err := strconv.ParseUint(string(s.data[s.at+1:s.at+5]), 16, 16)
	if err != nil {
		return 0, errors.New("invalid JSON text")
	}
	s.at += 5
	return int64(n), nil
}

func (s *valueScanner) value() (any, error) {
	s.space()
	if s.at >= len(s.data) {
		return nil, errors.New("invalid JSON text")
	}
	switch s.data[s.at] {
	case '"':
		return s.quoted()
	case '{':
		s.at++
		object := make(map[string]any)
		s.space()
		if s.consume('}') {
			return object, nil
		}
		for {
			s.space()
			name, err := s.quoted()
			if err != nil {
				return nil, err
			}
			s.space()
			if !s.consume(':') {
				return nil, errors.New("invalid JSON text")
			}
			value, err := s.value()
			if err != nil {
				return nil, err
			}
			object[name] = value
			s.space()
			if s.consume('}') {
				return object, nil
			}
			if !s.consume(',') {
				return nil, errors.New("invalid JSON text")
			}
		}
	case '[':
		s.at++
		array := make([]any, 0)
		s.space()
		if s.consume(']') {
			return array, nil
		}
		for {
			value, err := s.value()
			if err != nil {
				return nil, err
			}
			array = append(array, value)
			s.space()
			if s.consume(']') {
				return array, nil
			}
			if !s.consume(',') {
				return nil, errors.New("invalid JSON text")
			}
		}
	case 't', 'f', 'n':
		for _, token := range []struct {
			text  string
			value any
		}{{"true", true}, {"false", false}, {"null", nil}} {
			if strings.HasPrefix(string(s.data[s.at:]), token.text) {
				s.at += len(token.text)
				return token.value, nil
			}
		}
		return nil, errors.New("invalid JSON text")
	default:
		start := s.at
		for s.at < len(s.data) && strings.ContainsRune("0123456789+-.eE", rune(s.data[s.at])) {
			s.at++
		}
		if start == s.at {
			return nil, errors.New("invalid JSON text")
		}
		token := string(s.data[start:s.at])
		if !json.Valid([]byte(token)) {
			return nil, errors.New("invalid JSON text")
		}
		return json.Number(token), nil
	}
}

func (s *valueScanner) consume(c byte) bool {
	if s.at < len(s.data) && s.data[s.at] == c {
		s.at++
		return true
	}
	return false
}

func utf16Less(a, b string) bool {
	x, y := utf16.Encode([]rune(a)), utf16.Encode([]rune(b))
	for i := 0; i < len(x) && i < len(y); i++ {
		if x[i] != y[i] {
			return x[i] < y[i]
		}
	}
	return len(x) < len(y)
}

func canonicalString(s string) (string, error) {
	if !utf8.ValidString(s) {
		return "", errors.New(invalidScalar)
	}
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\t':
			b.WriteString(`\t`)
		case '\n':
			b.WriteString(`\n`)
		case '\f':
			b.WriteString(`\f`)
		case '\r':
			b.WriteString(`\r`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String(), nil
}

func canonicalNumber(token string) (string, error) {
	f, err := strconv.ParseFloat(token, 64)
	if err != nil && !errors.Is(err, strconv.ErrRange) {
		return "", errors.New("a value outside the JSON data model")
	}
	if math.IsInf(f, 0) || math.IsNaN(f) {
		return "", errors.New(nonfinite)
	}
	if f == 0 {
		return "0", nil
	}
	if math.Trunc(f) == f && math.Abs(f) > 9007199254740991 {
		return "", errors.New(unsafeInteger)
	}
	negative := f < 0
	if negative {
		f = -f
	}
	scientific := strconv.FormatFloat(f, 'e', -1, 64)
	pieces := strings.Split(scientific, "e")
	exponent, _ := strconv.Atoi(pieces[1])
	digits := strings.ReplaceAll(pieces[0], ".", "")
	var result string
	if exponent >= -6 && exponent < 21 {
		position := exponent + 1
		switch {
		case position <= 0:
			result = "0." + strings.Repeat("0", -position) + digits
		case position >= len(digits):
			result = digits + strings.Repeat("0", position-len(digits))
		default:
			result = digits[:position] + "." + digits[position:]
		}
	} else {
		result = digits[:1]
		if len(digits) > 1 {
			result += "." + digits[1:]
		}
		result += "e"
		if exponent >= 0 {
			result += "+"
		}
		result += strconv.Itoa(exponent)
	}
	if negative {
		result = "-" + result
	}
	return result, nil
}

func canonicalValue(value any) (string, error) {
	switch v := value.(type) {
	case nil:
		return "null", nil
	case bool:
		if v {
			return "true", nil
		}
		return "false", nil
	case string:
		return canonicalString(v)
	case canonicalFragment:
		return string(v), nil
	case json.Number:
		if !json.Valid([]byte(v.String())) {
			return "", errors.New("a value outside the JSON data model")
		}
		return canonicalNumber(v.String())
	}
	rv := reflect.ValueOf(value)
	switch rv.Kind() {
	case reflect.Float32, reflect.Float64:
		f := rv.Float()
		if math.IsInf(f, 0) || math.IsNaN(f) {
			return "", errors.New(nonfinite)
		}
		return canonicalNumber(strconv.FormatFloat(f, 'g', -1, 64))
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return canonicalNumber(strconv.FormatInt(rv.Int(), 10))
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return canonicalNumber(strconv.FormatUint(rv.Uint(), 10))
	case reflect.Map:
		if rv.IsNil() {
			return "null", nil
		}
		if rv.Type().Key().Kind() != reflect.String {
			return "", errors.New("a value outside the JSON data model")
		}
		names := make([]string, 0, rv.Len())
		for _, key := range rv.MapKeys() {
			names = append(names, key.String())
		}
		sort.Slice(names, func(i, j int) bool { return utf16Less(names[i], names[j]) })
		var b strings.Builder
		b.WriteByte('{')
		for i, name := range names {
			key, err := canonicalString(name)
			if err != nil {
				return "", err
			}
			item, err := canonicalValue(rv.MapIndex(reflect.ValueOf(name)).Interface())
			if err != nil {
				return "", err
			}
			if i > 0 {
				b.WriteByte(',')
			}
			b.WriteString(key)
			b.WriteByte(':')
			b.WriteString(item)
		}
		b.WriteByte('}')
		return b.String(), nil
	case reflect.Slice, reflect.Array:
		if rv.Kind() == reflect.Slice && rv.IsNil() {
			return "null", nil
		}
		var b strings.Builder
		b.WriteByte('[')
		for i := 0; i < rv.Len(); i++ {
			item, err := canonicalValue(rv.Index(i).Interface())
			if err != nil {
				return "", err
			}
			if i > 0 {
				b.WriteByte(',')
			}
			b.WriteString(item)
		}
		b.WriteByte(']')
		return b.String(), nil
	default:
		return "", errors.New("a value outside the JSON data model")
	}
}
