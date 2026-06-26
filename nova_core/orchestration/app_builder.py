"""Deterministic calculator app builder for investor demo."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from nova_core.agent_os.workspace import assert_workspace_write, calculator_project_path

CALCULATOR_FILES: dict[str, str] = {
    "package.json": json.dumps(
        {
            "name": "nova-calculator-app",
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
    + "\n",
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NOVA Calculator</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
    "tsconfig.json": json.dumps(
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
    + "\n",
    "tsconfig.node.json": json.dumps(
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
    + "\n",
    "vite.config.ts": """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
""",
    "src/main.tsx": """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
""",
    "src/App.tsx": """import { useEffect, useState } from 'react'
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
    <main className="calculator">
      <header>
        <p className="eyebrow">NOVA Calculator</p>
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
""",
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

body {
  margin: 0;
}

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
  min-height: 2.5rem;
}

.keypad {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

button {
  border: none;
  border-radius: 14px;
  padding: 1rem;
  font-size: 1.1rem;
  cursor: pointer;
  background: #1e293b;
  color: white;
}

button.op {
  background: #334155;
}

button.equals {
  background: linear-gradient(135deg, #2563eb, #7c3aed);
}
""",
    "README.md": """# NOVA Calculator App

Generated deterministically by NOVA Agent OS for the investor demo.

## Commands

```bash
npm install
npm run build
npm run dev
```
""",
}


@dataclass
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    success: bool


@dataclass
class BuildResult:
    project_path: str
    files_written: list[str]
    install: CommandResult | None
    build: CommandResult | None
    preview_url: str | None
    build_passed: bool


def write_calculator_files(project_path: Path | None = None) -> list[str]:
    root = assert_workspace_write(project_path or calculator_project_path())
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for rel, content in CALCULATOR_FILES.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def clean_calculator_workspace(project_path: Path | None = None) -> None:
    root = project_path or calculator_project_path()
    if root.exists():
        shutil.rmtree(root)


def run_workspace_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 300,
) -> CommandResult:
    assert_workspace_write(cwd)
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(
        command=" ".join(command),
        cwd=str(cwd),
        exit_code=proc.returncode,
        stdout=proc.stdout[-4000:],
        stderr=proc.stderr[-2000:],
        success=proc.returncode == 0,
    )


def build_calculator_app(
    *,
    run_npm: bool = True,
    project_path: Path | None = None,
) -> BuildResult:
    root = assert_workspace_write(project_path or calculator_project_path())
    files = write_calculator_files(root)
    install_result: CommandResult | None = None
    build_result: CommandResult | None = None
    preview_url = "http://127.0.0.1:5173"

    if run_npm:
        install_result = run_workspace_command(["npm", "install"], cwd=root)
        if install_result.success:
            build_result = run_workspace_command(["npm", "run", "build"], cwd=root)

    build_passed = bool(build_result and build_result.success)
    return BuildResult(
        project_path=str(root),
        files_written=files,
        install=install_result,
        build=build_result,
        preview_url=preview_url if build_passed else None,
        build_passed=build_passed,
    )


def expected_calculator_files(project_path: Path | None = None) -> list[Path]:
    root = project_path or calculator_project_path()
    return [root / rel for rel in CALCULATOR_FILES]
