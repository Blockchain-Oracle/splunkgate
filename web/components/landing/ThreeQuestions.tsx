import { SectionHead } from "../shared/SectionHead";

const QUESTIONS = [
  {
    n: "01",
    side: "input",
    tag: "on the way in",
    q: "Is this user input a prompt injection?",
    p: "Before the model ever sees it, the message is scanned at the model boundary. A cheap 9-regex first pass from splunklib.security catches the obvious; anything ambiguous escalates to Cisco AI Defense.",
    ex: "verdict=BLOCK · rules=[Prompt Injection]",
    cls: "v-block",
  },
  {
    n: "02",
    side: "output",
    tag: "on the way out",
    q: "Does this output leak PII, PHI, PCI, secrets or source?",
    p: "After inference, the response is checked before it returns to the caller. Six of the eleven Cisco rules cover sensitive-data classes; a hit can BLOCK or MODIFY the output in place.",
    ex: "verdict=MODIFY · rules=[PII, PCI]",
    cls: "v-mod",
  },
  {
    n: "03",
    side: "tool",
    tag: "before it acts",
    q: "Is this tool call's argument set safe to execute?",
    p: "The tool middleware inspects arguments before the call fires. If the verdict is BLOCK, the handler is never invoked — the dangerous action simply does not happen.",
    ex: "verdict=BLOCK · handler never called",
    cls: "v-block",
  },
];

export function ThreeQuestions() {
  return (
    <section className="ag-sec-wrap sec" id="how">
      <div className="wrap">
        <SectionHead
          kicker="What it actually does"
          title="Three questions, asked in real time."
          lead="SplunkGate is not a dashboard you check after the fact. It sits in the agent's path and answers three questions on every turn — and acts on the answer before anything irreversible happens."
        />
        <div className="card-grid cols-3 rv tq-grid">
          {QUESTIONS.map((q) => (
            <div className={"tq tq-" + q.side} key={q.n}>
              <div className="tq-top">
                <span className="tq-n mono">{q.n}</span>
                <span className="tq-tag mono">{q.tag}</span>
              </div>
              <h3 className="tq-q">{q.q}</h3>
              <p className="tq-p">{q.p}</p>
              <div className={"tq-ex mono " + q.cls}>{q.ex}</div>
            </div>
          ))}
        </div>
        <p className="tq-foot mono">
          All three return the <b>same</b> Verdict type — one schema, four surfaces, every answer auditable.
        </p>
      </div>
    </section>
  );
}
