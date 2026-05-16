import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthLayout } from "./AuthLayout";
import { ChatLayout } from "./ChatLayout";
import { MainLayout } from "./MainLayout";
import { ProtectedRoutes } from "./ProtectedRoutes";
import { testUser } from "@/test/utils";

const authState = {
  user: testUser as unknown,
  isLoading: false,
  logout: vi.fn(),
};

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("layouts", () => {
  beforeEach(() => {
    authState.user = testUser;
    authState.isLoading = false;
    authState.logout = vi.fn();
  });

  it("renders AuthLayout outlet content", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route element={<AuthLayout />}>
            <Route path="/login" element={<p>Login outlet</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login outlet")).toBeInTheDocument();
  });

  it("shows a loader while protected auth is loading", () => {
    authState.isLoading = true;

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<ProtectedRoutes />}>
            <Route path="/" element={<p>Secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText("Secret")).not.toBeInTheDocument();
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("redirects unauthenticated users and renders outlets for authenticated users", () => {
    authState.user = null;

    const { unmount } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<p>Login route</p>} />
          <Route element={<ProtectedRoutes />}>
            <Route path="/" element={<p>Secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login route")).toBeInTheDocument();
    unmount();

    authState.user = testUser;
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/login" element={<p>Login route</p>} />
          <Route element={<ProtectedRoutes />}>
            <Route path="/" element={<p>Secret</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Secret")).toBeInTheDocument();
  });

  it("renders main navigation and logs out", async () => {
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/chat" element={<p>Chat body</p>} />
            <Route path="/login" element={<p>Login route</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Relohelp")).toBeInTheDocument();
    expect(screen.getByText("Chat body")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /logout/i }));
    expect(authState.logout).toHaveBeenCalled();
  });

  it("renders chat layout with sidebar and outlet", () => {
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route path="/chat" element={<ChatLayout />}>
            <Route index element={<p>Chat index</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("button", { name: /new chat/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Chat index")).toBeInTheDocument();
  });
});
