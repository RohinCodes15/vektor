/** Decimal strings stay exact: no floating-point arithmetic for money. */
export function moneyInCents(value: string): bigint {
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/.exec(value);
  if (!match || value.length > 128) throw new Error("Invalid money value.");
  const fraction = match[3] ?? "";
  const shift = 2 + Number(match[4] ?? 0) - fraction.length;
  if (Math.abs(shift) > 128) throw new Error("Invalid money precision.");
  const digits = BigInt(`${match[2]}${fraction}`);
  const factor = BigInt(10) ** BigInt(Math.abs(shift));
  if (shift < 0 && digits % factor !== BigInt(0)) throw new Error("Money must be exact to cents.");
  const cents = shift < 0 ? digits / factor : digits * factor;
  return match[1] ? -cents : cents;
}

export function formatMoney(value: string | null): string {
  return value === null ? "Unavailable" : formatCents(moneyInCents(value));
}

function formatCents(cents: bigint): string {
  const negative = cents < BigInt(0);
  const absolute = negative ? -cents : cents;
  return `${negative ? "−" : ""}$${(absolute / BigInt(100)).toLocaleString("en-US")}.${String(absolute % BigInt(100)).padStart(2, "0")}`;
}
