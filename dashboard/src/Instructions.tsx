interface Props {
  readonly queue: string;
  readonly claim: string;
}

export function Instructions({ queue, claim }: Readonly<Props>) {
  return (
    <div className="instructions-page">
      <section className="panel">
        <h2>Running the queue</h2>
        <p className="lede accent">
          Read only. The queue agent loads these from the API.
        </p>
        <pre className="instructions">{queue}</pre>
      </section>
      <section className="panel">
        <h2>Working a claim</h2>
        <p className="lede accent">
          Read only. The claim agent loads these from the API.
        </p>
        <pre className="instructions">{claim}</pre>
      </section>
    </div>
  );
}
