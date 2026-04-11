import { useMemo } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";

import { cn } from "@/lib/utils";

export function MarkdownMessage({
  content,
  className
}: {
  content: string;
  className?: string;
}) {
  const html = useMemo(
    () =>
      DOMPurify.sanitize(
        marked.parse(content, {
          gfm: true,
          breaks: true
        }) as string
      ),
    [content]
  );

  return (
    <div
      className={cn(
        "prose prose-sm max-w-none text-foreground",
        "prose-headings:mb-2 prose-headings:mt-0 prose-headings:text-foreground",
        "prose-p:my-2 prose-p:leading-6",
        "prose-ul:my-2 prose-ol:my-2 prose-li:my-1",
        "prose-strong:text-foreground",
        "prose-code:rounded prose-code:bg-background/70 prose-code:px-1 prose-code:py-0.5 prose-code:text-foreground",
        "prose-pre:border prose-pre:border-border/60 prose-pre:bg-background/85",
        "prose-blockquote:border-border/80 prose-blockquote:text-muted-foreground",
        className
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
