interface CardProps {
  card: string;
  faceDown?: boolean;
}

const SUIT_SYMBOLS: Record<string, string> = {
  h: "♥",
  d: "♦",
  c: "♣",
  s: "♠",
};

const SUIT_COLORS: Record<string, string> = {
  h: "#e74c3c",
  d: "#e74c3c",
  c: "#2c3e50",
  s: "#2c3e50",
};

export function Card({ card, faceDown }: CardProps) {
  if (faceDown) {
    return <div className="card card-back">🂠</div>;
  }

  const rawRank = card.slice(0, -1).toUpperCase();
  const rank = rawRank === "T" ? "10" : rawRank;
  const suit = card.slice(-1);
  const symbol = SUIT_SYMBOLS[suit] || suit;
  const color = SUIT_COLORS[suit] || "#2c3e50";

  return (
    <div className="card" style={{ color }}>
      <span className="card-rank">{rank}</span>
      <span className="card-suit">{symbol}</span>
    </div>
  );
}
