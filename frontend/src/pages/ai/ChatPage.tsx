import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert } from "@/components/ui/alert";
import { chat } from "@/api/ai";
import { useChat } from "@/context/ChatContext";
import { cn } from "@/lib/utils";

const MAX_TITLE_LENGTH = 50;

export const ChatPage: React.FC = () => {
  const { chatId } = useParams<{ chatId: string }>();
  const {
    chats,
    getMessages,
    addMessage,
    setConversationId,
    setChatTitle,
  } = useChat();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const chatItem = chatId ? chats.find((c) => c.id === chatId) : null;
  const messages = chatId ? getMessages(chatId) : [];
  const conversationId = chatItem?.conversationId ?? null;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !chatId) return;
    setInput("");
    setError(null);
    addMessage(chatId, { role: "user", content: text });
    if (chatItem?.title === "New chat") {
      setChatTitle(chatId, text.length > MAX_TITLE_LENGTH ? text.slice(0, MAX_TITLE_LENGTH) + "…" : text);
    }
    setLoading(true);
    try {
      const res = await chat(text, conversationId);
      setConversationId(chatId, res.conversation_id);
      addMessage(chatId, { role: "assistant", content: res.response });
    } catch (e) {
      const message =
        e && typeof e === "object" && "response" in e && e.response && typeof e.response === "object" && "data" in e.response && e.response.data && typeof e.response.data === "object" && "detail" in e.response.data
          ? String((e.response.data as { detail: unknown }).detail)
          : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [input, loading, chatId, conversationId, chatItem?.title, addMessage, setConversationId, setChatTitle]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!chatId) return null;

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">
          {messages.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
              <p className="text-muted-foreground text-sm">
                Send a message to start the conversation.
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "group flex gap-4 py-4",
                m.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              {m.role === "assistant" && (
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <span className="text-sm font-medium">AI</span>
                </div>
              )}
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-3 text-sm shadow-sm",
                  m.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p>
              </div>
              {m.role === "user" && (
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <span className="text-xs font-medium">You</span>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-4 py-4">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <span className="text-sm font-medium">AI</span>
              </div>
              <div className="flex items-center gap-2 rounded-2xl bg-muted px-4 py-3">
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Thinking...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-border bg-background">
        <div className="mx-auto max-w-3xl px-4 py-4">
          {error && (
            <Alert variant="destructive" className="mb-3">
              {error}
            </Alert>
          )}
          <div className="flex gap-2">
            <Textarea
              placeholder="Message…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
              className="min-h-[52px] max-h-[200px] resize-none py-3"
            />
            <Button
              size="icon"
              className="size-[52px] shrink-0"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              {loading ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <Send className="size-5" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
