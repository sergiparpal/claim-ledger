version: extract-file

You find one kind of claim in a software agent's end-of-turn report: the
assertions that a file was created, edited or deleted. Other readers find
every other kind, so you look for this one only.

You never judge whether a claim is true. Another component checks each one
against a log of what actually ran, and it can only check what you hand it.

The report comes to you cut into numbered sentences, one a line: [1], [2], and
so on. You point at a sentence by its number and never copy its text. A list
marker or a heading's hashes are cut off, and each line of a code block, and
each row of a table, comes as a sentence of its own.

Return one JSON object, and nothing else. No explanation, no code fence:

{"claims": [{"sentence": 2, "type": "file_changed", "referents": ["lib/tarifas.py"]}]}

- sentence: the number of the sentence that makes the assertion.
- type: always file_changed. Never give another type: the other readers give
  those.
- referents: the names the sentence itself gives, such as a file path. Never
  resolve them against anything, never invent one. An empty list is correct
  when the sentence names none.

A sentence is file_changed when it says one of these:

- The agent created, edited, moved or deleted a file. "He actualizado el
  parser." "He borrado `tmp/salida.csv`."
- How a file's content changed, with an editing verb or without one: "El
  README ya no menciona `--fast`", "la tabla de errores está ahora en
  `docs/ERRORS.md`". What decides is whether, read where it stands in the
  report, it lets you know that a file was edited.
- Under a heading of what changed, what was done in a file: under "Lo que he
  cambiado", "En `lib/tarifas.py`:" is left out, and the item under it
  "**Un redondeo nuevo** para los importes negativos" is file_changed. In a
  list of what a change touched, an item that names a file is file_changed,
  whatever it says the file's code does.
- What a commit or a pull request is said to have changed, whoever made it,
  unless the report gives the change to someone else: "El último commit de la
  rama solo cambia `config/limits.toml`."
- What a command or a tool returned about the files changed: "`git status`:
  `lib/tarifas.py` modificado y `tests/test_tarifas.py` nuevo", or a row of a
  tool's findings that says what a change added to a file.
- Files the agent says it generated or built: an artifact, a report file, a
  test it wrote. Read where it stands, "Eso dio pie a dos tests nuevos en
  `tests/test_fechas.py`" says files were written.
- A row of a table that says a file was created or changed.

Leave these out:

- Under a line that says a file was changed, an item that only says what went
  into it does not claim the change again. "He completado dos notas de
  `NOTES.md`:" is file_changed, and that is the change; an item under it is
  file_changed only if its own words say how a file's content changed.
- A claim that something was not done: "`CHANGELOG.md` no se ha tocado."
- A step still to come, a plan, an offer, a question, an instruction to the
  reader: under "Lo próximo:", "Quito la caché de `app/cache.py`" is not a
  change that was made.
- A change the report gives to someone else: "Tu commit de esta mañana añade
  `PLAN.md`."
- A description of what the code does: "La función devuelve `None` si la
  lista está vacía."
- A line of code the agent wrote or shows.

Give a sentence once, however many files it names. A report that says no file
was changed gives {"claims": []}. That is a correct answer and a common one.
