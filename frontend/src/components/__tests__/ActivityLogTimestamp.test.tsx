/**
 * The frontend half of the timestamp contract. The backend half is
 * `tests/test_utils/test_timestamp_locale.py`, and neither half means anything
 * alone: that one says what is emitted, this one says nothing reinterprets it.
 *
 * The backend writes local wall clock as a bare `HH:MM:SS` — no date, no UTC
 * offset. This panel is the only place it is ever shown, and the only correct
 * thing to do with it is print it. Two ways that could stop being true, both of
 * which look like tidying up in a diff:
 *
 * *Parsing it.* `new Date("17:05:03")` is `Invalid Date` in V8 — verified on this
 * toolchain, not assumed — so a "let's format this nicely" change puts the literal
 * words "Invalid Date" in every row of the panel.
 *
 * *Converting it.* A naive string handed to `new Date` is read as **local** time,
 * so a formatter would silently re-stamp entries by the browser's own offset.
 *
 * The zone is stubbed rather than set through `process.env.TZ`, and that is a
 * measured constraint rather than a preference. `vitest.config.ts` pins
 * `pool: 'threads'` for determinism, and a worker thread gets its own copy of
 * `process.env`; assigning `TZ` there never reaches the V8 date cache, so both
 * "zones" resolve to whatever offset the machine running the suite happens to
 * have. `vi.stubEnv("TZ", ...)` was measured the same way and is equally inert.
 * A test that switched zones that way would pass on a panel that re-stamped
 * every row, which is the one failure it exists to catch.
 *
 * So the ambient zone is stubbed at the three places a regression could read it
 * — the `Date` constructor, `getTimezoneOffset`, and the zone
 * `Intl.DateTimeFormat` resolves — and the strongest of the three is checked
 * directly: the backend's string is never handed to `Date` at all. A value that
 * no clock ever parses cannot be re-stamped by any zone.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup } from "../../test/utils";
import { ActivityLog } from "../ActivityLog";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  api: {
    getActivityLog: vi.fn(),
  },
}));

const mocked = vi.mocked(api);

interface Entry {
  timestamp: string;
  message: string;
  level: string;
}

/** US Eastern standard time, as `getTimezoneOffset` reports it: UTC-5. */
const EASTERN_OFFSET_MINUTES = 300;
const EASTERN_ZONE = "America/New_York";

const restorers: Array<() => void> = [];

/**
 * Makes the ambient timezone read as `zone` for anything that asks, and records
 * every argument handed to `new Date(...)`.
 *
 * The returned `parsed` array is the load-bearing one: the panel is correct only
 * if the backend's timestamp never appears in it.
 */
function stubAmbientZone(zone: string, offsetMinutes: number): string[] {
  const parsed: string[] = [];

  const RealDate = globalThis.Date;
  globalThis.Date = new Proxy(RealDate, {
    construct(target, args) {
      if (typeof args[0] === "string") {
        parsed.push(args[0]);
      }
      return Reflect.construct(target, args);
    },
  });
  restorers.push(() => {
    globalThis.Date = RealDate;
  });

  const realOffset = RealDate.prototype.getTimezoneOffset;
  RealDate.prototype.getTimezoneOffset = () => offsetMinutes;
  restorers.push(() => {
    RealDate.prototype.getTimezoneOffset = realOffset;
  });

  const realResolved = Intl.DateTimeFormat.prototype.resolvedOptions;
  Intl.DateTimeFormat.prototype.resolvedOptions = function resolvedOptions() {
    return { ...realResolved.call(this), timeZone: zone };
  };
  restorers.push(() => {
    Intl.DateTimeFormat.prototype.resolvedOptions = realResolved;
  });

  return parsed;
}

/** Renders the panel open, with the entries the backend would have sent. */
async function openLogWith(entries: Entry[]): Promise<void> {
  mocked.getActivityLog.mockResolvedValue({ entries });
  render(<ActivityLog />);
  fireEvent.click(screen.getByTitle("Open activity log"));
  await waitFor(() => {
    expect(screen.getByText(entries[0].message)).toBeInTheDocument();
  });
}

/** One entry shaped exactly as `ActivityLog.add()` writes it. */
function entry(timestamp: string, message: string): Entry {
  return { timestamp, message, level: "success" };
}

describe("the activity panel prints the backend's clock rather than reading it", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    while (restorers.length > 0) {
      restorers.pop()?.();
    }
  });

  it("shows the backend's HH:MM:SS character for character", async () => {
    await openLogWith([
      entry("17:05:03", "Applied network:nagle_algorithm"),
    ]);

    expect(screen.getByText("17:05:03")).toBeInTheDocument();
    // The failure mode of parsing it, spelled out: V8 cannot read a bare time.
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
  });

  it("never hands the backend's reading to a clock", async () => {
    // Zone independence at its cause. Every way the panel could be re-stamped
    // starts with this string reaching `Date`, so a panel that never lets it
    // get there is correct in every zone at once — including the zones this
    // pool cannot actually switch the process into.
    const parsed = stubAmbientZone(EASTERN_ZONE, EASTERN_OFFSET_MINUTES);

    await openLogWith([entry("17:05:03", "Applied priority:game_priority")]);

    expect(screen.getByText("17:05:03")).toBeInTheDocument();
    expect(parsed).not.toContain("17:05:03");
  });

  it("renders the same string when the ambient zone is not the machine's", async () => {
    // 17:05:03 is what the backend's own clock wrote. A machine displaying that
    // log from another zone must still read 17:05:03: the string describes the
    // clock that produced it, and re-stamping it to 10:05:03 would claim the
    // events happened at a time this backend never reported.
    const written = entry("17:05:03", "Applied priority:game_priority");

    await openLogWith([written]);
    expect(screen.getByText("17:05:03")).toBeInTheDocument();

    // Torn down explicitly: the automatic cleanup runs between tests, and both
    // panels standing at once would make `getByText` ambiguous for the wrong reason.
    cleanup();

    stubAmbientZone(EASTERN_ZONE, EASTERN_OFFSET_MINUTES);
    await openLogWith([written]);
    expect(screen.getByText("17:05:03")).toBeInTheDocument();
  });

  it("leaves the fall-back hour ambiguous instead of resolving it", async () => {
    // US Eastern repeats 01:00-02:00 on 2026-11-01, so the backend writes
    // 01:30:00 for two entries a full hour apart -- proven on the Python side by
    // `test_an_hour_apart_at_the_fall_back_renders_identically`. The panel is
    // rendered here in that very zone, where a parser would have to pick one of
    // the two instants and would therefore have a chance to reorder or collapse
    // them. Both rows must survive, both reading 01:30:00.
    const parsed = stubAmbientZone(EASTERN_ZONE, EASTERN_OFFSET_MINUTES);

    await openLogWith([
      entry("01:30:00", "Applied network:tcp_ack_frequency"),
      entry("01:30:00", "Applied network:receive_side_scaling"),
    ]);

    expect(screen.getAllByText("01:30:00")).toHaveLength(2);
    expect(
      screen.getByText("Applied network:tcp_ack_frequency"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Applied network:receive_side_scaling"),
    ).toBeInTheDocument();
    expect(parsed).not.toContain("01:30:00");
  });

  it("does not reformat a spring-forward reading into an hour that never happened", async () => {
    // US Eastern jumps 02:00 -> 03:00 on 2026-03-08. 01:59:59 and 03:00:00 are one
    // second apart on the clock the backend read. Anything that parsed these and
    // formatted them back would be free to print 02:00:00, which no clock in the
    // zone ever showed.
    const parsed = stubAmbientZone(EASTERN_ZONE, EASTERN_OFFSET_MINUTES);

    await openLogWith([
      entry("01:59:59", "Applied system:gamedvr"),
      entry("03:00:00", "Applied priority:system_responsiveness"),
    ]);

    expect(screen.getByText("01:59:59")).toBeInTheDocument();
    expect(screen.getByText("03:00:00")).toBeInTheDocument();
    expect(screen.queryByText("02:00:00")).not.toBeInTheDocument();
    expect(parsed).not.toContain("01:59:59");
    expect(parsed).not.toContain("03:00:00");
  });
});
