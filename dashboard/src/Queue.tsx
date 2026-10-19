import { formatUsd } from "./money";
import { countByDecision, countByStatus } from "./queueStats";
import { statusClass, statusLabel } from "./statusLabel";
import type { QueueClaim } from "./types";

interface Props {
  readonly claims: QueueClaim[];
  readonly onOpen: (claimId: string) => void;
}

export function Queue({ claims, onOpen }: Readonly<Props>) {
  const statusCounts = countByStatus(claims);
  const decisionCounts = countByDecision(claims);

  return (
    <section className="panel">
      <h2>Claims queue</h2>
      <p className="lede">
        {claims.length} claims in the queue. Where each claim stands for the
        handlers.
      </p>

      <div className="queue-counts">
        <div>
          <h3>By status</h3>
          <ul>
            {statusCounts.map((row) => (
              <li key={row.status}>
                <span className={statusClass(row.status)}>{row.label}</span>
                <span className="mono count">{row.count}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3>By decision</h3>
          <ul>
            {decisionCounts.map((row) => (
              <li key={row.decision}>
                <span className={`decision-chip decision-${row.decision}`}>
                  {row.label}
                </span>
                <span className="mono count">{row.count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <table className="queue-table">
        <thead>
          <tr>
            <th>Claim</th>
            <th>Customer</th>
            <th>Summary</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Decision</th>
            <th>Payout</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((claim) => (
            <tr key={claim.claim_id}>
              <td>
                <button
                  type="button"
                  className="link mono"
                  onClick={() => {
                    onOpen(claim.claim_id);
                  }}
                >
                  {claim.claim_id}
                </button>
              </td>
              <td>{claim.customer_name}</td>
              <td>{claim.summary}</td>
              <td className="mono">{formatUsd(claim.amount_claimed)}</td>
              <td>
                <span className={statusClass(claim.status)}>
                  {statusLabel(claim.status)}
                </span>
              </td>
              <td>{claim.decision ?? "—"}</td>
              <td className="mono">
                {claim.payout === null ? "—" : formatUsd(claim.payout)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
