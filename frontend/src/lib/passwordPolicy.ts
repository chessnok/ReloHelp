/** Must match backend/app/core/password_policy.py (ASCII-only rules). */

const RULES: ReadonlyArray<{
  readonly test: (password: string) => boolean;
  readonly message: string;
}> = [
  {
    test: (password) => password.length >= 8,
    message: "Password must be at least 8 characters long",
  },
  {
    test: (password) => password.length <= 128,
    message: "Password must be at most 128 characters long",
  },
  {
    test: (password) => /[A-Z]/.test(password),
    message: "Password must contain at least one uppercase letter",
  },
  {
    test: (password) => /[a-z]/.test(password),
    message: "Password must contain at least one lowercase letter",
  },
  {
    test: (password) => /\d/.test(password),
    message: "Password must contain at least one digit",
  },
];

export function getPasswordErrors(password: string): string[] {
  return RULES.filter((rule) => !rule.test(password)).map(
    (rule) => rule.message,
  );
}

export function isPasswordValid(password: string): boolean {
  return getPasswordErrors(password).length === 0;
}
