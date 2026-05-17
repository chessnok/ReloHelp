import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";
import client from "@/api/client";
import { server } from "@/test/server";
import { testUser } from "@/test/utils";

const API = "http://localhost:8000";

function AuthConsumer() {
  const { user, isLoading, login, register, logout, checkAuth } = useAuth();

  return (
    <div>
      <p>{isLoading ? "loading" : "ready"}</p>
      <p>{user?.email ?? "anonymous"}</p>
      <button
        onClick={() =>
          login({ email: "person@example.com", password: "password123" })
        }
      >
        login
      </button>
      <button
        onClick={() =>
          register({ email: "person@example.com", password: "password123" })
        }
      >
        register
      </button>
      <button onClick={() => logout()}>logout</button>
      <button onClick={() => checkAuth()}>check</button>
    </div>
  );
}

describe("AuthContext", () => {
  it("loads the current user and supports login/register/logout/checkAuth", async () => {
    const requests: string[] = [];
    server.use(
      http.get(`${API}/auth/me`, () => {
        requests.push("me");
        return HttpResponse.json(testUser);
      }),
      http.post(`${API}/auth/login`, () => {
        requests.push("login");
        return HttpResponse.json({
          user: { ...testUser, email: "login@example.com" },
        });
      }),
      http.post(`${API}/auth/register`, () => {
        requests.push("register");
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API}/auth/logout`, () => {
        requests.push("logout");
        return HttpResponse.json({ ok: true });
      }),
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    expect(screen.getByText("loading")).toBeInTheDocument();
    await screen.findByText("person@example.com");
    expect(screen.getByText("ready")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "login" }));
    await screen.findByText("login@example.com");

    await userEvent.click(screen.getByRole("button", { name: "register" }));
    await userEvent.click(screen.getByRole("button", { name: "check" }));
    await screen.findByText("person@example.com");

    await userEvent.click(screen.getByRole("button", { name: "logout" }));
    await screen.findByText("anonymous");

    expect(requests).toEqual(["me", "login", "register", "me", "logout"]);
  });

  it("clears the user when initial auth or logout fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ detail: "not authenticated" }, { status: 401 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "refresh failed" }, { status: 401 }),
      ),
      http.post(`${API}/auth/logout`, () =>
        HttpResponse.json({ detail: "logout failed" }, { status: 500 }),
      ),
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await screen.findByText("anonymous");
    expect(screen.getByText("ready")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "logout" }));
    await waitFor(() => expect(consoleSpy).toHaveBeenCalled());
    expect(screen.getByText("anonymous")).toBeInTheDocument();
  });

  it("registers a logout callback used by the axios interceptor", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(testUser)),
      http.get(`${API}/protected`, () =>
        HttpResponse.json({ detail: "expired" }, { status: 401 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "invalid" }, { status: 401 }),
      ),
    );

    render(
      <AuthProvider>
        <AuthConsumer />
      </AuthProvider>,
    );

    await screen.findByText("person@example.com");
    await expect(client.get("/protected")).rejects.toBeDefined();
    await screen.findByText("anonymous");
  });

  it("throws when useAuth is rendered outside AuthProvider", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<AuthConsumer />)).toThrow(
      "useAuth must be used within an AuthProvider",
    );
    consoleSpy.mockRestore();
  });
});
