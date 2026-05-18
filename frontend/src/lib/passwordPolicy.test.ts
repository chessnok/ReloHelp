import { describe, expect, it } from "vitest";
import { getPasswordErrors, isPasswordValid } from "./passwordPolicy";

describe("passwordPolicy", () => {
  it("accepts a strong password", () => {
    expect(getPasswordErrors("Password1")).toEqual([]);
    expect(isPasswordValid("Password1")).toBe(true);
  });

  it("rejects passwords missing required character classes", () => {
    expect(getPasswordErrors("password1")[0]).toMatch(/uppercase/i);
    expect(getPasswordErrors("PASSWORD1")[0]).toMatch(/lowercase/i);
    expect(getPasswordErrors("Password")[0]).toMatch(/digit/i);
    expect(getPasswordErrors("Pass1")[0]).toMatch(/8 characters/i);
  });
});
