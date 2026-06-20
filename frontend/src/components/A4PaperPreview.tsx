"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { VisualPayload } from "@/types/sse";
import { getToken, API_BASE } from "@/lib/api";

interface Props {
  open: boolean;
  onClose: () => void;
  markdownContent: string;
  title?: string;
  visualPayload?: VisualPayload | null;
}

const mdComponents: Components = {
  h1: ({ children, ...props }) => (
    <h1 className="text-xl font-bold mt-6 mb-4 border-b-2 border-slate-300 pb-2 tracking-wide text-slate-900" {...props}>
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 className="text-[13pt] font-bold mt-5 mb-3 pb-1.5 border-b border-slate-300 text-slate-800 tracking-wide" {...props}>
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-[11pt] font-semibold mt-4 mb-2 pb-1 border-b border-slate-200 text-slate-700 tracking-normal" {...props}>
      {children}
    </h3>
  ),
  ul: ({ children, ...props }) => (
    <ul className="a4-ul" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="a4-ol" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => (
    <li className="a4-li" {...props}>
      {children}
    </li>
  ),
  p: ({ children, ...props }) => (
    <p className="my-1.5 leading-relaxed text-slate-700" {...props}>
      {children}
    </p>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-bold text-slate-950 mr-1" {...props}>
      {children}
    </strong>
  ),
  table: ({ children, ...props }) => (
    <table className="w-full border-collapse border border-slate-300 my-3 text-[9.5pt]" {...props}>
      {children}
    </table>
  ),
  th: ({ children, ...props }) => (
    <th className="border border-slate-300 px-3 py-1.5 bg-slate-100 font-semibold text-left text-slate-700" {...props}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="border border-slate-300 px-3 py-1.5 text-slate-600" {...props}>
      {children}
    </td>
  ),
  hr: ({ ...props }) => (
    <hr className="my-5 border-slate-200" {...props} />
  ),
};

export default function A4PaperPreview({
  open,
  onClose,
  markdownContent,
  title = "简历预览",
  visualPayload,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const handlePrint = useCallback(() => {
    window.print();
  }, []);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDialogElement>) => {
      if (e.target === dialogRef.current) onClose();
    },
    [onClose]
  );

  // ── v5.3 DOCX 导出 ──
  const [isExporting, setIsExporting] = useState(false);

  const handleDownloadDocx = useCallback(async () => {
    setIsExporting(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/resume/export/docx`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ markdown_content: markdownContent }),
      });
      if (!response.ok) {
        const detail = await response.json().then((d) => d.detail).catch(() => "导出失败");
        throw new Error(typeof detail === "string" ? detail : "导出失败");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `简历优化终稿_${new Date().toISOString().slice(0, 10)}.docx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("[DOCX导出]", err);
    } finally {
      setIsExporting(false);
    }
  }, [markdownContent]);

  const hasVisualPayload = visualPayload && (
    visualPayload.name ||
    visualPayload.skills.length > 0 ||
    visualPayload.main_resume_markdown
  );

  if (!open) return null;

  return (
    <dialog
      ref={dialogRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 m-auto w-full h-full bg-transparent backdrop:bg-black/60 backdrop:backdrop-blur-sm open:flex items-center justify-center"
    >
      <div className="relative flex flex-col items-center gap-4 p-6 max-h-full">
        {/* 工具栏 */}
        <div className="flex items-center gap-3 bg-white dark:bg-zinc-800 rounded-xl px-5 py-3 shadow-xl border border-zinc-200 dark:border-zinc-700">
          <span className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            {title}
          </span>
          <button
            onClick={handlePrint}
            className="px-4 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            打印 A4 简历
          </button>
          <button
            onClick={handleDownloadDocx}
            disabled={isExporting}
            className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 active:scale-[0.98] disabled:bg-slate-300 transition"
          >
            {isExporting ? "正在导出..." : "下载为 DOCX"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm rounded-lg bg-zinc-200 dark:bg-zinc-600 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-300 dark:hover:bg-zinc-500 transition-colors"
          >
            关闭
          </button>
        </div>

        {/* A4 纸容器: 210mm × 297mm 严苛物理比例 */}
        <div className="a4-paper overflow-y-auto overflow-x-hidden bg-white text-black shadow-2xl">
          {hasVisualPayload ? (
            <>
              {/* ═══ 结构化 Header 区 ═══ */}
              {visualPayload!.name && (
                <div className="a4-header">
                  <h1 className="a4-name">{visualPayload!.name}</h1>
                  {visualPayload!.contact && (
                    <p className="a4-contact">{visualPayload!.contact}</p>
                  )}
                </div>
              )}

              {/* ═══ 长文 Markdown 画布（含核心技术栈）═══ */}
              {visualPayload!.main_resume_markdown && (
                <div className="a4-markdown-body">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={mdComponents}
                  >
                    {visualPayload!.main_resume_markdown}
                  </ReactMarkdown>
                </div>
              )}
            </>
          ) : (
            /* ═══ 降级模式：裸 Markdown 直接渲染 ═══ */
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={mdComponents}
            >
              {markdownContent || "*暂无简历内容*"}
            </ReactMarkdown>
          )}
        </div>
      </div>

      <style jsx>{`
        /* ══════════════════════════════════════════════════════════
           A4 纸排版强约束 —— 冷色调极简工业风 v5.3
           ══════════════════════════════════════════════════════════ */
        .a4-paper {
          width: 210mm;
          min-height: 297mm;
          padding: 25mm 20mm 25mm 20mm;
          font-size: 11pt;
          line-height: 1.6;
          font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC",
            "Helvetica Neue", sans-serif;
          color: #1e293b;
        }

        /* ── 结构化 Header ── */
        .a4-header {
          text-align: center;
          margin-bottom: 24px;
          padding-bottom: 16px;
          border-bottom: 2px solid #e2e8f0;
        }

        .a4-name {
          font-size: 22pt;
          font-weight: 700;
          letter-spacing: 0.05em;
          margin: 0 0 6px 0;
          color: #0f172a;
        }

        .a4-contact {
          font-size: 9pt;
          color: #64748b;
          margin: 0;
          letter-spacing: 0.02em;
        }

        /* ── 长文 Markdown 画布 ── */
        .a4-markdown-body {
          margin-top: 4px;
        }

        .a4-markdown-body :global(> *:first-child) {
          margin-top: 0 !important;
        }

        .a4-markdown-body :global(h2) {
          margin-top: 22px !important;
          margin-bottom: 10px !important;
        }

        .a4-markdown-body :global(h3) {
          margin-top: 18px !important;
          margin-bottom: 8px !important;
        }

        .a4-markdown-body :global(p),
        .a4-markdown-body :global(li) {
          margin-bottom: 3px;
        }

        .a4-markdown-body :global(ul),
        .a4-markdown-body :global(ol) {
          margin-bottom: 12px;
        }

        /* ── 微缩点阵列表 (替代系统圆点) ── */
        :global(.a4-ul) {
          list-style: none;
          padding-left: 0;
          margin: 8px 0 12px 0;
        }

        :global(.a4-ol) {
          list-style: none;
          padding-left: 0;
          margin: 8px 0 12px 0;
          counter-reset: a4-ol-counter;
        }

        :global(.a4-li) {
          position: relative;
          padding-left: 16px;
          line-height: 1.7;
          margin-bottom: 2px;
          color: #334155;
        }

        :global(.a4-li)::before {
          content: "•";
          position: absolute;
          left: 0;
          top: 0;
          color: #94a3b8;
          font-size: 8pt;
          line-height: 1.7;
        }

        :global(.a4-ol) > :global(.a4-li) {
          padding-left: 22px;
        }

        :global(.a4-ol) > :global(.a4-li)::before {
          content: counter(a4-ol-counter) ".";
          counter-increment: a4-ol-counter;
          color: #64748b;
          font-size: 9pt;
          font-weight: 500;
        }

        /* ══════════════════════════════════════════════════════════
           打印样式
           ══════════════════════════════════════════════════════════ */
        @media print {
          html,
          body {
            margin: 0;
            padding: 0;
            background: white !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          dialog {
            all: unset !important;
            position: static !important;
          }
          dialog::backdrop {
            display: none !important;
          }
          .a4-paper {
            box-shadow: none !important;
            position: static !important;
            width: 210mm !important;
            min-height: 297mm !important;
            padding: 25mm 20mm 25mm 20mm !important;
            page-break-after: always;
          }
          .a4-paper + div,
          nav,
          button {
            display: none !important;
          }
          :global(.a4-li)::before {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
        }

        /* ══════════════════════════════════════════════════════════
           屏幕响应式
           ══════════════════════════════════════════════════════════ */
        @media screen {
          .a4-paper {
            max-height: 85vh;
          }
        }
      `}</style>
    </dialog>
  );
}
