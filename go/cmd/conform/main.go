// Command conform is the Go implementation's conformance adapter (contract: conformance/README.md). It reads one
// JSON request per line on stdin and answers one JSON line each. The Go implementation is a sender, so it declares the
// collector and stamper roles and not the receiver role.
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"

	pg "github.com/littlemex/perigraph/go"
)

type request struct {
	ID         int               `json:"id"`
	Op         string            `json:"op"`
	Body       any               `json:"body"`
	Files      map[string]string `json:"files"`
	Precision  map[string]string `json:"precision"`
	Runtime    map[string]string `json:"runtime"`
	AnswerMode string            `json:"answer_mode"`
}

func answer(r request) map[string]any {
	switch r.Op {
	case "describe":
		return map[string]any{"name": "perigraph (Go)", "roles": []string{"collector", "stamper"}}
	case "collect":
		return map[string]any{"attributes": pg.ToAttributes(pg.FromRequestValue(r.Body, "conformance", "1"))}
	case "stamp":
		var files [][2]string
		for p, t := range r.Files {
			h := sha256.Sum256([]byte(t))
			files = append(files, [2]string{p, hex.EncodeToString(h[:])})
		}
		ck, err := pg.CheckpointDigest(files)
		if err != nil {
			return map[string]any{"refused": err.Error()}
		}
		pr, err := pg.PrecisionDigest(r.Precision)
		if err != nil {
			return map[string]any{"refused": err.Error()}
		}
		rt, err := pg.RuntimeDigest(r.Runtime)
		if err != nil {
			return map[string]any{"refused": err.Error()}
		}
		m, err := pg.Loaded(ck, pr, rt, r.AnswerMode)
		if err != nil {
			return map[string]any{"refused": err.Error()}
		}
		return map[string]any{"checkpoint_digest": ck, "precision_digest": pr, "runtime_digest": rt,
			"model_identity": m.ModelIdentity, "artifact_identity": m.ArtifactIdentity}
	}
	return map[string]any{"error": "unknown op " + r.Op}
}

func main() {
	in := bufio.NewScanner(os.Stdin)
	in.Buffer(make([]byte, 1<<20), 1<<26)
	out := json.NewEncoder(os.Stdout)
	for in.Scan() {
		var r request
		if err := json.Unmarshal(in.Bytes(), &r); err != nil {
			os.Exit(2)
		}
		reply := answer(r)
		reply["id"] = r.ID
		if err := out.Encode(reply); err != nil {
			os.Exit(2)
		}
	}
}
