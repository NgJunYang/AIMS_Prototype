import { motion } from "motion/react";
import { Camera, PenLine, ShieldCheck, CheckCircle2, ClipboardCheck, ArrowRight, Sparkles } from "lucide-react";
import { Button } from "../components/ui/Button";

const pipeline = [
  { icon: Camera, label: "Photographed" },
  { icon: PenLine, label: "Transcribed" },
  { icon: CheckCircle2, label: "Confirmed" },
  { icon: ShieldCheck, label: "Verified" },
  { icon: ClipboardCheck, label: "Marked" },
];

const features = [
  {
    icon: ShieldCheck,
    title: "Grounded in math, not guesses",
    body: "Every confirmed step is independently checked by a symbolic solver — SymPy can't be talked into agreeing with a wrong answer the way a language model can.",
  },
  {
    icon: CheckCircle2,
    title: "You're always the last word",
    body: "AIMS transcribes the handwriting, but nothing is ever marked from what the AI read. You confirm the transcription first — every time.",
  },
  {
    icon: Sparkles,
    title: "Feedback fast enough to matter",
    body: "Per-criterion justification and targeted feedback land in seconds, not days — quick enough to actually change how a student studies next.",
  },
];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};
const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4 } },
};

export default function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="overflow-x-hidden">
      {/* Hero */}
      <section className="relative px-6 pt-24 pb-20 sm:pt-32 sm:pb-28">
        <div
          className="pointer-events-none absolute inset-0 -z-10 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, rgba(85,117,107,0.20), transparent 45%), radial-gradient(circle at 80% 0%, rgba(148,101,45,0.12), transparent 40%)",
          }}
        />
        <motion.div
          initial="hidden"
          animate="show"
          variants={container}
          className="mx-auto max-w-3xl text-center"
        >
          <motion.p
            variants={item}
            className="mb-4 font-mono text-xs font-semibold uppercase tracking-[0.2em] text-accent-hover"
          >
            AI Marking Support
          </motion.p>
          <motion.h1
            variants={item}
            className="text-4xl font-semibold leading-tight tracking-tight sm:text-6xl"
          >
            A mark you don't have to take on faith.
          </motion.h1>
          <motion.p variants={item} className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-text-muted">
            Photograph a student's handwritten working. Claude transcribes it, you confirm it, an independent
            symbolic solver verifies it — then AIMS marks against your rubric and writes the feedback.
          </motion.p>
          <motion.div variants={item} className="mt-10 flex items-center justify-center gap-3">
            <Button onClick={onStart} className="px-6 py-3 text-base">
              Start marking <ArrowRight size={16} />
            </Button>
          </motion.div>
        </motion.div>
      </section>

      {/* Pipeline strip */}
      <section className="border-y border-border bg-surface/40 px-6 py-10">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.4 }}
          variants={container}
          className="mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-x-2 gap-y-6"
        >
          {pipeline.map((step, i) => (
            <motion.div key={step.label} className="flex items-center gap-2" variants={item}>
              <div className="flex flex-col items-center gap-2">
                <div className="flex h-11 w-11 items-center justify-center rounded-full border border-border bg-surface-2 text-accent-hover">
                  <step.icon size={18} />
                </div>
                <span className="font-mono text-xs text-text-muted">{step.label}</span>
              </div>
              {i < pipeline.length - 1 && <ArrowRight size={16} className="mx-2 text-border" />}
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Features */}
      <section className="px-6 py-20">
        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.3 }}
          variants={container}
          className="mx-auto grid max-w-5xl gap-6 sm:grid-cols-3"
        >
          {features.map((f) => (
            <motion.div
              key={f.title}
              variants={item}
              className="rounded-2xl border border-border bg-surface p-6"
            >
              <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-accent-soft text-accent-hover">
                <f.icon size={18} />
              </div>
              <h3 className="mb-2 text-base font-semibold">{f.title}</h3>
              <p className="text-sm leading-relaxed text-text-muted">{f.body}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-border px-6 py-16 text-center">
        <h2 className="text-2xl font-semibold">Ready to mark?</h2>
        <p className="mx-auto mt-2 max-w-md text-text-muted">
          Pick a question, upload a script, and see the full pipeline run in under a minute.
        </p>
        <Button onClick={onStart} className="mt-6 px-6 py-3 text-base">
          Start marking <ArrowRight size={16} />
        </Button>
      </section>
    </div>
  );
}
