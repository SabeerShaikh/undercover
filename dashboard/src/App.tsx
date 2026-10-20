import { useEffect, useState } from "react";
import {
  fetchClaim,
  fetchClaims,
  fetchInstructions,
  signOffAndPay,
  startAgent,
} from "./api";
import { ClaimView } from "./ClaimView";
import { Instructions } from "./Instructions";
import { Queue } from "./Queue";
import type { InstructionsText } from "./api";
import type { ClaimDetail, QueueClaim, View } from "./types";

export function App() {
  const [view, setView] = useState<View>({ name: "queue" });
  const [claims, setClaims] = useState<QueueClaim[]>([]);
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [instructions, setInstructions] = useState<InstructionsText>({
    queue: "",
    claim: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (view.name !== "queue") return;
    let cancelled = false;
    const load = () => {
      void fetchClaims()
        .then((next) => {
          if (!cancelled) setClaims(next);
        })
        .catch(() => {
          if (!cancelled) setError("Could not load the claims queue.");
        });
    };
    load();
    const timer = window.setInterval(load, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [view]);

  useEffect(() => {
    if (view.name !== "claim") return;
    const claimId = view.claimId;
    let cancelled = false;
    const load = () => {
      void fetchClaim(claimId)
        .then((next) => {
          if (!cancelled) setClaim(next);
        })
        .catch(() => {
          if (!cancelled) setError("Could not load the claim.");
        });
    };
    load();
    const timer = window.setInterval(load, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [view]);

  useEffect(() => {
    if (view.name !== "instructions") return;
    void fetchInstructions()
      .then(setInstructions)
      .catch(() => {
        setError("Could not load instructions.");
      });
  }, [view]);

  async function handleSignOff() {
    if (claim?.payout == null) return;
    const claimId = claim.claim_id;
    const amount = claim.payout;
    setBusy(true);
    setError("");
    try {
      await signOffAndPay(claimId, amount);
      setClaim(await fetchClaim(claimId));
    } catch {
      setError("Sign-off failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRun() {
    if (!claim) return;
    setBusy(true);
    setError("");
    try {
      await startAgent(claim.claim_id);
      setClaim(await fetchClaim(claim.claim_id));
    } catch {
      setError("Could not start the agent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="brand">
        <div>
          <h1>UnderCover</h1>
          <p className="tagline">Claims desk for travel insurance handlers</p>
        </div>
        <nav>
          <button
            type="button"
            className={view.name === "queue" ? "active" : undefined}
            onClick={() => {
              setError("");
              setView({ name: "queue" });
            }}
          >
            Queue
          </button>
          <button
            type="button"
            className={view.name === "instructions" ? "active" : undefined}
            onClick={() => {
              setError("");
              setView({ name: "instructions" });
            }}
          >
            Instructions
          </button>
        </nav>
      </header>

      {error && <p className="error">{error}</p>}

      {view.name === "queue" && (
        <Queue
          claims={claims}
          onOpen={(claimId) => {
            setError("");
            setClaim(null);
            setView({ name: "claim", claimId });
          }}
        />
      )}

      {view.name === "claim" && claim && (
        <ClaimView
          claim={claim}
          busy={busy}
          onBack={() => {
            setError("");
            setView({ name: "queue" });
          }}
          onSignOff={() => {
            void handleSignOff();
          }}
          onRun={() => {
            void handleRun();
          }}
        />
      )}

      {view.name === "claim" && !claim && !error && (
        <section className="panel">
          <p>Loading claim…</p>
        </section>
      )}

      {view.name === "instructions" && (
        <Instructions queue={instructions.queue} claim={instructions.claim} />
      )}
    </div>
  );
}
