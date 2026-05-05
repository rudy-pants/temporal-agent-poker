import asyncio
from uuid import uuid4

from temporalio.client import Client

from env.poker_env import PokerEnv
from workflow.types import Action, Observation


def display_state(obs: Observation):
    print(f"\n{'='*50}")
    print(f"  Street: {obs.street}")
    print(f"  Your hand: {' '.join(obs.hole_cards)}")
    print(f"  Board: {' '.join(obs.board_cards) or '(none)'}")
    print(f"  Pot: {obs.pot}")
    print(f"  Your stack: {obs.stacks[obs.player_index]}")
    print(f"  Opponent stack: {obs.stacks[1 - obs.player_index]}")
    if obs.current_bet > 0:
        print(f"  To call: {obs.current_bet}")
    print(f"\n  Actions:")
    print(f"    f = fold")
    print(f"    c = check/call")
    if obs.min_raise > 0:
        print(f"    r <amount> = raise (min {obs.min_raise}, max {obs.max_raise})")
    print(f"{'='*50}")


def get_human_action(obs: Observation) -> Action:
    while True:
        choice = input("  > ").strip().lower()
        if choice == "f":
            return Action("fold")
        elif choice == "c":
            return Action("check_or_call")
        elif choice.startswith("r"):
            parts = choice.split()
            if len(parts) == 2:
                try:
                    amount = int(parts[1])
                    if obs.min_raise <= amount <= obs.max_raise:
                        return Action("raise", amount)
                    print(f"    Amount must be between {obs.min_raise} and {obs.max_raise}")
                    continue
                except ValueError:
                    pass
            elif obs.min_raise > 0:
                return Action("raise", obs.min_raise)
        print("    Invalid input. Use: f, c, or r <amount>")


async def main():
    client = await Client.connect("localhost:7233")
    env = PokerEnv(client, player_index=0)

    print("\n  Poker vs GPT Agent")
    print("  ==================")
    print("  Starting stack: 200 chips each")
    print("  Blinds: 1/2\n")

    while True:
        game_id = f"poker-{uuid4()}"
        config = {
            "small_blind": 1,
            "big_blind": 2,
            "starting_stack": 200,
            "player_count": 2,
        }

        print("\n  Dealing new hand...")
        obs = await env.reset(game_id=game_id, config=config)

        while not obs.terminal:
            if obs.is_my_turn:
                display_state(obs)
                action = get_human_action(obs)
                obs, payoff, done, info = await env.step(action)
            else:
                print("\n  GPT is thinking...")
                obs = await env._wait_for_turn()

        # Hand complete
        print(f"\n  {'='*50}")
        print(f"  Hand over!")
        print(f"  Board: {' '.join(obs.board_cards)}")
        print(f"  Result: {'+' if obs.payoff > 0 else ''}{obs.payoff} chips")
        print(f"  Stacks: You={obs.stacks[0]}, GPT={obs.stacks[1]}")
        print(f"  {'='*50}")

        again = input("\n  Play another hand? (y/n): ").strip().lower()
        if again != "y":
            print("\n  Thanks for playing!")
            break


if __name__ == "__main__":
    asyncio.run(main())
