import { render, screen, waitFor } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import App from "./App";

// Mock the auth API to avoid real API calls
vi.mock("./api/auth", () => ({
  authApi: {
    getMe: vi.fn().mockRejectedValue(new Error("Not authenticated")),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    verifyEmail: vi.fn(),
    forgotPassword: vi.fn(),
    resetPassword: vi.fn(),
  },
}));

// Mock the client to avoid axios calls
vi.mock("./api/client", () => ({
  setLogoutCallback: vi.fn(),
  apiClient: {},
  default: {},
}));

test("renders app and redirects to login when not authenticated", async () => {
  render(<App />);

  // Wait for navigation to login page (after auth check completes)
  await waitFor(
    () => {
      expect(
        screen.getByText("Sign in to continue your relocation journey"),
      ).toBeInTheDocument();
    },
    { timeout: 3000 },
  );

  // Check that login page elements are present
  expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
});
