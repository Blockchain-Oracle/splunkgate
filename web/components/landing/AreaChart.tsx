// Stacked-area chart used in the Splunk dashboard mockup. Splunk's KPI palette.
// Numbers are deterministic (sinusoidal + small index modulo), so this is safe
// to render server-side — no hydration mismatch.

const W = 560;
const H = 150;
const N = 24;
const SERIES = [
  { c: "#5CB85C", base: 26, amp: 8 }, // allow
  { c: "#F0AD4E", base: 9, amp: 5 }, // modify
  { c: "#D9534F", base: 5, amp: 4 }, // block
];

const valueAt = (i: number, base: number, amp: number) =>
  base + Math.round(amp * (Math.sin(i * 0.7 + base) * 0.5 + 0.5) + (i % 3));

export function AreaChart() {
  const stacks: { col: Array<[number, number]>; total: number }[] = [];
  for (let i = 0; i < N; i++) {
    let acc = 0;
    const col: Array<[number, number]> = [];
    SERIES.forEach((s) => {
      const v = valueAt(i, s.base, s.amp);
      col.push([acc, acc + v]);
      acc += v;
    });
    stacks.push({ col, total: acc });
  }
  const maxTotal = Math.max(...stacks.map((s) => s.total)) * 1.1;
  const x = (i: number) => (i / (N - 1)) * W;
  const y = (v: number) => H - (v / maxTotal) * H;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {SERIES.map((s, si) => {
        let d = `M 0 ${y(stacks[0].col[si][0])} `;
        for (let i = 0; i < N; i++) d += `L ${x(i)} ${y(stacks[i].col[si][1])} `;
        for (let i = N - 1; i >= 0; i--) d += `L ${x(i)} ${y(stacks[i].col[si][0])} `;
        return <path key={si} d={d + "Z"} fill={s.c} fillOpacity="0.85" />;
      })}
    </svg>
  );
}
