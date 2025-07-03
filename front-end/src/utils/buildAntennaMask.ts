/**
 * Converts a list of 1-based antenna IDs to a hex string mask (8 chars, upper-case, with 0x prefix).
 * Example: [1,2] → "0x00000003"
 */
export function buildAntennaMaskHex(antennaIds: number[]): string {
  let mask = 0;
  for (const aid of antennaIds) {
    if (aid < 1 || aid > 32) {
      throw new Error(`Antenna ID ${aid} ngoài phạm vi hợp lệ (1-32)`);
    }
    mask |= (1 << (aid - 1));
  }
  return `0x${mask.toString(16).toUpperCase().padStart(8, "0")}`;
}