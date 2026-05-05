export interface Observation {
  hole_cards: string[];
  board_cards: string[];
  pot: number;
  stacks: number[];
  current_bet: number;
  min_raise: number;
  max_raise: number;
  player_index: number;
  actor_index: number | null;
  is_my_turn: boolean;
  street: string;
  active_players: number[];
  history: ActionRecord[];
  terminal: boolean;
  payoff: number;
  opponent_cards: string[];
}

export interface Action {
  type: "fold" | "check_or_call" | "raise";
  amount: number;
}

export interface ActionRecord {
  player_index: number;
  action: Action;
  street: string;
}

export interface GameEvent {
  time: Date;
  message: string;
}
