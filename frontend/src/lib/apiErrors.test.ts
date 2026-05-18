import { describe, expect, it } from "vitest";
import { formatApiErrorDetail } from "./apiErrors";

describe("formatApiErrorDetail", () => {
  it("strips Value error prefix from validation messages", () => {
    const detail = [
      {
        type: "value_error",
        loc: ["body", "password"],
        msg: "Value error, Password must contain at least one uppercase letter",
        input: "weak",
      },
    ];
    expect(formatApiErrorDetail(detail, "fallback")).toBe(
      "Password must contain at least one uppercase letter",
    );
  });

  it("joins multiple validation messages", () => {
    const detail = [
      { msg: "Value error, Too short" },
      { msg: "Value error, Missing digit" },
    ];
    expect(formatApiErrorDetail(detail, "fallback")).toBe(
      "Too short; Missing digit",
    );
  });
});
