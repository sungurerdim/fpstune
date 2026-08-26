import { useT } from "../i18n";
import { Card } from "./ui/Card";
import { useState } from "react";
import { Scale, Activity } from "lucide-react";
import { HeadroomPanel } from "./HeadroomPanel";
import { SuitePanel } from "./SuitePanel";
import { VerifyPanel } from "./VerifyPanel";

type BenchTab = "suite" | "verify";

/**
 * Measure, then read what the measurement means.
 *
 * This was six sub-tabs, then four, and is now two. What went, and why:
 *
 * - **Network**, **Latency** and **Compare** were folded into the suite: it
 *   wraps the same instruments, repeats them, and compares through a noise
 *   floor rather than diffing two single readings.
 * - **FPS Capture** was a manual version of a measurement the product already
 *   takes by itself. `headroom_watch` measures a known game once per session
 *   and keeps one current reading; this panel asked the user to type a process
 *   name, name the capture, start it, stop it, and save it into an archive that
 *   nothing else read — and on the machine that reported the problem it held
 *   zero captures. The one thing it could do that headroom cannot is measure a
 *   game fpstune does not know; that is recorded as a gap rather than kept as a
 *   panel.
 * - **Stress Test** was FurMark, which answers "how hot, how stable" and never
 *   "what does this machine reach" (C11 rule 6). It stays off the performance
 *   path — but off it entirely rather than beside it, since it had never been
 *   installed. The instrument and its CLI command are untouched.
 *
 * The order is the order of the work: the suite is what you press, and what
 * this machine reaches is what you read afterwards. Headroom used to sit above
 * the bar, from when the suite needed three presses and a decision before it
 * measured anything.
 */
export function BenchmarksTab() {
  const { t } = useT();
  const [activeTab, setActiveTab] = useState<BenchTab>("suite");

  const tabs: { id: BenchTab; label: string; icon: typeof Activity }[] = [
    { id: "suite", label: t("bench.measure"), icon: Activity },
    { id: "verify", label: t("bench.verifyClaims"), icon: Scale },
  ];

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === id
                ? "bg-primary text-primary-foreground"
                : "bg-muted hover:bg-muted/80"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {activeTab === "suite" && <SuitePanel />}
      {activeTab === "verify" && (
        <Card className="p-4">
          <VerifyPanel />
        </Card>
      )}

      {/* Below the instrument, because it is the result rather than the tool:
          what a game reached on this machine, against what the panel can show. */}
      <HeadroomPanel />
    </div>
  );
}
