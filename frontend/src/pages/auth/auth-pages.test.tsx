import type React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { testUser } from "@/test/utils";
import { ForgotPasswordPage } from "./ForgotPasswordPage";
import { LoginPage } from "./LoginPage";
import { RegisterPage } from "./RegisterPage";
import { ResetPasswordPage } from "./ResetPasswordPage";
import { VerifyEmailPage } from "./VerifyEmailPage";

const API = "http://localhost:8000";
const authMock = {
  login: vi.fn(),
  register: vi.fn(),
};

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => authMock,
}));

function renderAuthPage(
  ui: React.ReactElement,
  initialEntry: string,
  mountPath: string,
) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/" element={<p>Home destination</p>} />
        <Route
          path="/login"
          element={mountPath === "/login" ? ui : <p>Login destination</p>}
        />
        <Route
          path="/register"
          element={mountPath === "/register" ? ui : <p>Register destination</p>}
        />
        <Route
          path="/forgot-password"
          element={
            mountPath === "/forgot-password" ? ui : <p>Forgot destination</p>
          }
        />
        <Route
          path="/reset-password"
          element={
            mountPath === "/reset-password" ? ui : <p>Reset destination</p>
          }
        />
        <Route
          path="/verify-email"
          element={
            mountPath === "/verify-email" ? ui : <p>Verify destination</p>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("auth pages", () => {
  beforeEach(() => {
    authMock.login = vi.fn().mockResolvedValue(undefined);
    authMock.register = vi.fn().mockResolvedValue(undefined);
  });

  it("validates and submits the login form", async () => {
    renderAuthPage(<LoginPage />, "/login", "/login");

    await userEvent.click(screen.getByRole("button", { name: "Login" }));
    expect(
      await screen.findByText("Invalid email address"),
    ).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() =>
      expect(authMock.login).toHaveBeenCalledWith({
        email: "person@example.com",
        password: "password123",
      }),
    );
    expect(screen.getByText("Home destination")).toBeInTheDocument();
  });

  it("shows login API errors", async () => {
    authMock.login.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "Bad credentials" } },
    });

    renderAuthPage(<LoginPage />, "/login", "/login");
    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    expect(await screen.findByText("Bad credentials")).toBeInTheDocument();
  });

  it("validates and submits the register form", async () => {
    renderAuthPage(<RegisterPage />, "/register", "/register");

    await userEvent.type(screen.getByLabelText("Email"), "bad");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.type(
      screen.getByLabelText("Confirm Password"),
      "different",
    );
    await userEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(
      await screen.findByText("Invalid email address"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Password must be at least 8 characters"),
    ).toBeInTheDocument();
    expect(screen.getByText("Passwords don't match")).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText("Email"));
    await userEvent.clear(screen.getByLabelText("Password"));
    await userEvent.clear(screen.getByLabelText("Confirm Password"));
    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.type(
      screen.getByLabelText("Confirm Password"),
      "password123",
    );
    await userEvent.click(screen.getByRole("button", { name: "Register" }));

    await waitFor(() =>
      expect(authMock.register).toHaveBeenCalledWith({
        email: "person@example.com",
        password: "password123",
      }),
    );
    expect(screen.getByText("Login destination")).toBeInTheDocument();
  });

  it("shows generic register errors", async () => {
    authMock.register.mockRejectedValue(new Error("network"));

    renderAuthPage(<RegisterPage />, "/register", "/register");
    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.type(
      screen.getByLabelText("Confirm Password"),
      "password123",
    );
    await userEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(await screen.findByText("Failed to register")).toBeInTheDocument();
  });

  it("submits forgot-password and shows success and errors", async () => {
    server.use(
      http.post(`${API}/auth/password/forgot`, () =>
        HttpResponse.json({ ok: true }),
      ),
    );
    renderAuthPage(
      <ForgotPasswordPage />,
      "/forgot-password",
      "/forgot-password",
    );

    await userEvent.type(screen.getByLabelText("Email"), "person@example.com");
    await userEvent.click(
      screen.getByRole("button", { name: "Send Reset Link" }),
    );

    expect(await screen.findByText("Check your email")).toBeInTheDocument();

    server.use(
      http.post(`${API}/auth/password/forgot`, () =>
        HttpResponse.json({ detail: "Unknown email" }, { status: 404 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "no refresh" }, { status: 401 }),
      ),
    );
    renderAuthPage(
      <ForgotPasswordPage />,
      "/forgot-password",
      "/forgot-password",
    );
    await userEvent.type(
      screen.getAllByLabelText("Email")[0],
      "missing@example.com",
    );
    await userEvent.click(
      screen.getAllByRole("button", { name: "Send Reset Link" })[0],
    );
    expect(await screen.findByText("Unknown email")).toBeInTheDocument();
  });

  it("handles reset-password token, validation, success, and invalid links", async () => {
    server.use(
      http.post(`${API}/auth/password/reset`, async ({ request }) => {
        expect(await request.json()).toEqual({
          token: "reset-token",
          new_password: "password123",
        });
        return HttpResponse.json({ ok: true });
      }),
    );

    const { unmount } = renderAuthPage(
      <ResetPasswordPage />,
      "/reset-password?token=reset-token",
      "/reset-password",
    );

    await userEvent.type(screen.getByLabelText("New Password"), "password123");
    await userEvent.type(
      screen.getByLabelText("Confirm New Password"),
      "password123",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Reset Password" }),
    );
    expect(await screen.findByText("Login destination")).toBeInTheDocument();
    unmount();

    renderAuthPage(<ResetPasswordPage />, "/reset-password", "/reset-password");
    expect(screen.getByText("Invalid Link")).toBeInTheDocument();
  });

  it("shows reset-password API errors", async () => {
    server.use(
      http.post(`${API}/auth/password/reset`, () =>
        HttpResponse.json({ detail: "Expired token" }, { status: 400 }),
      ),
    );

    renderAuthPage(
      <ResetPasswordPage />,
      "/reset-password?token=bad",
      "/reset-password",
    );
    await userEvent.type(screen.getByLabelText("New Password"), "password123");
    await userEvent.type(
      screen.getByLabelText("Confirm New Password"),
      "password123",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Reset Password" }),
    );

    expect(await screen.findByText("Expired token")).toBeInTheDocument();
  });

  it("verifies email success, missing token, and API errors", async () => {
    server.use(
      http.post(`${API}/auth/verify-email`, () =>
        HttpResponse.json({ user: testUser }),
      ),
    );

    const { unmount } = renderAuthPage(
      <VerifyEmailPage />,
      "/verify-email?token=verify-token",
      "/verify-email",
    );
    expect(screen.getByText("Verifying...")).toBeInTheDocument();
    expect(
      await screen.findByText("Email verified successfully!"),
    ).toBeInTheDocument();
    unmount();

    renderAuthPage(<VerifyEmailPage />, "/verify-email", "/verify-email");
    expect(
      await screen.findByText("No verification token provided."),
    ).toBeInTheDocument();
  });

  it("shows verify-email API errors", async () => {
    server.use(
      http.post(`${API}/auth/verify-email`, () =>
        HttpResponse.json(
          { detail: "Invalid verification token" },
          { status: 400 },
        ),
      ),
    );

    renderAuthPage(
      <VerifyEmailPage />,
      "/verify-email?token=bad",
      "/verify-email",
    );
    expect(
      await screen.findByText("Invalid verification token"),
    ).toBeInTheDocument();
  });
});
