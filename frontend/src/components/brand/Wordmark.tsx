type WordmarkProps = {
  tag?: string;
  className?: string;
};

export function Wordmark({ tag = "ALPHA", className = "" }: WordmarkProps) {
  return (
    <span className={`wordmark inline-flex items-baseline gap-2 text-fg ${className}`}>
      BRYT
      {tag && <span className="text-fg-subtle font-semibold tracking-[0.12em]">{`// ${tag}`}</span>}
    </span>
  );
}
