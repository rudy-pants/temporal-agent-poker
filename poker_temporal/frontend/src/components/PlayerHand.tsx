import { Card } from "./Card";

interface PlayerHandProps {
  cards: string[];
  label: string;
  stack: number;
  isActive: boolean;
}

export function PlayerHand({ cards, label, stack, isActive }: PlayerHandProps) {
  return (
    <div className={`player-hand ${isActive ? "active" : ""}`}>
      <div className="player-label">{label}</div>
      <div className="player-cards">
        {cards.map((c, i) => (
          <Card key={i} card={c} />
        ))}
      </div>
      <div className="player-stack">${stack}</div>
    </div>
  );
}
