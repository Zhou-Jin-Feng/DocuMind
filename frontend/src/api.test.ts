import { describe, expect, it } from "vitest";
import { parseSSEBlock } from "./api";

describe("SSE protocol parser", () => {
  it("parses event names and JSON data", () => {
    expect(parseSSEBlock('event: token\ndata: {"text":"你好"}')).toEqual({
      type: "token",
      data: { text: "你好" },
    });
  });

  it("ignores incomplete blocks", () => {
    expect(parseSSEBlock("data: {}")).toBeNull();
    expect(parseSSEBlock("event: token")).toBeNull();
  });
});
