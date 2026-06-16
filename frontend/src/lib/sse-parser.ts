/**
 * SSE 行缓冲解析器 —— 纯函数，无 React 依赖
 *
 * 防御核心：fetch().body.getReader() 返回的 chunk 边界与 SSE 帧边界不重合。
 * 本解析器维护一个内部字符串缓冲区，以 \n\n（双换行）为帧分隔符，
 * 确保任意 chunk 切割下每一帧都被完整解析，彻底堵死"半帧丢包"漏洞。
 *
 * 协议格式（对齐后端 main.py _sse_event）:
 *   event: <event_name>\ndata: <json>\n\n
 */

import type { ParsedSSEFrame } from "@/types/sse";

/**
 * 从 ReadableStream<Uint8Array> 中异步拉取并解析 SSE 帧，
 * 返回一个 AsyncGenerator，每次 yield 一个完整帧。
 *
 * 使用示例:
 *   const response = await fetch("/api/agent/stream", { method: "POST", ... });
 *   for await (const frame of parseSSEStream(response.body!)) {
 *     console.log(frame.event, frame.data);
 *   }
 */
export async function* parseSSEStream<T = unknown>(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal
): AsyncGenerator<ParsedSSEFrame<T>> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");

  // ═══ 行缓冲区：SSE 解析的命门 ═══
  // chunk 边界不可控 —— 一次 read() 可能返回半帧、一帧半、或多帧。
  // buffer 持续累积，只在遇到 \n\n 时才切割出完整帧。
  let buffer = "";

  try {
    while (true) {
      // 支持外部 AbortController 中断流
      if (signal?.aborted) {
        reader.cancel();
        return;
      }

      const { done, value } = await reader.read();

      if (done) {
        // 流结束：Flush TextDecoder 内部缓冲区中的最后字节
        buffer += decoder.decode();
        // 尽力解析 buffer 中可能残留的最后一帧
        if (buffer.trim()) {
          const frame = parseFrame(buffer);
          if (frame) {
            yield frame as ParsedSSEFrame<T>;
          } else {
            // 残帧无法按标准协议解析，尝试作为纯文本透传
            yield {
              event: "RESIDUAL",
              data: buffer.trim(),
            } as ParsedSSEFrame<T>;
          }
        }
        return;
      }

      // chunk → 字符串，追加到行缓冲区
      buffer += decoder.decode(value, { stream: true });

      // 按 \n\n 切割 —— 最后一段是不完整的残帧，留在 buffer 等下一轮
      const parts = buffer.split("\n\n");
      // 最后一段是残帧，塞回 buffer
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        if (!part.trim()) continue;
        const frame = parseFrame(part);
        if (frame) yield frame as ParsedSSEFrame<T>;
      }
    }
  } catch (err: unknown) {
    // 异常中断路径：强制 flush TextDecoder 内部缓冲区 + 行缓冲区残帧
    // 防止网络分包 / 非标 Token（如不完整 "Prom"）憋死在解析器内部
    try {
      buffer += decoder.decode();
      if (buffer.trim()) {
        const frame = parseFrame(buffer);
        if (frame) {
          yield frame as ParsedSSEFrame<T>;
        } else {
          yield {
            event: "RESIDUAL",
            data: buffer.trim(),
          } as ParsedSSEFrame<T>;
        }
      }
    } catch {
      // flush 失败不覆盖原始异常
    }
    throw err;
  } finally {
    // 确保 reader 释放，防止内存泄漏
    try {
      reader.releaseLock();
    } catch {
      // reader 可能已被 cancel 释放
    }
  }
}

/**
 * 解析单帧 SSE 文本块，提取 event 和 data 字段。
 *
 * 兼容两种后端 SSE 格式：
 *   1. 标准格式 (main.py _sse_event):
 *      event: radar_init\ndata: {...}\n\n
 *
 *   2. 嵌套格式 (agent_router.py):
 *      data: {"event": "NODE_CHANGED", "data": {...}}\n\n
 *
 * 对于嵌套格式，从 JSON 中提取 event 名和内部 data 负载。
 */
function parseFrame(raw: string): ParsedSSEFrame | null {
  let eventName = "";
  let dataStr = "";

  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) {
      eventName = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataStr = line.slice(6);
    }
  }

  // ── 兼容嵌套格式：event 名嵌在 JSON data 内部 ──
  if (!eventName && dataStr) {
    try {
      const outer = JSON.parse(dataStr);
      if (outer && typeof outer.event === "string") {
        eventName = outer.event;
        // 内部 data 可能是对象、字符串或 null
        if (outer.data !== undefined) {
          dataStr =
            typeof outer.data === "string"
              ? outer.data
              : JSON.stringify(outer.data);
        }
      }
    } catch {
      // 非 JSON，保持原样
    }
  }

  if (!eventName) return null;

  let data: unknown = dataStr;
  if (dataStr) {
    try {
      data = JSON.parse(dataStr);
    } catch {
      // 非 JSON 数据（如纯文本 content），原样透传
    }
  }

  return { event: eventName, data };
}
