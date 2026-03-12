// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export default function CollapsibleJSON({ title, data, defaultOpen = false }: { title: string; data: unknown; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mt-4">
      <button onClick={() => setOpen(!open)} className="text-sm text-gray-400 hover:text-white inline-flex items-center gap-1 transition-colors">
        {open ? (
          <>
            <ChevronDown className="w-4 h-4" />
            {"▾"} {title}
          </>
        ) : (
          <>
            <ChevronRight className="w-4 h-4" />
            {"▸"} {title}
          </>
        )}
      </button>
      {open && (
        <pre className="bg-gray-900/60 border border-gray-800/60 rounded-xl p-4 mt-2 text-xs overflow-x-auto animate-fade-in backdrop-blur-sm">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}