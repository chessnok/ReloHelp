import type { ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { cn } from "@/lib/utils";

const schema = {
  ...defaultSchema,
  tagNames: [
    "p",
    "br",
    "strong",
    "em",
    "del",
    "code",
    "pre",
    "a",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "input",
  ],
  attributes: {
    ...defaultSchema.attributes,
    a: [
      ["href", /^(https?:|mailto:|tel:|#|\/)/i],
      ["title"],
    ],
    code: [["className", /^language-[\w-]+$/]],
    input: [
      ["type", "checkbox"],
      ["checked"],
      ["disabled"],
    ],
    th: [["align", "left", "center", "right"]],
    td: [["align", "left", "center", "right"]],
  },
  clobberPrefix: "user-content-",
};

interface ChatMarkdownProps {
  content: string;
  className?: string;
}

type AnchorProps = ComponentPropsWithoutRef<"a">;

function ExternalLink({ href, children, ...rest }: AnchorProps) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="underline underline-offset-2"
      {...rest}
    >
      {children}
    </a>
  );
}

export function ChatMarkdown({ content, className }: ChatMarkdownProps) {
  return (
    <div
      data-testid="chat-markdown"
      className={cn(
        "prose-chat space-y-2 text-[15px] leading-[1.55] break-words",
        "[&_p]:m-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5",
        "[&_pre]:overflow-x-auto [&_pre]:rounded-2xl [&_pre]:bg-ink/5 [&_pre]:p-3 [&_pre]:text-[13px]",
        "[&_code]:rounded [&_code]:bg-ink/5 [&_code]:px-1 [&_code]:py-[1px] [&_code]:text-[13px]",
        "[&_pre_code]:bg-transparent [&_pre_code]:p-0",
        "[&_h1]:text-lg [&_h2]:text-base [&_h3]:text-[15px] [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium",
        "[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-stone",
        "[&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, schema]]}
        components={{
          a: ExternalLink,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
