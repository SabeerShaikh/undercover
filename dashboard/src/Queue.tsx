import { formatUsd } from "./money";
import { countByDecision, countByStatus, decisionLabel } from "./queueStats";
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
    <section className="queue">
      <h2>Claims queue</h2>
      <p className="lede">
        {claims.length} claims. Where each claim stands for the handlers.
      </p>

      <section className="tiles" aria-label="Claims by status">
        {statusCounts.map((row) => (
          <div
            className="panel tile"
            key={row.status}
            aria-label={`${row.label}: ${String(row.count)}`}
          >
            <span className={statusClass(row.status)}>{row.label}</span>
            <span className="tile-count mono">{row.count}</span>
          </div>
        ))}
      </section>

      <section className="tiles" aria-label="Claims by decision">
        {decisionCounts.map((row) => (
          <div
            className="panel tile"
            key={row.decision}
            aria-label={`${row.label}: ${String(row.count)}`}
          >
            <span className={`decision-chip decision-${row.decision}`}>
              {row.label}
            </span>
            <span className="tile-count mono">{row.count}</span>
          </div>
        ))}
      </section>

      <section className="panel table-scroll">
        <table className="queue-table">
          <thead>
            <tr>
              <th>Claim</th>
              <th>Customer</th>
              <th>Summary</th>
              <th className="num">Amount</th>
              <th>Status</th>
              <th>Decision</th>
              <th className="num">Payout</th>
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
                <td className="num mono">{formatUsd(claim.amount_claimed)}</td>
                <td>
                  <span className={statusClass(claim.status)}>
                    {statusLabel(claim.status)}
                  </span>
                </td>
                <td>
                  {claim.decision ? (
                    <span
                      className={`decision-chip decision-${claim.decision}`}
                    >
                      {decisionLabel(claim.decision)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="num mono">
                  {claim.payout === null ? "—" : formatUsd(claim.payout)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
