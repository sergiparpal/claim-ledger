import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { BandLevel, Shown } from '../types'

// claim-ledger's appendix, kept in view: one line in the band above the
// prompt, and all of it in a pane the band's button opens.
//
// band.py, in this plugin's folder, finds the appendix the turn's Stop hook
// left in the transcript and makes the line; this module draws what it prints
// and nothing else. What a mod draws never enters the model's context, so the
// agent is not taught which claims get caught (SPEC § Traps), and the turn is
// handed on as it came: the report is not edited (I-10).

const PANE = 'claim-ledger'
const READ_MS = 10_000
const RETRY_MS = 1_000

// Change the tag when Shown's fields change: it declines what an earlier
// version stored, which outlives a reload.
const shown = atom({ plugin: 'claim-ledger-band', key: 'shown' } as const, null, {
  shape: 'shown-1',
})

const LEVELS: readonly string[] = ['error', 'warn', 'note', 'quiet']

export const register: Register = on => {
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) {
      return result // a subagent's turn: claim-ledger audits the main loop's
    }
    let turn = await readTurn($, e.reason)
    if (turn.appendix === null && e.reason === 'answer'
        && next.budget.remainingMs > 3 * RETRY_MS) {
      // The Stop hook's row can reach the transcript a moment late: look again.
      await $.clock.sleep(RETRY_MS, { signal: next.signal })
      turn = await readTurn($, e.reason)
    }
    await update($, shown, () => turn)
    return result
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const turn = await read($, shown)
    if (e.props.hasSurvey || turn === null) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)

    return (
      <Box>
        <Text {...tone(turn.level, e.props.isWorking)}>{turn.band} </Text>
        <Button
          key="open"
          label="Open"
          onPress={() => $.ui.open({ id: PANE, title: 'claim-ledger' })}
        />
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const turn = await read($, shown)
    if (turn === null) {
      return <Text dimColor>No turn has ended in this session yet.</Text>
    }
    if (turn.appendix === null || e.props.placement === 'widget') {
      return <Text {...tone(turn.level)}>{turn.band}</Text>
    }
    const isSummarised = turn.band !== turn.appendix

    return (
      <Box flexDirection="column">
        {isSummarised && <Text {...tone(turn.level)}>{turn.band}</Text>}
        {isSummarised && <Text> </Text>}
        {turn.appendix.split('\n').map(line => (
          <Text mono>{line === '' ? ' ' : line}</Text>
        ))}
      </Box>
    )
  })
}

async function readTurn($: EngineInterface, reason: string): Promise<Shown> {
  try {
    const { transcriptPath } = await $.session.info()
    const ran = await $.process.run(
      ['python3', '-I', `${$.plugin.root}/band.py`, transcriptPath, reason],
      { timeoutMs: READ_MS },
    )
    if (ran.exitCode !== 0) {
      return failed(`band.py exited with ${ran.exitCode}: ${ran.stderr}`)
    }
    return parse(ran.stdout)
  } catch (error) {
    return failed(error instanceof Error ? error.message : String(error))
  }
}

function parse(stdout: string): Shown {
  const value: unknown = JSON.parse(stdout)
  if (typeof value === 'object' && value !== null) {
    const { band, level, appendix } = value as Record<string, unknown>
    if (typeof band === 'string' && typeof level === 'string' && LEVELS.includes(level)
        && (typeof appendix === 'string' || appendix === null)) {
      return { band, level: level as BandLevel, appendix }
    }
  }
  return failed('band.py printed something it never prints')
}

// A band that cannot read the turn says so, as an error: a turn it could not
// read is a turn whose audit nobody sees (I-9).
function failed(why: string): Shown {
  const last = why.split('\n').map(line => line.trim()).filter(line => line !== '')
    .at(-1) ?? 'no reason given'

  return {
    band: `claim-ledger · the band could not read this turn: ${last.slice(0, 160)}`,
    level: 'error',
    appendix: null,
  }
}

function tone(level: BandLevel, isWorking = false) {
  if (isWorking || level === 'quiet') {
    return { dimColor: true }
  }
  if (level === 'error') {
    return { color: 'error' }
  }
  if (level === 'warn') {
    return { color: 'warning' }
  }
  return {}
}
