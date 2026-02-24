/**
 * ChatWindow.jsx
 *
 * Renders:
 *   Empty state  — large greeting + 2×2 prompt cards (only when no messages)
 *   Chat state   — message history (user right, assistant left)
 *   Input area   — floating pill-shaped input bar, always visible at bottom
 *
 * Props:
 *   messages  — { role: "user"|"assistant", content: string }[]
 *   loading   — bool, true while awaiting API response
 *   onSubmit  — (text: string) => void
 */

import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import './ChatWindow.css'

// 4 prompt cards shown in the empty state (2×2 grid)
const PROMPT_CARDS = [
  {
    title: 'Search flights',
    preview: 'Find flights from Karachi to Dubai on March 15',
    prompt: 'Find flights from Karachi to Dubai on March 15',
  },
  {
    title: 'Economy deals',
    preview: 'Show me economy flights from Lahore to London next Friday',
    prompt: 'Show me economy flights from Lahore to London next Friday',
  },
  {
    title: 'Baggage policy',
    preview: "What is Emirates' baggage policy for economy class?",
    prompt: "What is Emirates' baggage policy for economy class?",
  },
  {
    title: 'Cancellation rules',
    preview: 'What happens if I cancel a PIA flight 48 hours before departure?',
    prompt: 'What happens if I cancel a PIA flight 48 hours before departure?',
  },
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

  function handleCardClick(prompt) {
    if (loading) return
    onSubmit(prompt)
    inputRef.current?.focus()
  }

  const isEmpty = messages.length === 0

  return (
    <div className="chat-window">

      {/* ── Message / empty state area ── */}
      <div className="messages-area">

        {/* Empty state: greeting + prompt cards */}
        {isEmpty && (
          <div className="empty-state">
            <p className="greeting-title">Hello, Sameer</p>
            <p className="greeting-subtitle">How can I help you today?</p>

            <div className="cards-grid" role="list" aria-label="Quick-start prompts">
              {PROMPT_CARDS.map((card, i) => (
                <button
                  key={i}
                  className="prompt-card"
                  onClick={() => handleCardClick(card.prompt)}
                  disabled={loading}
                  role="listitem"
                >
                  <p className="card-title">{card.title}</p>
                  <p className="card-preview">{card.preview}</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Message history (chat mode) */}
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

      {/* ── Floating pill input bar ── */}
      <div className="input-area">
        <div className="input-pill">
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
            title="Send"
          >
            ↑
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
