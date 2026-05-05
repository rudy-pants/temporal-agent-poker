interface PotDisplayProps {
  pot: number;
  street: string;
}

export function PotDisplay({ pot, street }: PotDisplayProps) {
  return (
    <div className="pot-display">
      <div className="pot-amount">${pot}</div>
      <div className="pot-street">{street}</div>
    </div>
  );
}
