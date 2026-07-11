/**
 * SSE reader for POST /chat/stream.
 *
 * The browser's native EventSource is GET-only, and our stream endpoint is a POST
 * (it carries a JSON body), so we read the response body as a stream and parse the
 * SSE frames ourselves. Mirrors the backend event protocol:
 *   intent -> message -> agent_output? -> done, or error on failure.
 */
import { API_BASE } from "./api";
import type {
  AgentOutput,
  ChatRequest,
  DoneEvent,
  ErrorEvent,
  IntentEvent,
  MessageEvent,
} from "./types";

export interface ChatStreamHandlers {
  onIntent?: (e: IntentEvent) => void;
  onMessage?: (e: MessageEvent) => void;
  onAgentOutput?: (e: AgentOutput) => void;
  onDone?: (e: DoneEvent) => void;
  onError?: (e: ErrorEvent) => void;
}

function dispatch(event: string, data: string, handlers: ChatStreamHandlers) {
  if (!data) return;
  const payload = JSON.parse(data);
  switch (event) {
    case "intent":
      handlers.onIntent?.(payload as IntentEvent);
      break;
    case "message":
      handlers.onMessage?.(payload as MessageEvent);
      break;
    case "agent_output":
      handlers.onAgentOutput?.(payload as AgentOutput);
      break;
    case "done":
      handlers.onDone?.(payload as DoneEvent);
      break;
    case "error":
      handlers.onError?.(payload as ErrorEvent);
      break;
  }
}

/** Open the chat stream and invoke handlers per event. Returns when the stream ends. */
export async function streamChat(
  body: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError?.({
      message: "Couldn't reach the assistant. Is the backend running?",
    });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      try {
        dispatch(event, data, handlers);
      } catch {
        /* ignore a malformed frame rather than break the stream */
      }
    }
  }
}
