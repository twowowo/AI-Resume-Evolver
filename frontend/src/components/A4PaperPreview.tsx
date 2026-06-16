"use client";

import { useEffect, useRef, useCallback } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { VisualPayload } from "@/types/sse";

interface Props {
  open: boolean;
  onClose: () => void;
  markdownContent: string;
  title?: string;
  visualPayload?: VisualPayload | null;
}

const mdComponents: Components = {
  h1: ({ children, ...props }) => (
    <h1
      className="text-xl font-bold mt-5 mb-3 border-b-2 border-gray-300 pb-1.5 tracking-wide"
      {...props}
    >
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2
      className="text-lg font-bold mt-4 mb-2 border-b border-gray-200 pb-1 tracking-wide"
      {...props}
    >
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-base font-semibold mt-3 mb-1.5" {...props}>
      {children}
    </h3>
  ),
  ul: ({ children, ...props }) => (
    <ul className="list-disc pl-6 my-2 space-y-0.5" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal pl-6 my-2 space-y-0.5" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => (
    <li className="my-0.5 leading-relaxed" {...props}>
      {children}
    </li>
  ),
  p: ({ children, ...props }) => (
    <p className="my-1.5 leading-relaxed" {...props}>
      {children}
    </p>
  ),
  strong: ({ children, ...props }) => (
    <strong className="font-bold text-gray-900" {...props}>
      {children}
    </strong>
  ),
  table: ({ children, ...props }) => (
    <table
      className="w-full border-collapse border border-gray-300 my-3 text-sm"
      {...props}
    >
      {children}
    </table>
  ),
  th: ({ children, ...props }) => (
    <th
      className="border border-gray-300 px-3 py-1.5 bg-gray-100 font-semibold text-left"
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="border border-gray-300 px-3 py-1.5" {...props}>
      {children}
    </td>
  ),
  hr: ({ ...props }) => (
    <hr className="my-4 border-gray-200" {...props} />
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

              {/* ═══ 核心技能 Pill 标签区 ═══ */}
              {visualPayload!.skills.length > 0 && (
                <div className="a4-skills-section">
                  <h2 className="a4-section-title">核心技术栈</h2>
                  <div className="a4-skills-pills">
                    {visualPayload!.skills.map((skill) => (
                      <span key={skill} className="a4-skill-pill">
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* ═══ 长文 Markdown 画布 ═══ */}
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
           A4 纸排版强约束 —— 大厂 HR 审美级
           ══════════════════════════════════════════════════════════ */
        .a4-paper {
          width: 210mm;
          min-height: 297mm;
          padding: 25mm 20mm 25mm 20mm;
          font-size: 11pt;
          line-height: 1.6;
          font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC",
            "Helvetica Neue", sans-serif;
          color: #1a1a1a;
        }

        /* ── 结构化 Header ── */
        .a4-header {
          text-align: center;
          margin-bottom: 24px;
          padding-bottom: 16px;
          border-bottom: 2px solid #e5e7eb;
        }

        .a4-name {
          font-size: 22pt;
          font-weight: 700;
          letter-spacing: 0.05em;
          margin: 0 0 6px 0;
          color: #111827;
        }

        .a4-contact {
          font-size: 9pt;
          color: #6b7280;
          margin: 0;
          letter-spacing: 0.02em;
        }

        /* ── 技能 Pill 标签区 ── */
        .a4-skills-section {
          margin-bottom: 20px;
        }

        .a4-section-title {
          font-size: 12pt;
          font-weight: 700;
          color: #374151;
          margin: 0 0 10px 0;
          padding-bottom: 4px;
          border-bottom: 1px solid #e5e7eb;
        }

        .a4-skills-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .a4-skill-pill {
          display: inline-block;
          padding: 4px 14px;
          font-size: 9.5pt;
          font-weight: 500;
          color: #1e40af;
          background: #eff6ff;
          border: 1px solid #bfdbfe;
          border-radius: 9999px;
          letter-spacing: 0.01em;
          line-height: 1.5;
        }

        /* ── 长文 Markdown 画布 ── */
        .a4-markdown-body {
          margin-top: 4px;
        }

        .a4-markdown-body :global(> *:first-child) {
          margin-top: 0 !important;
        }

        /* 模块间呼吸感 */
        .a4-markdown-body :global(h2) {
          margin-top: 20px !important;
          margin-bottom: 10px !important;
        }

        .a4-markdown-body :global(h3) {
          margin-top: 16px !important;
          margin-bottom: 8px !important;
        }

        .a4-markdown-body :global(p),
        .a4-markdown-body :global(li) {
          margin-bottom: 4px;
        }

        .a4-markdown-body :global(ul),
        .a4-markdown-body :global(ol) {
          margin-bottom: 12px;
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
          .a4-skill-pill {
            background: #eff6ff !important;
            border: 1px solid #bfdbfe !important;
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
