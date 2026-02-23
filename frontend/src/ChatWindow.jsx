/**
 * ChatWindow.jsx
 *
 * Renders:
 *   - Message history (user bubbles right, assistant bubbles left)
 *   - Loading indicator while agent is thinking
 *   - Fixed input area at the bottom (text input + submit button)
 *   - Six prompt template chips above the input
 *   - Reset button in the footer
 *
 * Props:
 *   messages  — { role: "user"|"assistant", content: string }[]
 *   loading   — bool, true while awaiting API response
 *   onSubmit  — (text: string) => void
 *   onReset   — () => void
 */

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './ChatWindow.css'

// Quick-start templates from PRD §4.2
const PROMPT_CHIPS = [
  'Find flights from Karachi to Dubai on March 15',
  'Show me economy flights from Lahore to London next Friday',
  'I want to travel from New York to Toronto, round trip, April 10 returning April 17',
  'Find flights from Islamabad to Jeddah on April 5 with Saudi Airlines',
  "What is Emirates' baggage policy for economy class?",
  'What happens if I cancel a PIA flight 48 hours before departure?',
]

export default function ChatWindow({ messages, loading, onSubmit, onReset }) {
  const [inputText, setInputText] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Auto-scroll to bottom whenever messages change or loading starts
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handleSend() {
    if (!inputText.trim() || loading) return
    onSubmit(inputText)
    setInputText('')
  }

  function handleKeyDown(e) {
    // Submit on Enter (not Shift+Enter)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleChipClick(chip) {
    if (loading) return
    onSubmit(chip)
    // Keep input clear after chip submit
    setInputText('')
    inputRef.current?.focus()
  }

  return (
    <div className="chat-window">
      {/* ── Message history ── */}
      <div className="messages-area">
        {messages.length === 0 && (
          <div className="empty-state">
            <p className="empty-title">Hi, I'm Kāishǐ</p>
            <p className="empty-subtitle">Your AI travel assistant. Ask me about flights or airline policies.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message-row ${msg.role}`}>
            <div className={`bubble ${msg.role}`}>
              {msg.role === 'assistant' ? (
                // Render markdown for assistant messages (tables, bold, etc.)
                <ReactMarkdown
                  components={{
                    // Open links in new tab for safety
                    a: ({ href, children }) => (
                      <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                    ),
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                <span>{msg.content}</span>
              )}
            </div>
          </div>
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="message-row assistant">
            <div className="bubble assistant loading-bubble">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </div>
        )}

        {/* Invisible anchor for auto-scroll */}
        <div ref={messagesEndRef} />
      </div>

      {/* ── Input area ── */}
      <div className="input-area">
        {/* Prompt template chips */}
        <div className="chips-row" role="list" aria-label="Quick-start prompts">
          {PROMPT_CHIPS.map((chip, i) => (
            <button
              key={i}
              className="chip"
              onClick={() => handleChipClick(chip)}
              disabled={loading}
              role="listitem"
            >
              {chip}
            </button>
          ))}
        </div>

        {/* Text input + buttons */}
        <div className="input-row">
          <input
            ref={inputRef}
            type="text"
            className="text-input"
            placeholder="Ask about flights or airline policies…"
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-label="Message input"
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={loading || !inputText.trim()}
            aria-label="Send message"
          >
            Send
          </button>
          <button
            className="reset-btn"
            onClick={onReset}
            disabled={loading}
            aria-label="Reset conversation"
            title="Clear chat history"
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}
