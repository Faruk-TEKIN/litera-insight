import type { ReactNode } from 'react';

type MarkdownContentProps = {
  content: string;
  compact?: boolean;
  className?: string;
};

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; lines: string[] }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'code'; text: string };

export function MarkdownContent({ content, compact = false, className = '' }: MarkdownContentProps) {
  const blocks = parseBlocks(content || '');

  return (
    <div className={`markdown-content max-w-none ${compact ? 'space-y-1' : 'space-y-3'} ${className}`}>
      {blocks.map((block, index) => renderBlock(block, index, compact))}
    </div>
  );
}

function renderBlock(block: Block, index: number, compact: boolean) {
  if (block.type === 'heading') {
    const Tag = `h${Math.min(block.level, 4)}` as keyof JSX.IntrinsicElements;
    const classes = headingClasses(block.level, compact);
    return <Tag key={index} className={classes}>{renderInline(block.text)}</Tag>;
  }

  if (block.type === 'ul') {
    return (
      <ul key={index} className={`${compact ? 'my-1' : 'my-2'} list-disc space-y-1 pl-5 text-[var(--text-secondary)]`}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex} className="leading-6">{renderInline(item)}</li>
        ))}
      </ul>
    );
  }

  if (block.type === 'ol') {
    return (
      <ol key={index} className={`${compact ? 'my-1' : 'my-2'} list-decimal space-y-1 pl-5 text-[var(--text-secondary)]`}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex} className="leading-6">{renderInline(item)}</li>
        ))}
      </ol>
    );
  }

  if (block.type === 'code') {
    return (
      <pre key={index} className="overflow-x-auto rounded-md border border-[var(--border)] bg-[var(--surface-elevated)] p-3 text-xs leading-5 text-[var(--text-primary)]">
        <code>{block.text}</code>
      </pre>
    );
  }

  return (
    <p key={index} className={`${compact ? 'text-xs leading-5' : 'text-[15px] leading-7'} text-[var(--text-secondary)]`}>
      {renderInline(block.lines.join(' '))}
    </p>
  );
}

function parseBlocks(content: string): Block[] {
  const blocks: Block[] = [];
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  let paragraph: string[] = [];
  let listType: 'ul' | 'ol' | null = null;
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let inCode = false;

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push({ type: 'paragraph', lines: paragraph });
      paragraph = [];
    }
  };

  const flushList = () => {
    if (listType && listItems.length) {
      blocks.push({ type: listType, items: listItems });
    }
    listType = null;
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inCode) {
        blocks.push({ type: 'code', text: codeLines.join('\n') });
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(rawLine);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() });
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listType !== 'ul') flushList();
      listType = 'ul';
      listItems.push(unordered[1].trim());
      continue;
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listType !== 'ol') flushList();
      listType = 'ol';
      listItems.push(ordered[1].trim());
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }

  if (inCode) {
    blocks.push({ type: 'code', text: codeLines.join('\n') });
  }
  flushParagraph();
  flushList();
  return blocks;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const regex = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])|(\*\*|__)(.*?)\2|(\*|_)(.*?)\4|(`)(.*?)\6/g;
  let match: RegExpExecArray | null;
  let lastIndex = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[1]) {
      nodes.push(
        <a
          key={`a-${match.index}`}
          href={match[1]}
          target="_blank"
          rel="noreferrer"
          className="break-words font-medium text-[var(--text-primary)] underline decoration-[var(--text-muted)] underline-offset-4 hover:decoration-[var(--text-primary)]"
        >
          {match[1]}
        </a>,
      );
    } else if (match[3]) {
      nodes.push(<strong key={`b-${match.index}`} className="font-semibold text-[var(--text-primary)]">{match[3]}</strong>);
    } else if (match[5]) {
      nodes.push(<em key={`i-${match.index}`} className="italic">{match[5]}</em>);
    } else if (match[7]) {
      nodes.push(
        <code key={`c-${match.index}`} className="rounded border border-[var(--border)] bg-[var(--surface-elevated)] px-1.5 py-0.5 font-mono text-xs text-[var(--text-primary)]">
          {match[7]}
        </code>,
      );
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function headingClasses(level: number, compact: boolean): string {
  if (compact) {
    return 'font-semibold leading-snug text-[var(--text-primary)]';
  }
  if (level === 1) {
    return 'mt-1 border-b border-[var(--border-muted)] pb-2 text-xl font-semibold leading-snug text-[var(--text-primary)]';
  }
  if (level === 2) {
    return 'pt-2 text-base font-semibold leading-snug text-[var(--text-primary)]';
  }
  return 'text-sm font-semibold leading-snug text-[var(--text-primary)]';
}
