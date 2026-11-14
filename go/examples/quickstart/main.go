// Command quickstart records a request and prints the record as the flat attributes a span would carry. The Go
// implementation is a sender, so there is no receiver step here.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	pg "github.com/littlemex/perigraph/go"
)

const body = `{
  "model": "example-model",
  "messages": [
    {"role": "system", "content": "Answer in one word."},
    {"role": "user", "content": "Which colour is the sky?"}
  ],
  "temperature": 0
}`

func main() {
	var request any
	if err := json.Unmarshal([]byte(body), &request); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	record := pg.FromRequestValue(request, "quickstart", "1")
	attributes, err := json.MarshalIndent(pg.ToAttributes(record), "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println(string(attributes))
	fmt.Println("harness identity:", record.HarnessIdentity)
}
