import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatProvider } from "@/context/ChatContext";
import { ChatSidebar } from "./ChatSidebar";

function renderSidebar(route = "/chat/chat-1") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ChatProvider>
        <Routes>
          <Route path="/chat" element={<ChatSidebar />} />
          <Route path="/chat/:chatId" element={<ChatSidebar />} />
        </Routes>
      </ChatProvider>
    </MemoryRouter>,
  );
}

describe("ChatSidebar", () => {
  beforeEach(() => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000002",
    );
    localStorage.setItem(
      "relohelp_chats",
      JSON.stringify([
        {
          id: "chat-1",
          title: "Existing chat",
          conversationId: null,
          createdAt: 1,
        },
      ]),
    );
  });

  it("renders chats, creates new chats, and deletes the active chat", async () => {
    renderSidebar();

    expect(screen.getByText("Existing chat")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /new chat/i }));
    expect(localStorage.getItem("relohelp_chats")).toContain(
      "00000000-0000-4000-8000-000000000002",
    );

    const deleteButtons = screen.getAllByRole("button", {
      name: "Delete chat",
    });
    await userEvent.click(deleteButtons[deleteButtons.length - 1]);
    expect(localStorage.getItem("relohelp_chats")).not.toContain("chat-1");
  });
});
