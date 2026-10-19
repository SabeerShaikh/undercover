import { formatUsd } from "./money";
import { statusClass, statusLabel } from "./statusLabel";
import type { QueueClaim } from "./types";

interface Props {
  readonly claims: QueueClaim[];
  readonly onOpen: (claimId: string) => void;
}

export function Queue({ claims, onOpen }: Readonly<Props>) {
  return (
    <section className="panel">
      <h2>Claims queue</h2>
      <p className="lede">Where each claim stands for the handlers.</p>
      <table className="queue-table">
        <thead>
          <tr>
            <th>Claim</th>
            <th>Customer</th>
            <th>Summary</th>
            <th>Amount</th>
            <th>Status</th>
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
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
