import client from "./client";

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  trace_id?: string | null;
}

export const chat = async (
  message: string,
  conversationId?: string | null,
): Promise<ChatResponse> => {
  const response = await client.post<ChatResponse>("/api/ai/chat", {
    message,
    conversation_id: conversationId ?? undefined,
  });
  return response.data;
};
