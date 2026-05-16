import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import client, { apiClient, setLogoutCallback } from "./client";
import { authApi } from "./auth";
import { chat } from "./ai";
import { server } from "@/test/server";
import { testUser } from "@/test/utils";

const API = "http://localhost:8000";

describe("api client", () => {
  it("configures base URL, credentials, and JSON headers", () => {
    expect(apiClient.defaults.baseURL).toBe(`${API}/`);
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.headers.common).toBeDefined();
    expect(apiClient.defaults.headers["Content-Type"]).toBe("application/json");
  });

  it("refreshes once on a 401 and retries the original request", async () => {
    let meCalls = 0;
    let refreshCalls = 0;

    server.use(
      http.get(`${API}/auth/me`, () => {
        meCalls += 1;
        if (meCalls === 1) {
          return HttpResponse.json({ detail: "expired" }, { status: 401 });
        }
        return HttpResponse.json(testUser);
      }),
      http.post(`${API}/auth/token/refresh`, () => {
        refreshCalls += 1;
        return HttpResponse.json({ ok: true });
      }),
    );

    await expect(client.get("/auth/me")).resolves.toMatchObject({
      data: testUser,
    });
    expect(meCalls).toBe(2);
    expect(refreshCalls).toBe(1);
  });

  it("clears auth state when refresh fails", async () => {
    const onLogout = vi.fn();
    setLogoutCallback(onLogout);
    document.cookie = "access_token=value; path=/";
    document.cookie = "refresh_token=value; path=/";

    server.use(
      http.get(`${API}/auth/me`, () =>
        HttpResponse.json({ detail: "expired" }, { status: 401 }),
      ),
      http.post(`${API}/auth/token/refresh`, () =>
        HttpResponse.json({ detail: "invalid" }, { status: 401 }),
      ),
    );

    await expect(client.get("/auth/me")).rejects.toBeDefined();
    expect(onLogout).toHaveBeenCalled();
    expect(document.cookie).not.toContain("access_token=value");
  });
});

describe("authApi", () => {
  it("registers, logs in, fetches current user, verifies email, and sends password reset calls", async () => {
    const seen: Array<{ path: string; body?: unknown }> = [];

    server.use(
      http.post(`${API}/auth/register`, async ({ request }) => {
        seen.push({ path: "/auth/register", body: await request.json() });
        return HttpResponse.json({ id: "created" });
      }),
      http.post(`${API}/auth/login`, async ({ request }) => {
        seen.push({ path: "/auth/login", body: await request.json() });
        return HttpResponse.json({ user: testUser });
      }),
      http.get(`${API}/auth/me`, () => HttpResponse.json(testUser)),
      http.post(`${API}/auth/verify-email`, async ({ request }) => {
        seen.push({ path: "/auth/verify-email", body: await request.json() });
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API}/auth/password/forgot`, async ({ request }) => {
        seen.push({
          path: "/auth/password/forgot",
          body: await request.json(),
        });
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API}/auth/password/reset`, async ({ request }) => {
        seen.push({ path: "/auth/password/reset", body: await request.json() });
        return HttpResponse.json({ ok: true });
      }),
      http.post(`${API}/auth/logout`, () => HttpResponse.json({ ok: true })),
    );

    await expect(
      authApi.register({
        email: "person@example.com",
        password: "password123",
      }),
    ).resolves.toEqual({ id: "created" });
    await expect(
      authApi.login({ email: "person@example.com", password: "password123" }),
    ).resolves.toEqual({ user: testUser });
    await expect(authApi.getMe()).resolves.toEqual(testUser);
    await expect(authApi.verifyEmail("verify-token")).resolves.toEqual({
      ok: true,
    });
    await expect(authApi.forgotPassword("person@example.com")).resolves.toEqual(
      {
        ok: true,
      },
    );
    await expect(
      authApi.resetPassword({
        token: "reset-token",
        new_password: "password123",
      }),
    ).resolves.toEqual({ ok: true });
    await expect(authApi.logout()).resolves.toBeUndefined();

    expect(seen).toEqual([
      {
        path: "/auth/register",
        body: { email: "person@example.com", password: "password123" },
      },
      {
        path: "/auth/login",
        body: { email: "person@example.com", password: "password123" },
      },
      { path: "/auth/verify-email", body: { token: "verify-token" } },
      { path: "/auth/password/forgot", body: { email: "person@example.com" } },
      {
        path: "/auth/password/reset",
        body: { token: "reset-token", new_password: "password123" },
      },
    ]);
  });
});

describe("chat api", () => {
  it("posts chat requests and normalizes an empty conversation id", async () => {
    const bodies: unknown[] = [];

    server.use(
      http.post(`${API}/api/ai/chat`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          response: "answer",
          conversation_id: "conversation-1",
          trace_id: "trace-1",
        });
      }),
    );

    await expect(chat("hello")).resolves.toEqual({
      response: "answer",
      conversation_id: "conversation-1",
      trace_id: "trace-1",
    });
    await chat("again", "conversation-1");

    expect(bodies).toEqual([
      { message: "hello" },
      { message: "again", conversation_id: "conversation-1" },
    ]);
  });
});
