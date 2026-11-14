// Record a request, carry the record as flat attributes, and read it back as a receiver would.
import { fromAttributes, fromRequest, toAttributes } from "../dist/src/index.js";

const body = {
  model: "example-model",
  messages: [
    { role: "system", content: "Answer in one word." },
    { role: "user", content: "Which colour is the sky?" },
  ],
  temperature: 0,
};

const record = fromRequest(body, { collector: "quickstart", version: "1" });
const attributes = toAttributes(record);
console.log(JSON.stringify(attributes, null, 2));

const received = fromAttributes(attributes);
console.log("harness identity:", received.identity);
console.log("verdict:", received.admissibleToAVerdict() ? "admissible" : "refused");
