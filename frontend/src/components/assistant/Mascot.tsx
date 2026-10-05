/**
 * The ImmobIA helper: the tall house from the brand symbol, with a face on the facade.
 * Its roof line is the brand's growth line, and the point at its tip blinks when there is news.
 */
export function Mascot({ alert = false, size = 44 }: { alert?: boolean; size?: number }) {
  return (
    <svg aria-hidden="true" className={alert ? "mascot alert" : "mascot"} height={size} viewBox="0 0 64 64" width={size}>
      <path className="mascot-body" d="M15 58 V35 L32 18 L49 35 V58 Z" fill="#0f5c66" stroke="#0f5c66" strokeLinejoin="round" strokeWidth="2" />
      <rect fill="#ffffff" height="11" rx="1" width="7" x="28.5" y="47" />
      <g className="mascot-eyes" fill="#ffffff">
        <ellipse cx="26" cy="37" rx="3.4" ry="3.9" />
        <ellipse cx="38" cy="37" rx="3.4" ry="3.9" />
      </g>
      <g className="mascot-pupils" fill="#15191b">
        <circle cx="26.8" cy="37.6" r="1.6" />
        <circle cx="38.8" cy="37.6" r="1.6" />
      </g>
      <path d="M8 34.5 L30 12.5" fill="none" stroke="#f5c518" strokeLinecap="round" strokeWidth="3.4" />
      <circle className="mascot-dot" cx="31" cy="11.5" fill="#f5c518" r="3.6" />
    </svg>
  );
}
