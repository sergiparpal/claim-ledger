import { expect, mock, test } from 'claude-code/testing'

// band.py's own rules are held in tests/test_band.py, under the repository's
// suite. These hold the module to drawing what band.py prints, to asking it
// about this session's transcript, and to handing the turn on as it came.

const PLUGIN = 'claim-ledger-band'
const TRANSCRIPT = '/home/u/.claude/projects/p/session.jsonl'
const SURFACES = ['terminal', 'desktop'] as const

const BAND = {
  plugin: PLUGIN,
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 100,
    scroll: { offset: 0, bodyRows: 10 },
    view: {},
  },
} as const

const PANE = {
  plugin: PLUGIN,
  component: 'Pane',
  requestId: 'claim-ledger',
  props: {
    title: 'claim-ledger',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const TURN = {
  answer: 'Done: the parser is fixed and the tests pass.',
  durationMs: 1200,
  isAborted: false,
  turnId: 't1',
  reason: 'answer',
} as const

const EXPANDED = [
  'claim-ledger',
  '',
  'STALE',
  '  "the tests pass"',
  '  make verify ok at 2026-11-21T10:00:00.000Z; src/a.py was modified after it ran',
  '',
  '1 verified, 2 unchecked · 1 check seen',
].join('\n')

const STALE = {
  band: 'claim-ledger · STALE 1 · 1 verified, 2 unchecked · 1 check seen',
  level: 'warn',
  appendix: EXPANDED,
}

const MISSING = { band: 'claim-ledger · no appendix for this turn', level: 'error', appendix: null }

type Ran = { exitCode: number; stdout: string; stderr: string }

// Stands for the engine: the session's transcript, band.py answering with
// `answers` in turn (the last one again once they run out), and the turn's own
// result. Its hooks go in before the test's first call on `$`, as the kit
// asks; `answer` changes what band.py prints after that. `runs` holds every
// argv band.py was run with.
function engine(on: Parameters<Parameters<typeof test>[1]>[1], ...first: (object | Ran)[]) {
  const runs: (readonly string[])[] = []
  let answers = first
  let since = 0
  on('session.info', () => ({ value: { transcriptPath: TRANSCRIPT } }))
  on('process.run', (_, e) => {
    runs.push(e.argv)
    since += 1
    const answer = answers[Math.min(since, answers.length) - 1] ?? {}
    const ran = 'exitCode' in answer
      ? answer
      : { exitCode: 0, stdout: JSON.stringify(answer), stderr: '' }
    return { value: { ...ran, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('turn.complete', (_, e) => ({ text: e.answer }))
  return {
    runs,
    answer: (...next: (object | Ran)[]) => {
      answers = next
      since = 0
    },
  }
}

test('an answered turn shows band.py\'s line, and the turn goes on as it came', async ($, on) => {
  engine(on, STALE)

  const result = await $.turn.complete(TURN)
  expect(result.text).toBe(TURN.answer)
  expect((result.by ?? []).includes(PLUGIN)).toBe(false)

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const line = await ui.find({ type: 'Text', text: /STALE 1/ })
    expect(line?.text).toBe(`${STALE.band} `)
    expect(line?.props.color).toBe('warning')
    expect((await ui.find({ type: 'Button', key: 'open' }))?.props.label).toBe('Open')
    await ui.unmount()
  }
})

test('band.py is asked about this session\'s transcript and why the turn ended', async ($, on) => {
  const { runs } = engine(on, STALE)

  await $.turn.complete({ ...TURN, reason: 'aborted', isAborted: true })

  expect(runs.length).toBe(1)
  const [python, isolated, script, transcript, reason] = runs[0] ?? []
  expect([python, isolated, transcript, reason]).toEqual(['python3', '-I', TRANSCRIPT, 'aborted'])
  expect(script?.endsWith('/band.py')).toBe(true)
})

test('a subagent\'s turn is not read, and the band stays as it was', async ($, on) => {
  const { runs } = engine(on, STALE)

  await $.turn.complete({ ...TURN, agentId: 'a1' })

  expect(runs.length).toBe(0)
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /claim-ledger/ })).toBeUndefined()
  await ui.unmount()
})

test('an answered turn with no appendix is looked at once more, then said as an error', async ($, on) => {
  const clock = mock.clock(on)
  const { runs } = engine(on, MISSING)

  const done = $.turn.complete(TURN)
  await clock.settle()
  expect(runs.length).toBe(1)
  await clock.advance(1_000)
  await done
  expect(runs.length).toBe(2)

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  const line = await ui.find({ type: 'Text', text: /no appendix/ })
  expect(line?.text).toBe(`${MISSING.band} `)
  expect(line?.props.color).toBe('error')
  await ui.unmount()
})

test('an appendix found on the second look is the one shown', async ($, on) => {
  const clock = mock.clock(on)
  const { runs } = engine(on, MISSING, STALE)

  const done = $.turn.complete(TURN)
  await clock.advance(1_000)
  await done

  expect(runs.length).toBe(2)
  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect((await ui.find({ type: 'Text', text: /STALE 1/ }))?.text).toBe(`${STALE.band} `)
  await ui.unmount()
})

test('a band.py that fails, or prints what it never prints, is said as an error', async ($, on) => {
  const clock = mock.clock(on)
  const failures: [Ran, RegExp][] = [
    [{ exitCode: 1, stdout: '', stderr: 'Traceback (most recent call last):\nPermissionError: [Errno 13] no' },
      /could not read this turn: PermissionError: \[Errno 13\] no $/],
    [{ exitCode: 0, stdout: 'not json', stderr: '' }, /could not read this turn: /],
    [{ exitCode: 0, stdout: '{"band": "claim-ledger · fine", "level": "great"}', stderr: '' },
      /could not read this turn: band\.py printed something it never prints $/],
  ]
  const band = engine(on)
  for (const [ran, said] of failures) {
    band.answer(ran)
    const done = $.turn.complete(TURN)
    await clock.advance(1_000)
    await done

    const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
    const line = await ui.find({ type: 'Text', text: /could not read/ })
    expect(line?.text).toMatch(said)
    expect(line?.props.color).toBe('error')
    await ui.unmount()
  }
})

test('the band yields to a survey, and dims while a turn runs', async ($, on) => {
  engine(on, STALE)
  await $.turn.complete(TURN)

  const survey = await $.ui.mount({ ...BAND, props: { ...BAND.props, hasSurvey: true }, surface: 'desktop' })
  expect(await survey.find({ type: 'Text', text: /STALE/ })).toBeUndefined()
  await survey.unmount()

  const working = await $.ui.mount({ ...BAND, props: { ...BAND.props, isWorking: true }, surface: 'desktop' })
  expect((await working.find({ type: 'Text', text: /STALE/ }))?.props.dimColor).toBe(true)
  await working.unmount()
})

test('the band\'s button opens the pane, which shows the appendix line by line', async ($, on) => {
  engine(on, STALE)
  const opened: unknown[] = []
  on('ui.open', (_, e) => {
    opened.push(e)
    return { value: { isPlaced: true } }
  })
  await $.turn.complete(TURN)

  const band = await $.ui.mount({ ...BAND, surface: 'desktop' })
  await band.press({ key: 'open' })
  expect(opened).toEqual([{ id: 'claim-ledger', title: 'claim-ledger' }])
  await band.unmount()

  for (const surface of SURFACES) {
    const pane = await $.ui.mount({ ...PANE, surface })
    const texts = (await pane.findAll({ type: 'Text' })).map(t => t.text)
    expect(texts).toEqual([STALE.band, ' ', ...EXPANDED.split('\n').map(l => (l === '' ? ' ' : l))])
    await pane.unmount()
  }
})

test('a one-line appendix is shown once in the pane, and before any turn it says so', async ($, on) => {
  const line = 'claim-ledger · 2 verified, 0 unchecked · 1 check seen · nothing unreported'
  engine(on, { band: line, level: 'quiet', appendix: line })

  const before = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await before.find({ type: 'Text' }))?.text).toBe('No turn has ended in this session yet.')
  await before.unmount()

  await $.turn.complete(TURN)

  const pane = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await pane.findAll({ type: 'Text' })).map(t => t.text)).toEqual([line])
  await pane.unmount()
})
