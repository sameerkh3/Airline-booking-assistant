/**
 * App.jsx — root component
 *
 * Owns all top-level state:
 *   messages       — display history shown in the chat window
 *   reasoning      — trace list from the last agent turn (for the panel)
 *   showReasoning  — controls visibility of the reasoning side panel
 *   loading        — true while an API request is in flight
 *
 * Renders:
 *   <NavBar>        — app name + reasoning toggle button
 *   <ChatWindow>    — message history, input box, prompt chips
 *   <ReasoningPanel> — slide-in panel (conditionally rendered)
 */

import { useState } from 'react'
import ChatWindow from './ChatWindow.jsx'
import ReasoningPanel from './ReasoningPanel.jsx'
import './App.css'

export default function App() {
  // Display messages: { role: "user" | "assistant", content: string }[]
  const [messages, setMessages] = useState([])
  // Reasoning trace from the last agent turn
  const [reasoning, setReasoning] = useState([])
  const [showReasoning, setShowReasoning] = useState(false)
  const [loading, setLoading] = useState(false)

  /**
   * Send a user message to the backend and append the assistant reply.
   * The server maintains its own conversation history; we only track
   * the display-level messages locally for rendering.
   */
  async function handleSubmit(text) {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    // Optimistically append the user message
    setMessages(prev => [...prev, { role: 'user', content: trimmed }])
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed }),
      })

      if (!res.ok) {
        throw new Error(`Server error: ${res.status}`)
      }

      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])
      setReasoning(data.reasoning ?? [])
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `⚠️ Error: ${err.message}. Please try again.` },
      ])
    } finally {
      setLoading(false)
    }
  }

  /** Clear chat display and tell the server to reset its history. */
  async function handleReset() {
    try {
      await fetch('/api/reset', { method: 'POST' })
    } catch {
      // Non-fatal — local state is cleared regardless
    }
    setMessages([])
    setReasoning([])
  }

  return (
    <div className="app-layout">
      {/* ── Top navigation bar ── */}
      <nav className="nav-bar">
        <span className="nav-title">Kāishǐ</span>
        <button
          className={`nav-reasoning-btn ${showReasoning ? 'active' : ''}`}
          onClick={() => setShowReasoning(v => !v)}
          title="Toggle agent reasoning panel"
        >
          {showReasoning ? 'Hide Reasoning' : 'Show Reasoning'}
        </button>
      </nav>

      {/* ── Main content area ── */}
      <div className="content-area">
        <ChatWindow
          messages={messages}
          loading={loading}
          onSubmit={handleSubmit}
          onReset={handleReset}
        />

        {/* Reasoning panel slides in from the right */}
        <ReasoningPanel
          reasoning={reasoning}
          visible={showReasoning}
          onClose={() => setShowReasoning(false)}
        />
      </div>
    </div>
  )
}
