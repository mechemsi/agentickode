// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Check, X } from "lucide-react";
import { approveRun, rejectRun } from "../../api";
import { useToast } from "../shared/Toast";

export default function ApprovalButtons({
  runId,
  onAction,
}: {
  runId: number;
  onAction: () => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const handleApprove = async () => {
    setLoading(true);
    try {
      await approveRun(runId);
      toast.success("Run approved successfully");
      onAction();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to approve run");
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await rejectRun(runId, reason);
      toast.success("Run rejected");
      onAction();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to reject run");
      setLoading(false);
    }
  };

  if (rejecting) {
    return (
      <div className="flex gap-2 items-center">
        <input
          className="bg-gray-800/80 border border-gray-700/60 rounded-lg px-3 py-1.5 text-sm text-white flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          placeholder="Rejection reason..."
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button
          onClick={handleReject}
          disabled={loading}
          className="px-4 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-sm disabled:opacity-50 shadow-sm shadow-red-900/30 focus:outline-none focus:ring-2 focus:ring-red-500/40"
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
    );
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={handleApprove}
        disabled={loading}
        className="px-4 py-1.5 bg-green-700 hover:bg-green-600 text-white rounded-lg text-sm disabled:opacity-50 inline-flex items-center gap-1.5 shadow-sm shadow-green-900/30 focus:outline-none focus:ring-2 focus:ring-green-500/40"
      >
        <Check className="w-4 h-4" />
        Approve & Merge
      </button>
      <button
        onClick={() => setRejecting(true)}
        disabled={loading}
        className="px-4 py-1.5 bg-red-900 hover:bg-red-800 text-white rounded-lg text-sm disabled:opacity-50 inline-flex items-center gap-1.5 shadow-sm shadow-red-900/30 focus:outline-none focus:ring-2 focus:ring-red-500/40"
      >
        <X className="w-4 h-4" />
        Reject
      </button>
    </div>
  );
}