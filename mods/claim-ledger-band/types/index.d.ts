// claim-ledger-band's state: what the band and its pane show of the last turn
// of the session's main loop to end.

/** How the band's line is coloured. What the line says is the appendix's. */
export type BandLevel = 'error' | 'warn' | 'note' | 'quiet'

export type Shown = {
  /** The band's one line, as band.py made it. */
  band: string
  level: BandLevel
  /** The appendix as the Stop hook wrote it; null when the turn left none. */
  appendix: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'claim-ledger-band': { shown: Shaped<Shown | null> }
  }
}
