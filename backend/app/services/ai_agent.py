"""AI Agent service: OpenAI integration, MCP tool calls, Langfuse tracing."""

import json
from collections import defaultdict
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.langfuse_client import get_langfuse
from app.core.logger import logger

# In-memory conversation history: conversation_id -> list of OpenAI message dicts
_conversation_history: dict[str, list[dict]] = defaultdict(list)

# Tools that need the authenticated user_id injected server-side.
# Listed explicitly so we never inject user_id into tools (e.g. find_official_info)
# that don't accept it — OpenAI would reject the extra parameter.
_USER_SCOPED_TOOLS = frozenset({"get_user_email"})

# Mirrors mcp/app/server.py SYSTEM_INSTRUCTIONS. The MCP server's `instructions`
# field is only delivered to MCP-aware clients; OpenAI Chat Completions never
# sees it, so the backend must include it as a system message itself.
SYSTEM_INSTRUCTIONS = """\
You are the Relohelp relocation assistant.

Source-of-truth policy (MANDATORY):
- Rely ONLY on NEW and OFFICIAL data when answering questions about visas,
  taxes, prices, regulations, residency, healthcare, or any other
  jurisdiction-specific topic.
- "Official" means: government portals (.gov, .gob, .gouv, ministry sites),
  embassies/consulates, official municipal/regional authorities, primary
  providers (carriers, banks, insurers) on their own domains, and
  authoritative international bodies (EU, UN, OECD, WHO).
- "New" means: prefer content updated within the last 12 months. Discard
  anything stale, undated, or contradicting a more recent official source.
- NEVER answer from training-cutoff memory for time-sensitive facts. Call
  `find_official_info` first.
- If no official, recent source is found, say so explicitly and refuse to
  guess.
- Always cite the source URL and its published/updated date when available.
"""

# OpenAI tool definition for get_user_email (backend injects user_id when calling)
GET_USER_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "get_user_email",
        "description": "Returns the authenticated user's email. Use this when the user asks for their email address.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The UUID of the user (injected by system).",
                }
            },
            "required": ["user_id"],
        },
    },
}

FIND_OFFICIAL_INFO_TOOL = {
    "type": "function",
    "function": {
        "name": "find_official_info",
        "description": (
            "Search the public web via Firecrawl for fresh, official information "
            "(government portals, embassies, primary providers). Use this whenever "
            "the user asks about visas, taxes, prices, regulations, embassy "
            "procedures, residency, healthcare, or any jurisdiction-specific topic "
            "that may have changed since training. Always include the country/"
            "jurisdiction in the query. Discard unofficial or stale results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural-language search query. Be specific and include "
                        "the country/jurisdiction and year. Example: 'Portugal D7 "
                        "visa minimum income requirement 2026 official'."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (optional).",
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query"],
        },
    },
}

DEFAULT_TOOLS = [GET_USER_EMAIL_TOOL, FIND_OFFICIAL_INFO_TOOL]


class AIAgentService:
    """Orchestrates chat with OpenAI and MCP tool execution."""

    def __init__(self) -> None:
        self._openai_client = None
        self._mcp_client = None

    def _get_openai(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI

            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is not set")
            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    async def _call_mcp_tool(
        self, tool_name: str, arguments: dict, user_id: UUID
    ) -> dict:
        """Call MCP server tool. For user-scoped tools, inject authenticated user_id."""
        from fastmcp import Client

        if tool_name in _USER_SCOPED_TOOLS:
            # Always overwrite any client-provided user_id with the authenticated one
            params = {**arguments, "user_id": str(user_id)}
        else:
            # Strip user_id if model hallucinated one for a non-user-scoped tool
            params = {k: v for k, v in arguments.items() if k != "user_id"}
        url = settings.MCP_SERVER_URL.rstrip("/")
        if not url.endswith("/mcp"):
            url = f"{url}/mcp"
        client = Client(url, timeout=30.0)
        async with client:
            result = await client.call_tool(tool_name, params)
        # CallToolResult may have .content or .result
        if hasattr(result, "content") and result.content:
            part = (
                result.content[0]
                if isinstance(result.content, list)
                else result.content
            )
            if hasattr(part, "text"):
                return (
                    json.loads(part.text) if isinstance(part.text, str) else part.text
                )
        if hasattr(result, "result"):
            return (
                result.result
                if isinstance(result.result, dict)
                else {"result": result.result}
            )
        return {"error": "Unknown MCP response format"}

    async def chat(
        self,
        message: str,
        user_id: UUID,
        conversation_id: str | None,
    ) -> tuple[str, str, str | None]:
        """Process a chat message; returns (response_text, conversation_id, trace_id)."""
        conv_id = conversation_id or str(uuid4())
        trace_id: str | None = None
        langfuse = get_langfuse()

        messages = _conversation_history[conv_id].copy()
        # Ensure the source-of-truth policy is always the first message.
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": SYSTEM_INSTRUCTIONS})
        messages.append({"role": "user", "content": message})

        tools = DEFAULT_TOOLS
        model = settings.OPENAI_MODEL

        async def _chat_loop(messages, tools, model, user_id):
            for _ in range(max_iterations := 5):
                if langfuse:
                    with langfuse.start_as_current_observation(
                        as_type="generation", name="openai_chat", model=model
                    ) as gen_span:
                        gen_span.update(input=messages)
                        try:
                            client = self._get_openai()
                            response = await client.chat.completions.create(
                                model=model,
                                messages=messages,
                                tools=tools,
                                tool_choice="auto",
                            )
                        except Exception as e:
                            logger.exception("OpenAI API error: %s", e)
                            gen_span.update(metadata={"error": str(e)})
                            raise
                        choice = response.choices[0]
                        msg = choice.message
                        gen_span.update(
                            output=msg.content or str(getattr(msg, "tool_calls", []))
                        )
                else:
                    try:
                        client = self._get_openai()
                        response = await client.chat.completions.create(
                            model=model,
                            messages=messages,
                            tools=tools,
                            tool_choice="auto",
                        )
                    except Exception as e:
                        logger.exception("OpenAI API error: %s", e)
                        raise
                    choice = response.choices[0]
                    msg = choice.message

                if not msg.content and not getattr(msg, "tool_calls", None):
                    break
                _tc_list = list(msg.tool_calls or [])
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or None,
                }
                if _tc_list:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in _tc_list
                    ]
                messages.append(assistant_msg)
                if not msg.tool_calls:
                    break
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = (
                            json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments
                        )
                    except json.JSONDecodeError:
                        args = {}
                    if langfuse:
                        with langfuse.start_as_current_observation(
                            as_type="span", name=f"mcp_tool_{name}", input=args
                        ) as tool_span:
                            try:
                                result = await self._call_mcp_tool(name, args, user_id)
                            except Exception as e:
                                logger.warning("MCP tool %s failed: %s", name, e)
                                result = {
                                    "error": f"Tool '{name}' is unavailable right now.",
                                }
                            tool_span.update(output=result)
                    else:
                        try:
                            result = await self._call_mcp_tool(name, args, user_id)
                        except Exception as e:
                            logger.warning("MCP tool %s failed: %s", name, e)
                            result = {
                                "error": "I couldn't retrieve your email right now."
                            }
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        }
                    )
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": "I ran into a limit. Please try again.",
                    }
                )
            return messages

        if langfuse:
            with langfuse.start_as_current_observation(
                as_type="span",
                name="ai_chat",
                input={"message": message, "conversation_id": conv_id},
                metadata={"model": model},
            ):
                try:
                    from langfuse import propagate_attributes

                    with propagate_attributes(user_id=str(user_id), session_id=conv_id):
                        messages = await _chat_loop(messages, tools, model, user_id)
                finally:
                    trace_id = langfuse.get_current_trace_id()
        else:
            messages = await _chat_loop(messages, tools, model, user_id)

        # Last assistant message in list
        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                response_text = m["content"]
                break
        else:
            response_text = "I couldn't generate a response. Please try again."

        # Persist history (cap length); always keep the leading system message.
        if messages and messages[0].get("role") == "system":
            _conversation_history[conv_id] = [messages[0]] + messages[1:][-19:]
        else:
            _conversation_history[conv_id] = messages[-20:]
        return response_text, conv_id, trace_id


def get_ai_agent_service() -> AIAgentService:
    """Return singleton AI agent service."""
    if not hasattr(get_ai_agent_service, "_instance"):
        get_ai_agent_service._instance = AIAgentService()
    return get_ai_agent_service._instance
