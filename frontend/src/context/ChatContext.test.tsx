import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatProvider, useChat } from "./ChatContext";

function ChatConsumer() {
  const {
    chats,
    getMessages,
    createChat,
    deleteChat,
    addMessage,
    setConversationId,
    setChatTitle,
  } = useChat();
  const first = chats[0];
  const messages = first ? getMessages(first.id) : [];

  return (
    <div>
      <p>chats:{chats.length}</p>
      <p>title:{first?.title ?? "none"}</p>
      <p>conversation:{first?.conversationId ?? "none"}</p>
      <p>messages:{messages.map((message) => message.content).join("|")}</p>
      <button onClick={() => createChat()}>create</button>
      <button
        onClick={() =>
          first && addMessage(first.id, { role: "user", content: "hello" })
        }
      >
        add
      </button>
      <button
        onClick={() => first && setConversationId(first.id, "conversation-1")}
      >
        conversation
      </button>
      <button onClick={() => first && setChatTitle(first.id, "Renamed")}>
        rename
      </button>
      <button onClick={() => first && deleteChat(first.id)}>delete</button>
    </div>
  );
}

describe("ChatContext", () => {
  beforeEach(() => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(
      "00000000-0000-4000-8000-000000000001",
    );
    vi.spyOn(Date, "now").mockReturnValue(1000);
  });

  it("creates chats, stores messages, updates metadata, and deletes persisted state", async () => {
    render(
      <ChatProvider>
        <ChatConsumer />
      </ChatProvider>,
    );

    expect(screen.getByText("chats:0")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "create" }));
    expect(screen.getByText("chats:1")).toBeInTheDocument();
    expect(screen.getByText("title:New chat")).toBeInTheDocument();
    expect(localStorage.getItem("relohelp_chats")).toContain(
      "00000000-0000-4000-8000-000000000001",
    );

    await userEvent.click(screen.getByRole("button", { name: "add" }));
    expect(screen.getByText("messages:hello")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "conversation" }));
    expect(screen.getByText("conversation:conversation-1")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "rename" }));
    expect(screen.getByText("title:Renamed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "delete" }));
    expect(screen.getByText("chats:0")).toBeInTheDocument();
    expect(localStorage.getItem("relohelp_chat_messages")).toBe("{}");
  });

  it("loads existing chats and tolerates malformed storage", () => {
    localStorage.setItem(
      "relohelp_chats",
      JSON.stringify([
        {
          id: "existing",
          title: "Existing",
          conversationId: null,
          createdAt: 1,
        },
      ]),
    );
    localStorage.setItem(
      "relohelp_chat_messages",
      JSON.stringify({ existing: [{ role: "assistant", content: "saved" }] }),
    );

    const { unmount } = render(
      <ChatProvider>
        <ChatConsumer />
      </ChatProvider>,
    );

    expect(screen.getByText("title:Existing")).toBeInTheDocument();
    expect(screen.getByText("messages:saved")).toBeInTheDocument();
    unmount();

    localStorage.setItem("relohelp_chats", "{bad json");
    localStorage.setItem("relohelp_chat_messages", "null");
    render(
      <ChatProvider>
        <ChatConsumer />
      </ChatProvider>,
    );

    expect(screen.getByText("chats:0")).toBeInTheDocument();
  });

  it("throws when useChat is rendered outside ChatProvider", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<ChatConsumer />)).toThrow(
      "useChat must be used within ChatProvider",
    );
    consoleSpy.mockRestore();
  });
});
