"""AI Agent service: OpenAI integration, MCP tool calls, Langfuse tracing."""

import json
from collections import defaultdict
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.langfuse_client import get_langfuse
from app.core.logger import logger

# Legacy in-memory conversation history. Used only when the caller does not
# supply a DB session (unit tests). Production traffic always hits the
# DB-backed path via the FastAPI route.
_conversation_history: dict[str, list[dict]] = defaultdict(list)

# Tools that need the authenticated user_id injected server-side.
# Listed explicitly so we never inject user_id into tools (e.g. find_official_info,
# search_telegram_chats) that don't accept it — OpenAI would reject the extra parameter.
_USER_SCOPED_TOOLS = frozenset({"get_user_email"})

# Single source of truth lives in mcp/app/server.py as FastMCP(instructions=...).
# Backend fetches it via MCP `initialize` and caches in the service singleton.
# This fallback is used ONLY if the MCP server is unreachable on the very first
# chat call; it must not duplicate the policy in detail (drift risk).
_FALLBACK_INSTRUCTIONS = (
    "You are the Relohelp relocation assistant. The MCP server is currently "
    "unreachable, so authoritative tool guidance is unavailable. Always call "
    "`find_official_info` for any jurisdiction-specific question (visas, taxes, "
    "prices, regulations, residency, healthcare) and `search_telegram_chats` for "
    "community experience. Refuse to guess; if no source is returned, say so explicitly."
)

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

SEARCH_TELEGRAM_CHATS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_telegram_chats",
        "description": (
            "Retrieves relevant snippets from indexed Telegram relocation/visa "
            "community chats. Call this whenever the user asks about real-world "
            "relocation, visa, residence permit, legalization, banking, or other "
            "migration logistics. Each returned hit includes chat_id and "
            "date_min/date_max - cite these in your answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language question; pass the user's question verbatim.",
                },
                "k": {
                    "type": "integer",
                    "description": "Number of hits to return (1..20). Default 5.",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
}

DEFAULT_TOOLS = [
    GET_USER_EMAIL_TOOL,
    FIND_OFFICIAL_INFO_TOOL,
    SEARCH_TELEGRAM_CHATS_TOOL,
]


class AIAgentService:
    """Orchestrates chat with OpenAI and MCP tool execution."""

    def __init__(self) -> None:
        self._openai_client = None
        self._mcp_client = None
        self._instructions_cache: str | None = None

    def _mcp_url(self) -> str:
        url = settings.MCP_SERVER_URL.rstrip("/")
        if not url.endswith("/mcp"):
            url = f"{url}/mcp"
        return url

    async def get_system_instructions(self) -> str:
        if self._instructions_cache is not None:
            return self._instructions_cache

        from fastmcp import Client

        try:
            client = Client(self._mcp_url(), timeout=10.0)
            async with client:
                init_result = client.initialize_result
                instructions = (
                    getattr(init_result, "instructions", None) if init_result else None
                )
        except Exception as e:
            logger.warning("Failed to fetch MCP instructions, using fallback: %s", e)
            instructions = None

        resolved: str = instructions or _FALLBACK_INSTRUCTIONS
        self._instructions_cache = resolved
        return resolved

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
        from fastmcp import Client

        if tool_name in _USER_SCOPED_TOOLS:
            params = {**arguments, "user_id": str(user_id)}
        else:
            params = {k: v for k, v in arguments.items() if k != "user_id"}
        client = Client(self._mcp_url(), timeout=30.0)
        async with client:
            result = await client.call_tool(tool_name, params)
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
        *,
        db: AsyncSession | None = None,
        background_tasks: Any | None = None,
    ) -> tuple[str, str, str | None]:
        """Process a chat message; returns (response_text, conversation_id, trace_id).

        When `db` is provided, conversation history is loaded from / persisted
        to the `messages` table and per-user long-term memories are retrieved
        and injected into the system prompt. When `db` is None, falls back to
        the legacy in-memory dict (used by tests that don't spin up a database).
        """
        conv_id = conversation_id or str(uuid4())
        conv_uuid: UUID | None
        try:
            conv_uuid = UUID(conv_id)
        except ValueError:
            # Legacy in-memory path tolerates arbitrary strings (used by
            # existing tests); DB path always coerces to a UUID below.
            conv_uuid = None
        if db is not None and conv_uuid is None:
            conv_uuid = uuid4()
            conv_id = str(conv_uuid)

        trace_id: str | None = None
        langfuse = get_langfuse()

        if db is not None:
            from app.services.messages import get_message_service

            msg_svc = get_message_service()
            await msg_svc.ensure_conversation(db, conv_uuid, user_id)
            messages = await msg_svc.load_history(
                db, conv_uuid, limit=settings.MEMORY_HISTORY_LIMIT
            )
            history_len_before = len(messages)
        else:
            messages = _conversation_history[conv_id].copy()
            # Legacy path used to keep the leading system message in the list;
            # drop it because we always re-inject a fresh one below.
            if messages and messages[0].get("role") == "system":
                messages = messages[1:]
            history_len_before = None

        system_prompt = await self.get_system_instructions()
        if db is not None and settings.MEMORY_ENABLED:
            try:
                from app.services.memory import get_memory_service

                mem_svc = get_memory_service()
                hits = await mem_svc.search(db, user_id, message)
                if hits:
                    block = (
                        "Known facts about the user (from prior conversations):\n"
                        + "\n".join(f"- [{h.kind}] {h.content}" for h in hits)
                    )
                    system_prompt = f"{system_prompt}\n\n{block}"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Memory retrieval failed: %s", exc)

        messages.insert(0, {"role": "system", "content": system_prompt})
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
                                "error": f"Tool '{name}' is unavailable right now.",
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

        for m in reversed(messages):
            if m.get("role") == "assistant" and m.get("content"):
                response_text = m["content"]
                break
        else:
            response_text = "I couldn't generate a response. Please try again."

        if db is not None:
            assert conv_uuid is not None  # set above when db is not None
            await self._persist_new_turns(db, conv_uuid, messages, history_len_before)
            await db.commit()
            if background_tasks is not None and settings.MEMORY_ENABLED:
                from app.services.memory import get_memory_service

                tail = _extraction_tail(messages, settings.MEMORY_EXTRACTION_TURNS)
                background_tasks.add_task(
                    get_memory_service().extract_and_store,
                    user_id,
                    conv_uuid,
                    tail,
                )
        else:
            if messages and messages[0].get("role") == "system":
                _conversation_history[conv_id] = [messages[0]] + messages[1:][-19:]
            else:
                _conversation_history[conv_id] = messages[-20:]
        return response_text, conv_id, trace_id

    async def _persist_new_turns(
        self,
        db: AsyncSession,
        conv_uuid: UUID,
        messages: list[dict],
        history_len_before: int | None,
    ) -> None:
        from app.services.messages import get_message_service

        msg_svc = get_message_service()
        # Layout: [system, ...loaded history (history_len_before items), ...new turns]
        start = 1 + (history_len_before or 0)
        for m in messages[start:]:
            role = m.get("role")
            if role == "system":
                continue
            await msg_svc.append(
                db,
                conversation_id=conv_uuid,
                role=role,
                content=m.get("content"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
            )


def _extraction_tail(messages: list[dict], n: int) -> list[dict]:
    keep = [
        m
        for m in messages
        if m.get("role") in {"user", "assistant"} and m.get("content")
    ]
    return keep[-n:]


def get_ai_agent_service() -> AIAgentService:
    if not hasattr(get_ai_agent_service, "_instance"):
        get_ai_agent_service._instance = AIAgentService()
    return get_ai_agent_service._instance
