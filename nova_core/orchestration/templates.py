"""Deterministic Vite + React + TypeScript app templates."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from nova_core.orchestration.app_spec import AppSpec

FileMap = dict[str, str]
TemplateBuilder = Callable[[AppSpec], FileMap]


@dataclass(frozen=True)
class AppTemplate:
    template_id: str
    supported_app_types: tuple[str, ...]
    build_files: TemplateBuilder
    validation_commands: tuple[str, ...] = ("npm install", "npm run build")
    preview_command: str = "npm run dev"


def _pkg_name(spec: AppSpec) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", spec.app_name.lower()).strip("-")
    return slug or "nova-app"


def _base_package_json(spec: AppSpec) -> str:
    return (
        json.dumps(
            {
                "name": _pkg_name(spec),
                "private": True,
                "version": "1.0.0",
                "type": "module",
                "scripts": {
                    "dev": "vite --host 127.0.0.1 --port 5173",
                    "build": "vite build",
                    "preview": "vite preview --host 127.0.0.1 --port 4173",
                },
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
                "devDependencies": {
                    "@types/react": "^18.3.12",
                    "@types/react-dom": "^18.3.1",
                    "@vitejs/plugin-react": "^4.3.4",
                    "typescript": "^5.6.3",
                    "vite": "^5.4.11",
                },
            },
            indent=2,
        )
        + "\n"
    )


def _base_tsconfig() -> str:
    return (
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2020",
                    "useDefineForClassFields": True,
                    "lib": ["ES2020", "DOM", "DOM.Iterable"],
                    "module": "ESNext",
                    "skipLibCheck": True,
                    "moduleResolution": "bundler",
                    "allowImportingTsExtensions": True,
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "noEmit": True,
                    "jsx": "react-jsx",
                    "strict": True,
                },
                "include": ["src"],
            },
            indent=2,
        )
        + "\n"
    )


def _base_tsconfig_node() -> str:
    return (
        json.dumps(
            {
                "compilerOptions": {
                    "composite": True,
                    "skipLibCheck": True,
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "allowSyntheticDefaultImports": True,
                },
                "include": ["vite.config.ts"],
            },
            indent=2,
        )
        + "\n"
    )


def _vite_config() -> str:
    return """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
"""


def _main_tsx() -> str:
    return """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
"""


def _index_html(title: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""


def _readme(spec: AppSpec) -> str:
    return f"""# {spec.title}

Generated deterministically by NOVA Agent OS.

## Commands

```bash
npm install
npm run build
npm run dev
```
"""


def _scaffold(spec: AppSpec, extra: FileMap) -> FileMap:
    files = {
        "package.json": _base_package_json(spec),
        "index.html": _index_html(spec.title),
        "tsconfig.json": _base_tsconfig(),
        "tsconfig.node.json": _base_tsconfig_node(),
        "vite.config.ts": _vite_config(),
        "src/main.tsx": _main_tsx(),
        "README.md": _readme(spec),
    }
    files.update(extra)
    return files


def _calculator_files(spec: AppSpec) -> FileMap:
    title = spec.title
    app_tsx = """import { useEffect, useState } from 'react'
import { appendDigit, applyOperator, clearAll, deleteLast, evaluate } from './calculator'

const BUTTONS = [
  ['C', 'DEL', '/', '*'],
  ['7', '8', '9', '-'],
  ['4', '5', '6', '+'],
  ['1', '2', '3', '='],
  ['0', '.', '='],
]

export default function App() {
  const [display, setDisplay] = useState('0')
  const [pendingOp, setPendingOp] = useState<string | null>(null)
  const [stored, setStored] = useState<number | null>(null)
  const [fresh, setFresh] = useState(true)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const key = event.key
      if (/\\d/.test(key)) handleDigit(key)
      else if (key === '.') handleDigit('.')
      else if (['+', '-', '*', '/'].includes(key)) handleOperator(key)
      else if (key === 'Enter' || key === '=') handleEquals()
      else if (key === 'Escape') handleClear()
      else if (key === 'Backspace') handleDelete()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const currentValue = () => Number(display)

  const handleDigit = (digit: string) => {
    setDisplay((prev) => appendDigit(prev, digit, fresh))
    setFresh(false)
  }

  const handleOperator = (op: string) => {
    const value = currentValue()
    if (stored !== null && pendingOp && !fresh) {
      const result = applyOperator(stored, value, pendingOp)
      setStored(result)
      setDisplay(String(result))
    } else {
      setStored(value)
    }
    setPendingOp(op)
    setFresh(true)
  }

  const handleEquals = () => {
    if (pendingOp === null || stored === null) return
    const result = evaluate(stored, currentValue(), pendingOp)
    setDisplay(String(result))
    setStored(null)
    setPendingOp(null)
    setFresh(true)
  }

  const handleClear = () => {
    setDisplay(clearAll())
    setStored(null)
    setPendingOp(null)
    setFresh(true)
  }

  const handleDelete = () => {
    setDisplay(deleteLast(display))
    setFresh(false)
  }

  const onButton = (label: string) => {
    if (label === 'C') handleClear()
    else if (label === 'DEL') handleDelete()
    else if (label === '=') handleEquals()
    else if (['+', '-', '*', '/'].includes(label)) handleOperator(label)
    else handleDigit(label)
  }

  return (
    <main className="app calculator">
      <header>
        <p className="eyebrow">NOVA_CALCULATOR_TITLE</p>
        <div className="display" aria-live="polite">{display}</div>
      </header>
      <section className="keypad">
        {BUTTONS.flat().map((label, index) => (
          <button
            key={`${label}-${index}`}
            type="button"
            className={label === '=' ? 'equals' : label.match(/[+\\-*/]|C|DEL/) ? 'op' : 'digit'}
            onClick={() => onButton(label)}
          >
            {label}
          </button>
        ))}
      </section>
    </main>
  )
}
""".replace("NOVA_CALCULATOR_TITLE", title)
    return _scaffold(
        spec,
        {
            "src/App.tsx": app_tsx,
            "src/calculator.ts": """export function appendDigit(current: string, digit: string, fresh: boolean): string {
  if (digit === '.' && current.includes('.')) return current
  if (fresh || current === '0') return digit === '.' ? '0.' : digit
  return current + digit
}

export function clearAll(): string {
  return '0'
}

export function deleteLast(current: string): string {
  if (current.length <= 1) return '0'
  return current.slice(0, -1)
}

export function applyOperator(a: number, b: number, op: string): number {
  return evaluate(a, b, op)
}

export function evaluate(a: number, b: number, op: string): number {
  switch (op) {
    case '+':
      return a + b
    case '-':
      return a - b
    case '*':
      return a * b
    case '/':
      if (b === 0) return NaN
      return a / b
    default:
      return b
  }
}
""",
            "src/App.css": """:root {
  color-scheme: dark;
  font-family: 'SF Pro Text', system-ui, sans-serif;
  background: radial-gradient(circle at top, #1f2a44, #0b1020 55%);
  min-height: 100vh;
}
body { margin: 0; }
.calculator {
  max-width: 360px;
  margin: 4rem auto;
  padding: 1.5rem;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.9);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
}
.eyebrow {
  margin: 0 0 0.5rem;
  color: #93c5fd;
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.display {
  font-size: 2.5rem;
  text-align: right;
  padding: 1rem;
  border-radius: 16px;
  background: #020617;
  margin-bottom: 1rem;
}
.keypad { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }
button {
  border: none;
  border-radius: 14px;
  padding: 1rem;
  font-size: 1.1rem;
  cursor: pointer;
  background: #1e293b;
  color: white;
}
button.op { background: #334155; }
button.equals { background: linear-gradient(135deg, #2563eb, #7c3aed); }
""",
        },
    )


def _todo_files(spec: AppSpec) -> FileMap:
    return _scaffold(
        spec,
        {
            "src/App.tsx": """import { useEffect, useMemo, useState } from 'react'

type Todo = { id: string; text: string; done: boolean }
type Filter = 'all' | 'active' | 'completed'
const STORAGE_KEY = 'nova-todo-items'

export default function App() {
  const [items, setItems] = useState<Todo[]>([])
  const [text, setText] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) setItems(JSON.parse(raw))
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  }, [items])

  const visible = useMemo(() => {
    if (filter === 'active') return items.filter((i) => !i.done)
    if (filter === 'completed') return items.filter((i) => i.done)
    return items
  }, [items, filter])

  const add = () => {
    const value = text.trim()
    if (!value) return
    setItems((prev) => [...prev, { id: crypto.randomUUID(), text: value, done: false }])
    setText('')
  }

  return (
    <main className="app todo">
      <h1>NOVA Todo</h1>
      <div className="composer">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="New task" />
        <button type="button" onClick={add}>Add</button>
      </div>
      <div className="filters">
        {(['all', 'active', 'completed'] as Filter[]).map((f) => (
          <button key={f} type="button" className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>
      <ul>
        {visible.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={item.done}
                onChange={() =>
                  setItems((prev) =>
                    prev.map((t) => (t.id === item.id ? { ...t, done: !t.done } : t)),
                  )
                }
              />
              <span className={item.done ? 'done' : ''}>{item.text}</span>
            </label>
            <button type="button" onClick={() => setItems((prev) => prev.filter((t) => t.id !== item.id))}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </main>
  )
}
""",
            "src/App.css": """:root { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
body { margin: 0; }
.todo { max-width: 560px; margin: 3rem auto; padding: 1.5rem; }
.composer { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
input { flex: 1; padding: 0.75rem; border-radius: 8px; border: 1px solid #334155; background: #020617; color: inherit; }
button { border: none; border-radius: 8px; padding: 0.6rem 1rem; cursor: pointer; background: #2563eb; color: white; }
.filters button { background: #1e293b; margin-right: 0.5rem; }
.filters button.active { background: #7c3aed; }
ul { list-style: none; padding: 0; }
li { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid #1e293b; }
.done { text-decoration: line-through; opacity: 0.6; }
""",
        },
    )


def _habit_files(spec: AppSpec) -> FileMap:
    return _scaffold(
        spec,
        {
            "src/App.tsx": """import { useEffect, useState } from 'react'

type Habit = { id: string; name: string; completed: string[] }
const STORAGE_KEY = 'nova-habits'
const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function todayKey() {
  return new Date().toISOString().slice(0, 10)
}

function streak(completed: string[]) {
  const set = new Set(completed)
  let count = 0
  const cursor = new Date()
  while (set.has(cursor.toISOString().slice(0, 10))) {
    count += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return count
}

export default function App() {
  const [habits, setHabits] = useState<Habit[]>([])
  const [name, setName] = useState('')

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) setHabits(JSON.parse(raw))
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(habits))
  }, [habits])

  const add = () => {
    const value = name.trim()
    if (!value) return
    setHabits((prev) => [...prev, { id: crypto.randomUUID(), name: value, completed: [] }])
    setName('')
  }

  const toggleToday = (id: string) => {
    const key = todayKey()
    setHabits((prev) =>
      prev.map((h) => {
        if (h.id !== id) return h
        const done = h.completed.includes(key)
        return {
          ...h,
          completed: done ? h.completed.filter((d) => d !== key) : [...h.completed, key],
        }
      }),
    )
  }

  return (
    <main className="app habit">
      <h1>NOVA Habit Tracker</h1>
      <div className="composer">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New habit" />
        <button type="button" onClick={add}>Add habit</button>
      </div>
      <div className="grid">
        {habits.map((habit) => (
          <article key={habit.id} className="card">
            <header>
              <h2>{habit.name}</h2>
              <span className="streak">{streak(habit.completed)} day streak</span>
            </header>
            <button type="button" onClick={() => toggleToday(habit.id)}>
              {habit.completed.includes(todayKey()) ? 'Completed today' : 'Mark today'}
            </button>
            <div className="week">
              {days.map((day) => (
                <span key={day}>{day}</span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </main>
  )
}
""",
            "src/App.css": """:root { font-family: system-ui, sans-serif; background: #111827; color: #f9fafb; min-height: 100vh; }
body { margin: 0; }
.habit { max-width: 900px; margin: 2rem auto; padding: 1.5rem; }
.composer { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
input { flex: 1; padding: 0.75rem; border-radius: 8px; border: 1px solid #374151; background: #030712; color: inherit; }
button { border: none; border-radius: 8px; padding: 0.6rem 1rem; cursor: pointer; background: #059669; color: white; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
.card { background: #1f2937; border-radius: 16px; padding: 1rem; }
.streak { color: #34d399; font-size: 0.9rem; }
.week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 0.25rem; margin-top: 0.75rem; font-size: 0.75rem; opacity: 0.8; }
""",
        },
    )


def _expense_files(spec: AppSpec) -> FileMap:
    return _scaffold(
        spec,
        {
            "src/App.tsx": """import { useEffect, useMemo, useState } from 'react'

type Tx = { id: string; label: string; amount: number; category: string; kind: 'income' | 'expense' }
const STORAGE_KEY = 'nova-expenses'

export default function App() {
  const [items, setItems] = useState<Tx[]>([])
  const [label, setLabel] = useState('')
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('General')
  const [kind, setKind] = useState<'income' | 'expense'>('expense')

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) setItems(JSON.parse(raw))
  }, [])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
  }, [items])

  const balance = useMemo(
    () =>
      items.reduce(
        (sum, tx) => sum + (tx.kind === 'income' ? tx.amount : -tx.amount),
        0,
      ),
    [items],
  )

  const add = () => {
    const value = Number(amount)
    if (!label.trim() || Number.isNaN(value)) return
    setItems((prev) => [
      ...prev,
      { id: crypto.randomUUID(), label: label.trim(), amount: value, category, kind },
    ])
    setLabel('')
    setAmount('')
  }

  return (
    <main className="app expense">
      <h1>NOVA Expense Tracker</h1>
      <div className="balance">Balance: ${balance.toFixed(2)}</div>
      <div className="composer">
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Description" />
        <input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" type="number" />
        <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" />
        <select value={kind} onChange={(e) => setKind(e.target.value as 'income' | 'expense')}>
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </select>
        <button type="button" onClick={add}>Add</button>
      </div>
      <ul>
        {items.map((tx) => (
          <li key={tx.id}>
            <span>{tx.label}</span>
            <span>{tx.category}</span>
            <strong className={tx.kind}>{tx.kind === 'income' ? '+' : '-'}${tx.amount.toFixed(2)}</strong>
          </li>
        ))}
      </ul>
    </main>
  )
}
""",
            "src/App.css": """:root { font-family: system-ui, sans-serif; background: #0b1220; color: #e5e7eb; min-height: 100vh; }
body { margin: 0; }
.expense { max-width: 720px; margin: 2rem auto; padding: 1.5rem; }
.balance { font-size: 1.5rem; margin-bottom: 1rem; }
.composer { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-bottom: 1rem; }
input, select { padding: 0.65rem; border-radius: 8px; border: 1px solid #334155; background: #020617; color: inherit; }
button { grid-column: span 3; border: none; border-radius: 8px; padding: 0.7rem; background: #2563eb; color: white; cursor: pointer; }
ul { list-style: none; padding: 0; }
li { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 0.5rem; padding: 0.6rem 0; border-bottom: 1px solid #1f2937; }
.income { color: #34d399; }
.expense { color: #f87171; }
""",
        },
    )


def _landing_files(spec: AppSpec) -> FileMap:
    title = spec.title.replace(" Landing Page", "")
    return _scaffold(
        spec,
        {
            "src/App.tsx": f"""export default function App() {{
  return (
    <main className="app landing">
      <section className="hero">
        <p className="eyebrow">Built with NOVA Agent OS</p>
        <h1>{title}</h1>
        <p className="lede">A polished landing page scaffold for your startup demo.</p>
        <button type="button">Get started</button>
      </section>
      <section className="features">
        <h2>Features</h2>
        <div className="cards">
          <article><h3>Fast setup</h3><p>Ship a credible demo in minutes.</p></article>
          <article><h3>Responsive</h3><p>Looks great on desktop and mobile.</p></article>
          <article><h3>Investor-ready</h3><p>Clean structure and modern styling.</p></article>
        </div>
      </section>
      <section className="how">
        <h2>How it works</h2>
        <ol>
          <li>Describe your app idea to NOVA.</li>
          <li>Agent OS generates and validates the project.</li>
          <li>Preview locally, deploy when you approve.</li>
        </ol>
      </section>
      <section className="cta">
        <h2>Ready to launch {title}?</h2>
        <button type="button">Book a demo</button>
      </section>
    </main>
  )
}}
""",
            "src/App.css": """:root { font-family: 'SF Pro Text', system-ui, sans-serif; color: #0f172a; }
body { margin: 0; background: #f8fafc; }
.landing { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
.hero { text-align: center; padding: 4rem 1rem; background: linear-gradient(135deg, #dbeafe, #ede9fe); border-radius: 24px; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; color: #4f46e5; }
.lede { font-size: 1.15rem; max-width: 540px; margin: 0 auto 1.5rem; }
.features .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
article { background: white; border-radius: 16px; padding: 1rem; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08); }
.how, .cta { margin-top: 3rem; text-align: center; }
button { border: none; border-radius: 999px; padding: 0.85rem 1.5rem; background: #2563eb; color: white; font-size: 1rem; cursor: pointer; }
""",
        },
    )


def _generic_files(spec: AppSpec) -> FileMap:
    idea = spec.app_name
    return _scaffold(
        spec,
        {
            "src/App.tsx": f"""export default function App() {{
  return (
    <main className="app generic">
      <section className="panel">
        <p className="eyebrow">NOVA Web App Scaffold</p>
        <h1>{idea}</h1>
        <p>
          This is a deterministic starter generated for your idea. Extend components,
          routes, and data here while Agent OS handles build and preview validation.
        </p>
        <ul>
          <li>Vite + React + TypeScript</li>
          <li>Responsive shell</li>
          <li>Workspace-scoped writes</li>
        </ul>
      </section>
    </main>
  )
}}
""",
            "src/App.css": """:root { font-family: system-ui, sans-serif; background: #111827; color: #f3f4f6; min-height: 100vh; }
body { margin: 0; }
.generic { display: grid; place-items: center; min-height: 100vh; padding: 2rem; }
.panel { max-width: 640px; background: #1f2937; border-radius: 20px; padding: 2rem; }
.eyebrow { color: #93c5fd; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.8rem; }
""",
        },
    )


def _cli_calculator_files(spec: AppSpec) -> FileMap:
    title = spec.title
    return {
        "calculator.py": f'''#!/usr/bin/env python3
"""{title} — command-line calculator generated by NOVA Agent OS."""

from __future__ import annotations

import sys


def evaluate(left: float, op: str, right: float) -> float:
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            raise ZeroDivisionError("division by zero")
        return left / right
    raise ValueError(f"unsupported operator: {{op}}")


def repl() -> None:
    print("{title} — enter expressions like 2 + 2, or q to quit")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        if line.lower() in {{"q", "quit", "exit"}}:
            break
        for op in ("+", "-", "*", "/"):
            if op in line:
                left_text, right_text = line.split(op, 1)
                result = evaluate(float(left_text.strip()), op, float(right_text.strip()))
                print(result)
                break
        else:
            print("Use format: <number> <op> <number>")


def smoke_test() -> None:
    assert evaluate(2, "+", 2) == 4
    assert evaluate(9, "/", 3) == 3
    try:
        evaluate(1, "/", 0)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("expected divide by zero")


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke_test()
        print("smoke: PASS")
    else:
        repl()
''',
        "README.md": f"""# {title}

Command-line calculator generated by NOVA Agent OS.

## Run

```bash
python3 calculator.py
```

## Smoke test

```bash
python3 calculator.py --smoke
```
""",
    }


TEMPLATES: dict[str, AppTemplate] = {
    "calculator_react_vite": AppTemplate(
        template_id="calculator_react_vite",
        supported_app_types=("calculator",),
        build_files=_calculator_files,
    ),
    "todo_react_vite": AppTemplate(
        template_id="todo_react_vite",
        supported_app_types=("todo",),
        build_files=_todo_files,
    ),
    "habit_tracker_react_vite": AppTemplate(
        template_id="habit_tracker_react_vite",
        supported_app_types=("habit_tracker",),
        build_files=_habit_files,
    ),
    "expense_tracker_react_vite": AppTemplate(
        template_id="expense_tracker_react_vite",
        supported_app_types=("expense_tracker",),
        build_files=_expense_files,
    ),
    "landing_page_react_vite": AppTemplate(
        template_id="landing_page_react_vite",
        supported_app_types=("landing_page",),
        build_files=_landing_files,
    ),
    "generic_react_vite": AppTemplate(
        template_id="generic_react_vite",
        supported_app_types=("generic",),
        build_files=_generic_files,
    ),
    "cli_calculator_python": AppTemplate(
        template_id="cli_calculator_python",
        supported_app_types=("cli_calculator",),
        build_files=_cli_calculator_files,
        validation_commands=(
            "python3 -m py_compile calculator.py",
            "python3 calculator.py --smoke",
        ),
        preview_command="",
    ),
}


def get_template(template_id: str) -> AppTemplate:
    template = TEMPLATES.get(template_id)
    if template is None:
        return TEMPLATES["generic_react_vite"]
    return template


def template_for_spec(spec: AppSpec) -> AppTemplate:
    return get_template(spec.template_id)
