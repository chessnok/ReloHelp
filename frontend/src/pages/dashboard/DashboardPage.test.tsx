import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";
import { testUser } from "@/test/utils";

const authMock = {
  user: testUser as typeof testUser | null,
};

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => authMock,
}));

describe("DashboardPage", () => {
  it("renders the signed-in user", () => {
    authMock.user = testUser;
    render(<DashboardPage />);

    expect(
      screen.getByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Welcome, person@example.com/)).toBeInTheDocument();
  });

  it("renders a generic welcome when the user email is missing", () => {
    authMock.user = null;
    render(<DashboardPage />);

    expect(screen.getByText("Welcome. You are logged in.")).toBeInTheDocument();
  });
});
