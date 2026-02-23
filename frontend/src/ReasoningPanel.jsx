/**
 * ReasoningPanel.jsx
 *
 * Fixed-position slide-in panel on the right side of the viewport.
 * Shown only when `visible` is true. Displays the agent's reasoning
 * trace from the last turn — never visible in the main chat window.
 *
 * Each entry in `reasoning` has a prefix tag that determines its style:
 *   [assistant]   — blue   — model's text thinking
 *   [tool_call]   — orange — tool invocation with inputs
 *   [tool_result] — green  — tool output
 *   [error]       — red    — unexpected errors
 *
 * Props:
 *   reasoning  — string[]   (trace entries from the last agent turn)
 *   visible    — bool
 *   onClose    — () => void
 */

import './ReasoningPanel.css'

// Tag definitions: prefix → CSS class + display label
const TAG_MAP = [
  { prefix: '[assistant]',   cls: 'tag-assistant',   label: 'assistant'    },
  { prefix: '[tool_call]',   cls: 'tag-tool-call',   label: 'tool call'    },
  { prefix: '[tool_result]', cls: 'tag-tool-result', label: 'tool result'  },
  { prefix: '[error]',       cls: 'tag-error',        label: 'error'        },
]

function parseEntry(entry) {
  for (const { prefix, cls, label } of TAG_MAP) {
    if (entry.startsWith(prefix)) {
      return {
        tag: label,
        cls,
        text: entry.slice(prefix.length).trim(),
        mono: prefix !== '[assistant]', // monospace for tool calls/results
      }
    }
  }
  // Fallback: no recognised prefix
  return { tag: null, cls: '', text: entry, mono: false }
}

export default function ReasoningPanel({ reasoning, visible, onClose }) {
  return (
    <aside className={`reasoning-panel ${visible ? 'open' : ''}`} aria-label="Agent reasoning panel">
      <div className="panel-header">
        <span className="panel-title">Agent Reasoning</span>
        <button className="panel-close-btn" onClick={onClose} aria-label="Close reasoning panel">✕</button>
      </div>

      <div className="panel-body">
        {reasoning.length === 0 ? (
          <p className="panel-empty">No reasoning data yet. Send a message to see the agent's thinking.</p>
        ) : (
          <ol className="trace-list">
            {reasoning.map((entry, i) => {
              const { tag, cls, text, mono } = parseEntry(entry)
              return (
                <li key={i} className="trace-entry">
                  {tag && <span className={`trace-tag ${cls}`}>{tag}</span>}
                  <span className={`trace-text ${mono ? 'mono' : ''}`}>{text}</span>
                </li>
              )
            })}
          </ol>
        )}
      </div>
    </aside>
  )
}
