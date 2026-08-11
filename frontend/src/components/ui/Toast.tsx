import * as RadixToast from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";

type ToastKind = "error" | "success" | "info";
type ToastItem = { id: number; kind: ToastKind; message: string };

const ToastCtx = createContext<{ push: (kind: ToastKind, message: string) => void } | null>(null);

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return {
    error: (message: string) => ctx.push("error", message),
    success: (message: string) => ctx.push("success", message),
    info: (message: string) => ctx.push("info", message),
  };
}

const toneClasses: Record<ToastKind, string> = {
  error: "border-danger/40 bg-danger-soft text-danger",
  success: "border-success/40 bg-success-soft text-success",
  info: "border-accent/40 bg-accent-soft text-accent-hover",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random();
    setItems((cur) => [...cur, { id, kind, message }]);
    setTimeout(() => setItems((cur) => cur.filter((i) => i.id !== id)), 5000);
  }, []);

  return (
    <ToastCtx.Provider value={{ push }}>
      <RadixToast.Provider swipeDirection="right">
        {children}
        <AnimatePresence>
          {items.map((item) => (
            <RadixToast.Root key={item.id} asChild forceMount duration={5000}>
              <motion.div
                initial={{ opacity: 0, y: -12, x: 0 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: 40 }}
                className={`rounded-lg border px-4 py-3 text-sm font-medium shadow-lg ${toneClasses[item.kind]}`}
              >
                {item.message}
              </motion.div>
            </RadixToast.Root>
          ))}
        </AnimatePresence>
        <RadixToast.Viewport className="fixed top-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
      </RadixToast.Provider>
    </ToastCtx.Provider>
  );
}
