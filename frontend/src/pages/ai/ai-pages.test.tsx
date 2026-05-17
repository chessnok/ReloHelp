import type React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatProvider } from "@/context/ChatContext";
import { server } from "@/test/server";
import { ChatIndexPage } from "./ChatIndexPage";
import { ChatPage } from "./ChatPage";

const API = "http://localhost:8000";

function renderChat(route: string, element: React.ReactElement) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ChatProvider>
        <Routes>
          <Route path="/chat" element={element} />
          <Route path="/chat/:chatId" element={element} />
        </Routes>
      </ChatProvider>
    </MemoryRouter>,
  );
}

describe("AI chat pages", () => {
  beforeEach(() => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000001",
    );
    vi.spyOn(Date, "now").mockReturnValue(1000);
  });

  it("creates a new chat from the index page", async () => {
    renderChat("/chat", <ChatIndexPage />);

    expect(screen.getByText("How can I help you today?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /new chat/i }));

    expect(localStorage.getItem("relohelp_chats")).toContain(
      "00000000-0000-4000-8000-000000000001",
    );
  });

  it("renders history and sends a chat message", async () => {
    localStorage.setItem(
      "relohelp_chats",
      JSON.stringify([
        { id: "chat-1", title: "New chat", conversationId: null, createdAt: 1 },
      ]),
    );
    localStorage.setItem(
      "relohelp_chat_messages",
      JSON.stringify({
        "chat-1": [{ role: "assistant", content: "Saved answer" }],
      }),
    );

    const requests: unknown[] = [];
    server.use(
      http.post(`${API}/api/ai/chat`, async ({ request }) => {
        requests.push(await request.json());
        return HttpResponse.json({
          response: "Fresh answer",
          conversation_id: "conversation-1",
        });
      }),
    );

    renderChat("/chat/chat-1", <ChatPage />);

    expect(screen.getByText("Saved answer")).toBeInTheDocument();
    await userEvent.type(
      screen.getByPlaceholderText("Message Relohelp…"),
      "What should I do?",
    );
    await userEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(screen.getByText("What should I do?")).toBeInTheDocument();
    expect(await screen.findByText("Fresh answer")).toBeInTheDocument();
    expect(requests).toEqual([{ message: "What should I do?" }]);
    expect(localStorage.getItem("relohelp_chats")).toContain("conversation-1");
    expect(localStorage.getItem("relohelp_chats")).toContain(
      "What should I do?",
    );
  });

  it("submits with Enter, allows Shift+Enter, and renders API errors", async () => {
    localStorage.setItem(
      "relohelp_chats",
      JSON.stringify([
        {
          id: "chat-1",
          title: "Existing",
          conversationId: "conversation-1",
          createdAt: 1,
        },
      ]),
    );
    server.use(
      http.post(`${API}/api/ai/chat`, () =>
        HttpResponse.json({ detail: "AI is unavailable" }, { status: 500 }),
      ),
    );

    renderChat("/chat/chat-1", <ChatPage />);
    const input = screen.getByPlaceholderText("Message Relohelp…");
    await userEvent.type(input, "first line{shift>}{enter}{/shift}second line");
    expect(input).toHaveValue("first line\nsecond line");

    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(screen.getByText("AI is unavailable")).toBeInTheDocument(),
    );
  });
});
