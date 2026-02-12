import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

export type Message = { role: "user" | "assistant"; content: string };

export type ChatItem = {
  id: string;
  title: string;
  conversationId: string | null;
  createdAt: number;
};

const STORAGE_KEY_CHATS = "relohelp_chats";
const STORAGE_KEY_MESSAGES = "relohelp_chat_messages";

function loadChats(): ChatItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CHATS);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadMessages(): Record<string, Message[]> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_MESSAGES);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Message[]>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveChats(chats: ChatItem[]) {
  localStorage.setItem(STORAGE_KEY_CHATS, JSON.stringify(chats));
}

function saveMessages(messages: Record<string, Message[]>) {
  localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(messages));
}

type ChatContextValue = {
  chats: ChatItem[];
  messagesByChatId: Record<string, Message[]>;
  createChat: () => string;
  deleteChat: (chatId: string) => void;
  getMessages: (chatId: string) => Message[];
  addMessage: (chatId: string, message: Message) => void;
  setConversationId: (chatId: string, conversationId: string) => void;
  setChatTitle: (chatId: string, title: string) => void;
};

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [chats, setChats] = useState<ChatItem[]>(loadChats);
  const [messagesByChatId, setMessagesByChatId] = useState<Record<string, Message[]>>(loadMessages);

  const createChat = useCallback(() => {
    const id = crypto.randomUUID();
    const item: ChatItem = {
      id,
      title: "New chat",
      conversationId: null,
      createdAt: Date.now(),
    };
    setChats((prev) => {
      const next = [item, ...prev];
      saveChats(next);
      return next;
    });
    return id;
  }, []);

  const deleteChat = useCallback((chatId: string) => {
    setChats((prev) => {
      const next = prev.filter((c) => c.id !== chatId);
      saveChats(next);
      return next;
    });
    setMessagesByChatId((prev) => {
      const next = { ...prev };
      delete next[chatId];
      saveMessages(next);
      return next;
    });
  }, []);

  const getMessages = useCallback(
    (chatId: string) => messagesByChatId[chatId] ?? [],
    [messagesByChatId]
  );

  const addMessage = useCallback((chatId: string, message: Message) => {
    setMessagesByChatId((prev) => {
      const list = prev[chatId] ?? [];
      const next = { ...prev, [chatId]: [...list, message] };
      saveMessages(next);
      return next;
    });
  }, []);

  const setConversationId = useCallback((chatId: string, conversationId: string) => {
    setChats((prev) => {
      const next = prev.map((c) =>
        c.id === chatId ? { ...c, conversationId } : c
      );
      saveChats(next);
      return next;
    });
  }, []);

  const setChatTitle = useCallback((chatId: string, title: string) => {
    setChats((prev) => {
      const next = prev.map((c) => (c.id === chatId ? { ...c, title } : c));
      saveChats(next);
      return next;
    });
  }, []);

  const value = useMemo<ChatContextValue>(
    () => ({
      chats,
      messagesByChatId,
      createChat,
      deleteChat,
      getMessages,
      addMessage,
      setConversationId,
      setChatTitle,
    }),
    [
      chats,
      messagesByChatId,
      createChat,
      deleteChat,
      getMessages,
      addMessage,
      setConversationId,
      setChatTitle,
    ]
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
