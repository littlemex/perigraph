// Command crosscheck prints the Go sender's attributes for every identity fixture body and its digests and identities
// for every model fixture, as JSON, so tools/cross_check.py can compare it with the other senders. Written by the
// reviewer, not by the implementation's author.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"

	pg "github.com/littlemex/perigraph/go"
)

func main() {
	var id struct {
		Cases []struct{ Body map[string]any }
	}
	var mc struct {
		Cases []struct {
			Files      map[string]string
			Precision  map[string]string
			Runtime    map[string]string
			AnswerMode string `json:"answer_mode"`
		}
		RefusedPrecision struct{ Cases []map[string]string } `json:"refused_precision"`
	}
	b, _ := os.ReadFile(os.Args[1])
	json.Unmarshal(b, &id)
	b, _ = os.ReadFile(os.Args[2])
	json.Unmarshal(b, &mc)
	out := map[string]any{}
	var attrs []map[string]any
	for _, c := range id.Cases {
		attrs = append(attrs, pg.ToAttributes(pg.FromRequest(c.Body, "x", "1")))
	}
	out["attrs"] = attrs
	var models []map[string]any
	for _, c := range mc.Cases {
		var files [][2]string
		for p, t := range c.Files {
			h := sha256.Sum256([]byte(t))
			files = append(files, [2]string{p, hex.EncodeToString(h[:])})
		}
		r := map[string]any{}
		ck, err := pg.CheckpointDigest(files)
		pr, err2 := pg.PrecisionDigest(c.Precision)
		rt, err3 := pg.RuntimeDigest(c.Runtime)
		r["checkpoint_digest"], r["precision_digest"], r["runtime_digest"] = ck, pr, rt
		r["errs"] = fmt.Sprint(err, err2, err3)
		if m, e := pg.Loaded(ck, pr, rt, c.AnswerMode); e == nil {
			r["model"], r["artifact"] = m.ModelIdentity, m.ArtifactIdentity
		} else {
			r["loaded_err"] = e.Error()
		}
		models = append(models, r)
	}
	out["models"] = models
	var refused []bool
	for _, p := range mc.RefusedPrecision.Cases {
		_, err := pg.PrecisionDigest(p)
		refused = append(refused, err != nil)
	}
	out["refused_precision"] = refused
	j, _ := json.Marshal(out)
	fmt.Println(string(j))
}
