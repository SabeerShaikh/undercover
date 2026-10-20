import { formatUsd } from "./money";
import { countByDecision, countByStatus, decisionLabel } from "./queueStats";
import { statusClass, statusLabel } from "./statusLabel";
import { todoClass, todoLabel } from "./todoStatus";
import type { QueueClaim, QueueRun } from "./types";

interface Props {
  readonly claims: QueueClaim[];
  readonly run: QueueRun | null;
  readonly onOpen: (claimId: string) => void;
}

function TodoContent({
  content,
  onOpen,
}: Readonly<{ content: string; onOpen: (claimId: string) => void }>) {
  const parts = content.split(/(CLM-\d+)/g);
  return (
    <>
      {parts.map((part, index) =>
        /^CLM-\d+$/.test(part) ? (
          <button
            key={`${part}-${String(index)}`}
            type="button"
            className="link"
            onClick={() => {
              onOpen(part);
            }}
          >
            {part}
          </button>
        ) : (
          <span key={`${part}-${String(index)}`}>{part}</span>
        ),
      )}
    </>
  );
}

export function Queue({ claims, run, onOpen }: Readonly<Props>) {
  const statusCounts = countByStatus(claims);
  const decisionCounts = countByDecision(claims);
  const openCount = claims.filter((claim) => claim.status !== "decided").length;

  return (
    <section className="queue">
      <header className="queue-heading">
        <div>
          <h2>Claims queue</h2>
          <p className="lede accent">
            {claims.length} claims · {openCount} still open
          </p>
        </div>
      </header>

      <div className="stats-block">
        <h3 className="stats-label">Status</h3>
        <section className="tiles" aria-label="Claims by status">
          {statusCounts.map((row) => (
            <div
              className={`panel tile${row.count === 0 ? " tile-empty" : ""}`}
              key={row.status}
              aria-label={`${row.label}: ${String(row.count)}`}
            >
              <span className={statusClass(row.status)}>{row.label}</span>
              <span className="tile-count mono">{row.count}</span>
            </div>
          ))}
        </section>
      </div>

      <div className="stats-block">
        <h3 className="stats-label">Decision</h3>
        <section
          className="tiles tiles-decision"
          aria-label="Claims by decision"
        >
          {decisionCounts.map((row) => (
            <div
              className={`panel tile${row.count === 0 ? " tile-empty" : ""}`}
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
      </div>

      <section className="panel run-panel" aria-label="Latest run">
        <h3 className="stats-label">Latest run</h3>
        {run === null ? (
          <p className="lede">No run yet</p>
        ) : (
          <>
            <p className="lede">
              Cap {run.cap} ·{" "}
              {run.status === "running" ? "Running" : "Finished"}
            </p>
            {run.todos.length === 0 ? (
              <p className="lede">No to-do items yet</p>
            ) : (
              <ul className="todo-list">
                {run.todos.map((item, index) => (
                  <li key={`${item.content}-${String(index)}`}>
                    <span className={todoClass(item.status)}>
                      {todoLabel(item.status)}
                    </span>
                    <span>
                      <TodoContent content={item.content} onOpen={onOpen} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {run.status === "finished" && run.summary && (
              <p className="run-summary">{run.summary}</p>
            )}
          </>
        )}
      </section>

      <section className="panel table-scroll">
        <table className="queue-table">
          <thead>
            <tr>
              <th>Claim</th>
              <th>Customer</th>
              <th>Summary</th>
              <th className="num">Claimed</th>
              <th>Status</th>
              <th>Decision</th>
              <th className="num">Payout</th>
            </tr>
          </thead>
          <tbody>
            {claims.map((claim) => (
              <tr
                key={claim.claim_id}
                className="queue-row"
                onClick={() => {
                  onOpen(claim.claim_id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpen(claim.claim_id);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`Open claim ${claim.claim_id}`}
              >
                <td className="mono nowrap">{claim.claim_id}</td>
                <td className="nowrap">{claim.customer_name}</td>
                <td className="summary">{claim.summary}</td>
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
                    <span className="dash">—</span>
                  )}
                </td>
                <td className="num mono">
                  {claim.payout === null ? (
                    <span className="dash">—</span>
                  ) : (
                    formatUsd(claim.payout)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
