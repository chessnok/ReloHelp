/** Must match backend/app/core/password_policy.py */

export const LOGIN_PASSWORD_ERROR =
  "Something went wrong. Check your email and password.";

export function getPasswordErrors(password: string): string[] {
  const errors: string[] = [];
  if (password.length < 8) {
    errors.push("Password must be at least 8 characters long");
  }
  if (password.length > 128) {
    errors.push("Password must be at most 128 characters long");
  }
  if (!/[A-Z]/.test(password)) {
    errors.push("Password must contain at least one uppercase letter");
  }
  if (!/[a-z]/.test(password)) {
    errors.push("Password must contain at least one lowercase letter");
  }
  if (!/\d/.test(password)) {
    errors.push("Password must contain at least one digit");
  }
  return errors;
}

export function isPasswordValid(password: string): boolean {
  return getPasswordErrors(password).length === 0;
}
