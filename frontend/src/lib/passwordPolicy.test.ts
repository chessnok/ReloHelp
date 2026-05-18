import { describe, expect, it } from "vitest";
import { getPasswordErrors, isPasswordValid } from "./passwordPolicy";

describe("passwordPolicy", () => {
  it("accepts a strong password", () => {
    expect(getPasswordErrors("Password1")).toEqual([]);
    expect(isPasswordValid("Password1")).toBe(true);
  });

  it("rejects passwords missing required character classes", () => {
    expect(getPasswordErrors("password1")).toContain(
      "Password must contain at least one uppercase letter",
    );
    expect(getPasswordErrors("PASSWORD1")).toContain(
      "Password must contain at least one lowercase letter",
    );
    expect(getPasswordErrors("Password")).toContain(
      "Password must contain at least one digit",
    );
    expect(getPasswordErrors("Pass1")).toContain(
      "Password must be at least 8 characters long",
    );
  });

  it("rejects unicode passwords that would not match ASCII rules", () => {
    expect(getPasswordErrors("Пароль1")).toContain(
      "Password must contain at least one uppercase letter",
    );
  });

  it("rejects passwords longer than 128 characters", () => {
    const password = `Password1${"x".repeat(122)}`;
    expect(getPasswordErrors(password)).toContain(
      "Password must be at most 128 characters long",
    );
  });
});
