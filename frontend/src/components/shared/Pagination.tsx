// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  total: number;
  offset: number;
  limit: number;
  onPageChange: (newOffset: number) => void;
}

export default function Pagination({ total, offset, limit, onPageChange }: Props) {
  if (total <= limit) return null;

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div className="flex items-center justify-between mt-4 text-sm text-gray-400">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(0, offset - limit))}
          disabled={!hasPrev}
          className="px-2 py-1 rounded border border-gray-700/50 hover:bg-gray-800/40 disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-1"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Previous
        </button>
        <span className="text-gray-500">
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={() => onPageChange(offset + limit)}
          disabled={!hasNext}
          className="px-2 py-1 rounded border border-gray-700/50 hover:bg-gray-800/40 disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-1"
        >
          Next <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}