import type { GameEvent } from "../types";

interface EventLogProps {
  events: GameEvent[];
}

export function EventLog({ events }: EventLogProps) {
  return (
    <div className="event-log">
      <div className="event-log-header">
        <span>Event Log (Temporal Signals)</span>
        <span className="live-dot">● LIVE</span>
      </div>
      <div className="event-log-body">
        {events.map((event, i) => (
          <div key={i} className="event-entry">
            <span className="event-time">
              {event.time.toLocaleTimeString()}
            </span>
            <span className="event-message">{event.message}</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="event-entry empty">Waiting for game to start...</div>
        )}
      </div>
    </div>
  );
}
