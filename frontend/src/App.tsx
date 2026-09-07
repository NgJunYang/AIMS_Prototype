import { useState } from "react";
import { motion } from "motion/react";
import { GraduationCap, PenSquare } from "lucide-react";
import { ToastProvider } from "./components/ui/Toast";
import { WorkbenchProvider, useWorkbench } from "./state/WorkbenchContext";
import Landing from "./pages/Landing";
import Setup from "./pages/Setup";
import Confirm from "./pages/Confirm";
import Class from "./pages/Class";
import Student from "./pages/Student";

export type Screen = "landing" | "setup" | "confirm" | "class" | "student";
export type Role = "instructor" | "student";

const INSTRUCTOR_SCREENS: { id: Screen; label: string }[] = [
  { id: "setup", label: "Setup" },
  { id: "confirm", label: "Workbench" },
  { id: "class", label: "Analytics" },
];

function readRole(): Role {
  try {
    return localStorage.getItem("aims_role") === "student" ? "student" : "instructor";
  } catch {
    return "instructor";
  }
}

function Shell() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [role, setRoleState] = useState<Role>(readRole);
  const { state } = useWorkbench();

  function setRole(next: Role) {
    setRoleState(next);
    try {
      localStorage.setItem("aims_role", next);
    } catch {
      /* private mode — the switch still works for this session */
    }
    setScreen(next === "student" ? "student" : "setup");
  }

  return (
    <div className="min-h-screen bg-bg text-text">
      {screen !== "landing" && (
        <header className="sticky top-0 z-30 border-b border-border bg-bg/90 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-3">
            <button
              onClick={() => setScreen("landing")}
              className="font-mono text-sm font-semibold tracking-tight text-text hover:text-accent transition-colors"
            >
              AIMS
            </button>
            <nav className="flex items-center gap-1">
              {screen !== "student" &&
                INSTRUCTOR_SCREENS.map((s) => {
                  const disabled = s.id === "confirm" && !state.submissionId;
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
              <button
                onClick={() => setRole(role === "student" ? "instructor" : "student")}
                className="ml-2 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-text-muted hover:border-accent/50 hover:text-text"
                title={role === "student" ? "Switch to instructor view" : "Switch to student view"}
              >
                {role === "student" ? <PenSquare size={14} /> : <GraduationCap size={14} />}
                {role === "student" ? "Instructor" : "Student"}
              </button>
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
        {screen === "landing" && <Landing onStart={(r) => setRole(r)} />}
        {screen === "setup" && <Setup onSubmissionCreated={() => setScreen("confirm")} />}
        {screen === "confirm" && <Confirm />}
        {screen === "class" && <Class />}
        {screen === "student" && <Student />}
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
