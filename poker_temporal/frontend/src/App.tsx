import { useState } from "react";
import { useGameSocket } from "./hooks/useGameSocket";
import { PokerTable } from "./components/PokerTable";
import { EventLog } from "./components/EventLog";
import "./styles/table.css";

function App() {
  const [gameId, setGameId] = useState<string | null>(null);
  const { observation, connected, events, sendAction } = useGameSocket(gameId);

  const startNewGame = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/new-game", {
        method: "POST",
      });
      const data = await res.json();
      setGameId(data.game_id);
    } catch (e) {
      console.error("Failed to start game:", e);
    }
  };

  if (!gameId || !observation) {
    return (
      <div className="app-container">
        <div className="lobby">
          <h1>Poker vs GPT</h1>
          <p>No-Limit Texas Hold'em &bull; Powered by Temporal</p>
          <button className="btn btn-start" onClick={startNewGame}>
            {gameId ? "Connecting..." : "New Game"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <div className="game-layout">
        <div className="table-section">
          <div className="game-header">
            <span className={`connection-status ${connected ? "on" : "off"}`}>
              ● {connected ? "Connected" : "Disconnected"}
            </span>
            <span className="game-id">ID: {gameId.slice(0, 12)}...</span>
          </div>
          <PokerTable observation={observation} onAction={sendAction} />
          {observation.terminal && (
            observation.stacks[0] <= 0 || observation.stacks[1] <= 0 ? (
              <div className="game-over">
                <h2>{observation.stacks[0] > 0 ? "You Win!" : "GPT Wins!"}</h2>
                <button className="btn btn-start" onClick={startNewGame}>
                  New Game
                </button>
              </div>
            ) : (
              <div className="next-hand-notice">Next hand starting...</div>
            )
          )}
        </div>
        <div className="log-section">
          <EventLog events={events} />
        </div>
      </div>
    </div>
  );
}

export default App;
