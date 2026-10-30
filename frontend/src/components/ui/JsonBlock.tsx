import { prettyJson } from "@/lib/format";

interface JsonBlockProps {
  value: unknown;
}

export function JsonBlock({ value }: JsonBlockProps) {
  return (
    <pre className="max-h-72 overflow-auto rounded-[var(--radius-control)] bg-sunken px-3 py-2 font-mono text-xs leading-relaxed text-ink-2">
      {prettyJson(value)}
    </pre>
  );
}
