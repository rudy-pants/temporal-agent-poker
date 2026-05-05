import { Card } from "./Card";
import type { Observation } from "../types";

interface OpponentHandProps {
  stack: number;
  isActive: boolean;
  revealedCards?: string[];
  lastAction?: string;
}

export function OpponentHand({ stack, isActive, revealedCards, lastAction }: OpponentHandProps) {
  const showCards = revealedCards && revealedCards.length > 0;

  return (
    <div className={`player-hand opponent ${isActive ? "active" : ""}`}>
      <div className="player-label">GPT Agent</div>
      <div className="player-cards">
        {showCards ? (
          revealedCards.map((c, i) => <Card key={i} card={c} />)
        ) : (
          <>
            <Card card="" faceDown />
            <Card card="" faceDown />
          </>
        )}
      </div>
      <div className="player-stack">${stack}</div>
      {lastAction && <div className="opponent-action-badge">{lastAction}</div>}
    </div>
  );
}

export function getLastGPTAction(observation: Observation): string | null {
  const history = observation.history;
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].player_index === 1) {
      const action = history[i].action;
      if (action.type === "fold") return "Folded";
      if (action.type === "check_or_call") {
        return observation.current_bet > 0 ? "Called" : "Checked";
      }
      if (action.type === "raise") return `Raised to $${action.amount}`;
      return action.type;
    }
  }
  return null;
}
