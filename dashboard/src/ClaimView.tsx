import { formatUsd } from "./money";
import { statusClass, statusLabel } from "./statusLabel";
import type { ClaimDetail, ClaimStep } from "./types";

function stepLine(step: ClaimStep) {
  if (step.tool_name === "reading") {
    return <>Read {step.detail}</>;
  }
  if (step.tool_name === "error") {
    return <>Failed {step.detail}</>;
  }
  return (
    <>
      <span className="mono">{step.tool_name}</span>: {step.detail}
    </>
  );
}

function uniqueReadings(steps: ClaimStep[]): string[] {
  const readings: string[] = [];
  const seen = new Set<string>();
  for (const step of steps) {
    if (step.tool_name === "reading" && !seen.has(step.detail)) {
      seen.add(step.detail);
      readings.push(step.detail);
    }
  }
  return readings;
}

function ClaimNotices({ claim }: Readonly<{ claim: ClaimDetail }>) {
  if (claim.status === "left_for_handler") {
    return (
      <p className="notice">
        This claim was left for a handler after two failed attempts.
      </p>
    );
  }
  if (claim.status === "waiting" && claim.attempts > 0) {
    return (
      <p className="notice">This claim came back after a failed attempt.</p>
    );
  }
  return null;
}

function ClaimActions({
  claim,
  busy,
  onSignOff,
  onRun,
}: Readonly<{
  claim: ClaimDetail;
  busy: boolean;
  onSignOff: () => void;
  onRun: () => void;
}>) {
  const canRun =
    claim.status === "waiting" ||
    (claim.status === "in_progress" && !claim.decision);
  return (
    <div className="actions">
      {canRun && (
        <button type="button" disabled={busy} onClick={onRun}>
          Run agent
        </button>
      )}
      {claim.status === "waiting_for_sign_off" && (
        <button type="button" disabled={busy} onClick={onSignOff}>
          Sign off and pay
        </button>
      )}
    </div>
  );
}

interface Props {
  readonly claim: ClaimDetail;
  readonly busy: boolean;
  readonly onSignOff: () => void;
  readonly onRun: () => void;
  readonly onBack: () => void;
}

export function ClaimView({
  claim,
  busy,
  onSignOff,
  onRun,
  onBack,
}: Readonly<Props>) {
  const planName = claim.plan?.name ?? claim.policy.plan;
  const readings = uniqueReadings(claim.steps);
  return (
    <section className="panel claim">
      <button type="button" className="link" onClick={onBack}>
        Back to queue
      </button>
      <header className="claim-header">
        <div>
          <h2 className="mono">{claim.claim_id}</h2>
          <p className="lede">{claim.summary}</p>
        </div>
        <span className={statusClass(claim.status)}>
          {statusLabel(claim.status)}
        </span>
      </header>

      <ClaimNotices claim={claim} />
      <ClaimActions
        claim={claim}
        busy={busy}
        onSignOff={onSignOff}
        onRun={onRun}
      />

      <div className="grid">
        <article>
          <h3>Story</h3>
          <p>{claim.story}</p>
        </article>
        <article>
          <h3>Customer</h3>
          <p>{claim.customer.name}</p>
          <p className="mono">
            {claim.policy.policy_id} · {planName}
          </p>
          <p>
            Trip to {claim.policy.trip.destination} (
            {claim.policy.trip.departs_on} to {claim.policy.trip.returns_on})
          </p>
          {claim.customer.previous_claims.length > 0 && (
            <>
              <h4>Previous claims</h4>
              <ul>
                {claim.customer.previous_claims.map((previous) => (
                  <li key={previous.claim_id}>
                    <span className="mono">{previous.claim_id}</span>:{" "}
                    {previous.summary} ({previous.outcome},{" "}
                    {formatUsd(previous.amount_paid)})
                  </li>
                ))}
              </ul>
            </>
          )}
        </article>
      </div>

      <article>
        <h3>Items claimed ({formatUsd(claim.amount_claimed)})</h3>
        <ul>
          {claim.items.map((item) => (
            <li key={`${item.description}-${String(item.amount)}`}>
              {item.description} · {item.category} · {formatUsd(item.amount)}
            </li>
          ))}
        </ul>
      </article>

      <article>
        <h3>Documents</h3>
        {claim.documents.map((document) => (
          <details key={document.name}>
            <summary>
              {document.name} ({document.type})
            </summary>
            <p>{document.content}</p>
          </details>
        ))}
      </article>

      {claim.decision && (
        <article className="decision">
          <h3>Decision</h3>
          <p>
            <strong>{claim.decision}</strong>
            {claim.payout !== null && <> · {formatUsd(claim.payout)}</>}
            {claim.paid_amount !== null && (
              <> · paid {formatUsd(claim.paid_amount)}</>
            )}
          </p>
          <p>{claim.reason}</p>
          {claim.policy_section && (
            <p className="accent">{claim.policy_section}</p>
          )}
        </article>
      )}

      {readings.length > 0 && (
        <article>
          <h3>Sections read</h3>
          <ul>
            {readings.map((detail) => (
              <li key={detail}>{detail}</li>
            ))}
          </ul>
        </article>
      )}

      {claim.steps.length > 0 && (
        <article>
          <h3>Agent steps</h3>
          <ol className="steps">
            {claim.steps.map((step, index) => (
              <li key={`${step.tool_name}-${String(index)}`}>
                {stepLine(step)}
              </li>
            ))}
          </ol>
        </article>
      )}
    </section>
  );
}
