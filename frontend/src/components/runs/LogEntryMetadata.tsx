// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { ChevronDown, ChevronRight, Terminal, MessageSquare, Reply } from "lucide-react";

interface LogEntryMetadataProps {
  metadata: Record<string, unknown>;
}

const categoryLabels: Record<string, { label: string; Icon: typeof Terminal }> = {
  ssh_command: { label: "SSH Command", Icon: Terminal },
  system_prompt: { label: "System Prompt", Icon: MessageSquare },
  prompt: { label: "Prompt", Icon: MessageSquare },
  response: { label: "Response", Icon: Reply },
};

const textFields = new Set([
  "prompt_text",
  "system_prompt_text",
  "response_text",
  "stdout",
  "stderr",
  "command",
]);

export default function LogEntryMetadata({ metadata }: LogEntryMetadataProps) {
  const [expanded, setExpanded] = useState(false);

  const category = metadata.category as string | undefined;
  const config = category ? categoryLabels[category] : undefined;
  const label = config?.label ?? category ?? "Details";
  const Icon = config?.Icon ?? Terminal;

  return (
    <div className="ml-8 mt-0.5 mb-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        data-testid="metadata-toggle"
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Icon className="w-3 h-3" />
        <span>{label}</span>
      </button>

      {expanded && (
        <div className="mt-1 rounded bg-gray-800/60 border border-gray-700/50 p-2 text-xs space-y-1.5" data-testid="metadata-content">
          {Object.entries(metadata).map(([key, value]) => {
            if (key === "category") return null;

            // Truncation warnings
            if (key.endsWith("_truncated") && value === true) {
              const origKey = key.replace("_truncated", "_original_length");
              const origLen = metadata[origKey];
              return (
                <p key={key} className="text-yellow-500 text-[10px]">
                  Content truncated{origLen ? ` (original: ${origLen} chars)` : ""}
                </p>
              );
            }
            if (key.endsWith("_original_length")) return null;

            // Preformatted text blocks
            if (textFields.has(key) && typeof value === "string") {
              return (
                <div key={key}>
                  <span className="text-gray-500">{key}:</span>
                  <pre className="mt-0.5 whitespace-pre-wrap break-all text-gray-400 bg-gray-900/50 rounded p-1.5 max-h-48 overflow-y-auto">
                    {value}
                  </pre>
                </div>
              );
            }

            // Key-value pairs
            return (
              <div key={key} className="flex gap-2">
                <span className="text-gray-500 shrink-0">{key}:</span>
                <span className="text-gray-400 break-all">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}