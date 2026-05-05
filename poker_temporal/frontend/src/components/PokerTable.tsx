import type { Observation } from "../types";
import { Card } from "./Card";
import { PlayerHand } from "./PlayerHand";
import { OpponentHand, getLastGPTAction } from "./OpponentHand";
import { PotDisplay } from "./PotDisplay";
import { ActionPanel } from "./ActionPanel";

interface PokerTableProps {
  observation: Observation;
  onAction: (type: string, amount?: number) => void;
}

export function PokerTable({ observation, onAction }: PokerTableProps) {
  const {
    hole_cards,
    board_cards,
    pot,
    stacks,
    street,
    is_my_turn,
    terminal,
    payoff,
    actor_index,
  } = observation;

  const lastGPTAction = getLastGPTAction(observation);

  return (
    <div className="poker-table">
      {/* Opponent at top */}
      <OpponentHand
        stack={stacks[1] || 0}
        isActive={actor_index === 1}
        revealedCards={terminal ? observation.opponent_cards : undefined}
        lastAction={lastGPTAction || undefined}
      />

      {/* Community cards + pot in center */}
      <div className="table-center">
        <PotDisplay pot={pot} street={street} />
        <div className="community-cards">
          {board_cards.length > 0 ? (
            board_cards.map((c, i) => <Card key={i} card={c} />)
          ) : (
            <div className="no-cards">No community cards yet</div>
          )}
        </div>
      </div>

      {/* Result overlay */}
      {terminal && (
        <div className="result-overlay">
          <div className={`result ${payoff > 0 ? "win" : payoff < 0 ? "lose" : "push"}`}>
            {payoff > 0 ? `+$${payoff}` : payoff < 0 ? `-$${Math.abs(payoff)}` : "Push"}
          </div>
        </div>
      )}

      {/* Player at bottom */}
      <PlayerHand
        cards={hole_cards}
        label="You"
        stack={stacks[0] || 0}
        isActive={is_my_turn}
      />

      {/* Action panel */}
      {!terminal && <ActionPanel observation={observation} onAction={onAction} />}
    </div>
  );
}
