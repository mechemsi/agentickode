// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { AlertTriangle, CheckCircle, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { reviewPlan } from "../../api/runs";
import { useToast } from "../shared/Toast";

interface Subtask {
  id?: number;
  title: string;
  description?: string;
  files_likely_affected?: string[];
  complexity?: string;
}

interface PlanReviewPanelProps {
  runId: number;
  subtasks: Subtask[];
  complexity?: string;
  notes?: string;
  onReviewed: () => void;
}

function ComplexityBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    simple: "bg-green-900/40 text-green-300 border-green-700/50",
    medium: "bg-yellow-900/40 text-yellow-300 border-yellow-700/50",
    complex: "bg-red-900/40 text-red-300 border-red-700/50",
  };
  return (
    <span className={`px-2 py-0.5 text-xs rounded border ${colors[level] ?? "bg-gray-800 text-gray-400 border-gray-700"}`}>
      {level}
    </span>
  );
}

export default function PlanReviewPanel({
  runId,
  subtasks,
  complexity,
  notes,
  onReviewed,
}: PlanReviewPanelProps) {
  const toast = useToast();
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);

  const toggle = (idx: number) =>
    setExpanded((prev) => ({ ...prev, [idx]: !prev[idx] }));

  const handleApprove = async () => {
    setLoading(true);
    try {
      await reviewPlan(runId, { action: "approve" });
      toast.success("Plan approved — coding will begin");
      onReviewed();
    } catch (e) {
      toast.error(`Failed to approve: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await reviewPlan(runId, { action: "reject", rejection_reason: reason || undefined });
      toast.success("Plan rejected");
      onReviewed();
    } catch (e) {
      toast.error(`Failed to reject: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900/40 border border-blue-800/40 rounded-xl p-5 mb-6 backdrop-blur-sm">
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        Plan Review
        {complexity && <ComplexityBadge level={complexity} />}
      </h2>

      {notes && (
        <div className="flex items-start gap-2 mb-4 p-3 bg-yellow-900/20 border border-yellow-700/40 rounded-lg text-sm text-yellow-200">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{notes}</span>
        </div>
      )}

      <div className="space-y-2 mb-5">
        {subtasks.map((st, idx) => (
          <div key={st.id ?? idx} className="border border-gray-800/60 rounded-lg">
            <button
              onClick={() => toggle(idx)}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-gray-800/30"
            >
              {expanded[idx] ? (
                <ChevronDown className="w-4 h-4 text-gray-500" />
              ) : (
                <ChevronRight className="w-4 h-4 text-gray-500" />
              )}
              <span className="text-gray-300 font-medium">{idx + 1}. {st.title}</span>
            </button>
            {expanded[idx] && (
              <div className="px-4 pb-3 text-sm text-gray-400 space-y-1">
                {st.description && <p>{st.description}</p>}
                {st.files_likely_affected && st.files_likely_affected.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {st.files_likely_affected.map((f) => (
                      <span key={f} className="px-1.5 py-0.5 bg-gray-800 text-gray-300 rounded text-xs font-mono">{f}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleApprove}
          disabled={loading}
          className="px-4 py-1.5 bg-green-700 hover:bg-green-600 disabled:opacity-50 text-white rounded-lg text-sm inline-flex items-center gap-1.5"
        >
          <CheckCircle className="w-4 h-4" />
          Approve Plan &amp; Start Coding
        </button>
        {!rejecting ? (
          <button
            onClick={() => setRejecting(true)}
            disabled={loading}
            className="px-4 py-1.5 bg-red-800 hover:bg-red-700 disabled:opacity-50 text-white rounded-lg text-sm inline-flex items-center gap-1.5"
          >
            <XCircle className="w-4 h-4" />
            Reject
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Reason (optional)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-1 focus:ring-red-500"
            />
            <button
              onClick={handleReject}
              disabled={loading}
              className="px-3 py-1.5 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white rounded-lg text-sm"
            >
              Confirm Reject
            </button>
            <button
              onClick={() => setRejecting(false)}
              className="px-3 py-1.5 text-gray-400 hover:text-white text-sm"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}