import { useState } from "react";
import { motion } from "motion/react";
import { ToastProvider } from "./components/ui/Toast";
import { WorkbenchProvider, useWorkbench } from "./state/WorkbenchContext";
import Landing from "./pages/Landing";
import Setup from "./pages/Setup";
import Confirm from "./pages/Confirm";
import Review from "./pages/Review";
import Class from "./pages/Class";

export type Screen = "landing" | "setup" | "confirm" | "review" | "class";

const APP_SCREENS: { id: Screen; label: string }[] = [
  { id: "setup", label: "Setup" },
  { id: "confirm", label: "Confirm" },
  { id: "review", label: "Review" },
  { id: "class", label: "Class" },
];

function Shell() {
  const [screen, setScreen] = useState<Screen>("landing");
  const { state } = useWorkbench();

  return (
    <div className="min-h-screen bg-bg text-text">
      {screen !== "landing" && (
        <header className="sticky top-0 z-30 border-b border-border bg-bg/90 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
            <button
              onClick={() => setScreen("landing")}
              className="font-mono text-sm font-semibold tracking-tight text-text hover:text-accent transition-colors"
            >
              AIMS
            </button>
            <nav className="flex gap-1">
              {APP_SCREENS.map((s) => {
                const disabled = (s.id === "confirm" || s.id === "review") && !state.submissionId;
                return (
                  <button
                    key={s.id}
                    disabled={disabled}
                    onClick={() => setScreen(s.id)}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-30 disabled:pointer-events-none ${
                      screen === s.id ? "bg-accent-soft text-accent-hover" : "text-text-muted hover:text-text"
                    }`}
                  >
                    {s.label}
                  </button>
                );
              })}
            </nav>
          </div>
        </header>
      )}

      {/*
        Deliberately NOT AnimatePresence mode="wait": that gates mounting the
        new screen on the old screen's exit animation firing
        onAnimationComplete, which can silently never fire for a
        throttled/backgrounded tab — leaving the user stuck with no way to
        navigate. Content shown always matches `screen` synchronously; the
        transition below is a best-effort entrance animation only.
      */}
      <motion.main
        key={screen}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        {screen === "landing" && <Landing onStart={() => setScreen("setup")} />}
        {screen === "setup" && <Setup onSubmissionCreated={() => setScreen("confirm")} />}
        {screen === "confirm" && <Confirm onMarked={() => setScreen("review")} />}
        {screen === "review" && <Review />}
        {screen === "class" && <Class />}
      </motion.main>
    </div>
  );
}

function App() {
  return (
    <ToastProvider>
      <WorkbenchProvider>
        <Shell />
      </WorkbenchProvider>
    </ToastProvider>
  );
}

export default App;
