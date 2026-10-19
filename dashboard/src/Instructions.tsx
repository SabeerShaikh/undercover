interface Props {
  readonly text: string;
}

export function Instructions({ text }: Readonly<Props>) {
  return (
    <section className="panel">
      <h2>Agent instructions</h2>
      <p className="lede accent">
        Read only. The agent loads these from the API.
      </p>
      <pre className="instructions">{text}</pre>
    </section>
  );
}
