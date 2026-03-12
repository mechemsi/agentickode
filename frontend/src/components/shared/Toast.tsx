// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { createContext, useCallback, useContext, useEffect, useReducer, useRef } from "react";
import { createPortal } from "react-dom";
import { CheckCircle, Info, X, XCircle, AlertTriangle } from "lucide-react";

type Variant = "success" | "error" | "info" | "warning";

interface Toast {
  id: string;
  message: string;
  variant: Variant;
  duration: number;
}

type Action = { type: "ADD"; toast: Toast } | { type: "REMOVE"; id: string };

function reducer(state: Toast[], action: Action): Toast[] {
  if (action.type === "ADD") return [...state, action.toast];
  if (action.type === "REMOVE") return state.filter((t) => t.id !== action.id);
  return state;
}

interface ToastAPI {
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
  warning: (message: string, duration?: number) => void;
}

const Ctx = createContext<ToastAPI | null>(null);

export function useToast(): ToastAPI {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast requires ToastProvider");
  return ctx;
}

const STYLES: Record<Variant, string> = {
  success: "border-green-700/60 bg-green-950/80 text-green-200",
  error: "border-red-700/60 bg-red-950/80 text-red-200",
  info: "border-blue-700/60 bg-blue-950/80 text-blue-200",
  warning: "border-yellow-700/60 bg-yellow-950/80 text-yellow-200",
};

const ICONS: Record<Variant, typeof CheckCircle> = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const ICON_COLOR: Record<Variant, string> = {
  success: "text-green-400",
  error: "text-red-400",
  info: "text-blue-400",
  warning: "text-yellow-400",
};

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (toast.duration > 0) {
      timer.current = setTimeout(() => onRemove(toast.id), toast.duration);
    }
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [toast.id, toast.duration, onRemove]);

  const Icon = ICONS[toast.variant];

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-xl border backdrop-blur-md shadow-lg w-80 max-w-[calc(100vw-2rem)] animate-slide-up ${STYLES[toast.variant]}`}
      role="alert"
    >
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${ICON_COLOR[toast.variant]}`} />
      <span className="flex-1 text-sm leading-snug">{toast.message}</span>
      <button
        onClick={() => onRemove(toast.id)}
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
        aria-label="Dismiss"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, dispatch] = useReducer(reducer, []);

  const remove = useCallback((id: string) => dispatch({ type: "REMOVE", id }), []);

  const add = useCallback(
    (variant: Variant) => (message: string, duration = 4000) => {
      dispatch({ type: "ADD", toast: { id: crypto.randomUUID(), message, variant, duration } });
    },
    [],
  );

  const api: ToastAPI = {
    success: add("success"),
    error: add("error"),
    info: add("info"),
    warning: add("warning"),
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      {createPortal(
        <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 items-end pointer-events-none">
          {toasts.map((t) => (
            <div key={t.id} className="pointer-events-auto">
              <ToastItem toast={t} onRemove={remove} />
            </div>
          ))}
        </div>,
        document.body,
      )}
    </Ctx.Provider>
  );
}