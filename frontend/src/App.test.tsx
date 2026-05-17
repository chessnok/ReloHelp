import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import App from "./App";
import { server } from "@/test/server";
import { testUser } from "@/test/utils";

const API = "http://localhost:8000";

describe("App routing", () => {
  it("redirects unauthenticated users to login", async () => {
    window.history.pushState({}, "", "/");
    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ detail: "not authenticated" }, { status: 401 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "no refresh" }, { status: 401 }),
      ),
    );

    render(<App />);

    expect(
      await screen.findByText("Sign in to continue your relocation journey"),
    ).toBeInTheDocument();
  });

  it("renders protected dashboard routes for authenticated users", async () => {
    window.history.pushState({}, "", "/");
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json(testUser)));

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Welcome, person@example.com/)).toBeInTheDocument();
  });

  it("renders public auth routes", async () => {
    window.history.pushState({}, "", "/forgot-password");
    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ detail: "not authenticated" }, { status: 401 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "no refresh" }, { status: 401 }),
      ),
    );

    render(<App />);

    expect(await screen.findByText("Forgot Password")).toBeInTheDocument();
  });
});
