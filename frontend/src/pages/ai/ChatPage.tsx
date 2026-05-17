import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  const { chats, getMessages, addMessage, setConversationId, setChatTitle } =
    useChat();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const chatItem = chatId ? chats.find((c) => c.id === chatId) : null;
  const messages = useMemo(
    () => (chatId ? getMessages(chatId) : []),
    [chatId, getMessages],
  );
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
      setChatTitle(
        chatId,
        text.length > MAX_TITLE_LENGTH
          ? text.slice(0, MAX_TITLE_LENGTH) + "…"
          : text,
      );
    }
    setLoading(true);
    try {
      const res = await chat(text, conversationId);
      setConversationId(chatId, res.conversation_id);
      addMessage(chatId, { role: "assistant", content: res.response });
    } catch (e) {
      const message =
        e &&
        typeof e === "object" &&
        "response" in e &&
        e.response &&
        typeof e.response === "object" &&
        "data" in e.response &&
        e.response.data &&
        typeof e.response.data === "object" &&
        "detail" in e.response.data
          ? String((e.response.data as { detail: unknown }).detail)
          : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [
    input,
    loading,
    chatId,
    conversationId,
    chatItem?.title,
    addMessage,
    setConversationId,
    setChatTitle,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!chatId) return null;

  return (
    <div className="flex h-full flex-col bg-canvas">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-6 py-10">
          {messages.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-24 text-center">
              <p className="font-display text-[28px] tracking-tight text-ink">
                Say hello to get started
              </p>
              <p className="max-w-sm text-[15px] text-muted-stone">
                Ask anything — visas, neighborhoods, taxes, schools, or what to
                pack first.
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "group flex gap-3 py-3",
                m.role === "user" ? "justify-end" : "justify-start",
              )}
            >
              {m.role === "assistant" && (
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-warm-mist text-terracotta">
                  <span className="text-[11px] font-medium tracking-wide">
                    AI
                  </span>
                </div>
              )}
              <div
                className={cn(
                  "max-w-[85%] rounded-3xl px-5 py-3 text-[15px] leading-[1.55]",
                  m.role === "user" ? "bg-ink text-canvas" : "bg-fog text-ink",
                )}
              >
                <p className="whitespace-pre-wrap">{m.content}</p>
              </div>
              {m.role === "user" && (
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-ink text-canvas">
                  <span className="text-[11px] font-medium">You</span>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3 py-3">
              <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-warm-mist text-terracotta">
                <span className="text-[11px] font-medium tracking-wide">
                  AI
                </span>
              </div>
              <div className="flex items-center gap-2 rounded-3xl bg-fog px-5 py-3">
                <Loader2 className="size-4 animate-spin text-muted-stone" />
                <span className="text-[14px] text-muted-stone">Thinking…</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="border-t border-border/60 bg-canvas">
        <div className="mx-auto max-w-3xl px-6 py-5">
          {error && (
            <Alert variant="destructive" className="mb-3">
              {error}
            </Alert>
          )}
          <div className="flex items-end gap-2 rounded-3xl border border-border bg-canvas p-2 transition-colors focus-within:border-ink">
            <Textarea
              placeholder="Message Relohelp…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
              className="min-h-[44px] max-h-[200px] resize-none border-0 bg-transparent py-2 focus-visible:border-0 focus-visible:ring-0"
            />
            <Button
              size="icon"
              className="size-11 shrink-0"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              {loading ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <Send className="size-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
