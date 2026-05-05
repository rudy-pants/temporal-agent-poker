import { useState } from "react";
import type { Observation } from "../types";

interface ActionPanelProps {
  observation: Observation;
  onAction: (type: string, amount?: number) => void;
}

function getLastGPTAction(observation: Observation): string | null {
  const history = observation.history;
  for (let i = history.length - 1; i >= 0; i--) {
    if (history[i].player_index === 1) {
      const action = history[i].action;
      if (action.type === "fold") return "GPT folded";
      if (action.type === "check_or_call") {
        return action.amount ? `GPT called $${action.amount}` : "GPT checked";
      }
      if (action.type === "raise") return `GPT raised to $${action.amount}`;
      return `GPT: ${action.type}`;
    }
  }
  return null;
}

export function ActionPanel({ observation, onAction }: ActionPanelProps) {
  const [raiseAmount, setRaiseAmount] = useState(observation.min_raise);
  const { is_my_turn, current_bet, min_raise, max_raise } = observation;

  const lastGPTAction = getLastGPTAction(observation);

  if (!is_my_turn) {
    return (
      <div className="action-panel waiting">
        <div className="thinking-indicator">
          <span className="dot">●</span> GPT is thinking...
        </div>
      </div>
    );
  }

  return (
    <div className="action-panel">
      {lastGPTAction && (
        <div className="gpt-action-badge">{lastGPTAction}</div>
      )}
      <button className="btn btn-fold" onClick={() => onAction("fold")}>
        Fold
      </button>

      <button className="btn btn-call" onClick={() => onAction("check_or_call")}>
        {current_bet > 0 ? `Call $${current_bet}` : "Check"}
      </button>

      {min_raise > 0 && (
        <div className="raise-group">
          <input
            type="range"
            min={min_raise}
            max={max_raise}
            value={raiseAmount}
            onChange={(e) => setRaiseAmount(Number(e.target.value))}
          />
          <button
            className="btn btn-raise"
            onClick={() => onAction("raise", raiseAmount)}
          >
            Raise to ${raiseAmount}
          </button>
        </div>
      )}
    </div>
  );
}
