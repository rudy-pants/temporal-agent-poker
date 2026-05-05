import { useState, useEffect, useCallback, useRef } from "react";
import type { Observation, GameEvent } from "../types";

interface GameState {
  observation: Observation | null;
  connected: boolean;
  events: GameEvent[];
}

export function useGameSocket(gameId: string | null) {
  const [state, setState] = useState<GameState>({
    observation: null,
    connected: false,
    events: [],
  });
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!gameId) return;

    const socket = new WebSocket(`ws://localhost:8000/ws/game/${gameId}`);
    ws.current = socket;

    socket.onopen = () => {
      setState((s) => ({ ...s, connected: true }));
    };

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "state_update") {
        setState((s) => ({
          ...s,
          observation: msg.observation,
          events: [
            ...s.events,
            {
              time: new Date(),
              message: formatEvent(msg.observation, s.observation),
            },
          ],
        }));
      } else if (msg.type === "hand_complete") {
        setState((s) => ({
          ...s,
          events: [
            ...s.events,
            { time: new Date(), message: `Hand complete. Payoff: ${msg.payoff}` },
          ],
        }));
      }
    };

    socket.onclose = () => {
      setState((s) => ({ ...s, connected: false }));
    };

    return () => {
      socket.close();
    };
  }, [gameId]);

  const sendAction = useCallback((type: string, amount?: number) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(
        JSON.stringify({ type: "action", action_type: type, amount: amount || 0 })
      );
    }
  }, []);

  return { ...state, sendAction };
}

function formatEvent(
  current: Observation,
  previous: Observation | null
): string {
  if (!previous) return "Game started. Cards dealt.";
  if (current.street !== previous.street) return `${current.street} dealt: ${current.board_cards.join(" ")}`;
  if (current.terminal) return "Hand complete.";
  const lastAction = current.history[current.history.length - 1];
  if (lastAction) {
    const amt = lastAction.action.amount ? ` ${lastAction.action.amount}` : "";
    const player = lastAction.player_index === 0 ? "You" : "GPT";
    return `${player}: ${lastAction.action.type}${amt}`;
  }
  return "State updated.";
}
