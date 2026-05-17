import type React from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";

type RenderWithRouterOptions = RenderOptions & {
  router?: MemoryRouterProps;
};

export function renderWithRouter(
  ui: React.ReactElement,
  { router, ...renderOptions }: RenderWithRouterOptions = {},
) {
  return render(<MemoryRouter {...router}>{ui}</MemoryRouter>, renderOptions);
}

export const testUser = {
  id: "user-1",
  email: "person@example.com",
  is_active: true,
  roles: ["user"],
  email_is_verified: true,
};
