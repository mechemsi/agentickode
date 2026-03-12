// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { createContext, useCallback, useContext, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, Info, X } from "lucide-react";

type Variant = "danger" | "warning" | "info";

interface ConfirmOptions {
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
}

type ConfirmFn = (options: ConfirmOptions | string) => Promise<boolean>;

const Ctx = createContext<ConfirmFn | null>(null);

export function useConfirm(): ConfirmFn {
  const fn = useContext(Ctx);
  if (!fn) throw new Error("useConfirm requires ConfirmProvider");
  return fn;
}

const V: Record<Variant, { btn: string; icon: string; badge: string; Icon: typeof AlertTriangle }> = {
  danger: {
    btn: "bg-red-600 hover:bg-red-500 shadow-red-900/30 focus:ring-red-500/40",
    icon: "text-red-400",
    badge: "bg-red-500/10",
    Icon: AlertTriangle,
  },
  warning: {
    btn: "bg-yellow-600 hover:bg-yellow-500 shadow-yellow-900/30 focus:ring-yellow-500/40",
    icon: "text-yellow-400",
    badge: "bg-yellow-500/10",
    Icon: AlertTriangle,
  },
  info: {
    btn: "bg-blue-600 hover:bg-blue-500 shadow-blue-900/30 focus:ring-blue-500/40",
    icon: "text-blue-400",
    badge: "bg-blue-500/10",
    Icon: Info,
  },
};

interface DialogState extends ConfirmOptions {
  resolve: (v: boolean) => void;
}

function Dialog({ state, onClose }: { state: DialogState; onClose: (v: boolean) => void }) {
  const v = V[state.variant ?? "danger"];
  const VIcon = v.Icon;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(false); }}
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-gray-900 border border-gray-700/60 rounded-2xl p-6 w-full max-w-sm shadow-2xl animate-slide-down">
        <div className="flex items-start gap-3 mb-4">
          <span className={`p-2 rounded-lg ${v.badge}`}>
            <VIcon className={`w-4 h-4 ${v.icon}`} />
          </span>
          <div className="flex-1 min-w-0">
            {state.title && (
              <h3 className="text-sm font-semibold text-white mb-1">{state.title}</h3>
            )}
            <p className="text-sm text-gray-300 leading-relaxed">{state.message}</p>
          </div>
          <button
            onClick={() => onClose(false)}
            className="text-gray-500 hover:text-white shrink-0 transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => onClose(false)}
            autoFocus
            className="px-4 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500/40"
          >
            {state.cancelLabel ?? "Cancel"}
          </button>
          <button
            onClick={() => onClose(true)}
            className={`px-4 py-1.5 text-sm text-white rounded-lg shadow-sm transition-colors focus:outline-none focus:ring-2 ${v.btn}`}
          >
            {state.confirmLabel ?? "Confirm"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [dialog, setDialog] = useState<DialogState | null>(null);

  const confirm: ConfirmFn = useCallback(
    (options) =>
      new Promise<boolean>((resolve) => {
        const normalized = typeof options === "string" ? { message: options } : options;
        setDialog({ ...normalized, resolve });
      }),
    [],
  );

  const handleClose = (result: boolean) => {
    dialog?.resolve(result);
    setDialog(null);
  };

  return (
    <Ctx.Provider value={confirm}>
      {children}
      {dialog && <Dialog state={dialog} onClose={handleClose} />}
    </Ctx.Provider>
  );
}