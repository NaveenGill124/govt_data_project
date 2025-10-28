import React, { useState, useRef, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

// === Backend URL ===
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function ChatApp() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([
    { sender: 'bot', text: '🤖 **Welcome to Project Samarth!** — Ask me about crop production, rainfall, or agriculture data.' }
  ]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Scroll to bottom on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Send query to backend
  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: input }),
      });
      const data = await res.json();
      const botReply = data.output || "⚠️ Sorry, I couldn’t find an answer.";
      setMessages(prev => [...prev, { sender: 'bot', text: botReply }]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { sender: 'bot', text: '❌ Network error. Please try again later.' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const renderMarkdown = (text) => {
    const clean = DOMPurify.sanitize(marked.parse(text || ''));
    return { __html: clean };
  };

  // Sample questions
  const sampleQueries = [
    "Compare rainfall in Kerala and Haryana in 2014",
    "What were the top 3 crops produced in Punjab in 2012?",
    "What were the top 3 crops in Maharashtra in 2012? Also, show me the top 3 from Gujarat in the same year.",
    "Analyze the production trend of Sugarcane in Maharashtra from 2005 to 2012 and correlate this with the rainfall trend in the same period.",
    "Analyze the production trend of Wheat in Punjab from 2009 to 2013",
    "A policy advisor wants to promote Sugarcane (which is water-intensive) over Wheat in Haryana. Based on production and rainfall trends from 2007-2012, what data-backed arguments could you make for or against this?"
  ];

  const handleSampleClick = (q) => setInput(q);

  return (
    <div className="flex flex-col md:flex-row h-screen bg-green-50 text-gray-900 font-sans">

      {/* === LEFT PANEL: SAMPLE QUESTIONS === */}
      <aside className="hidden md:flex md:flex-col w-1/4 bg-green-700 text-white p-5 overflow-y-auto space-y-4">
        <h2 className="text-lg font-semibold mb-2">💡 Try Asking:</h2>
        {sampleQueries.map((q, i) => (
          <button
            key={i}
            onClick={() => handleSampleClick(q)}
            className="text-left bg-green-600 hover:bg-green-500 transition-all rounded-lg px-3 py-2 text-sm"
          >
            {q}
          </button>
        ))}
        <p className="mt-6 text-xs text-green-200">
          Tap a question to auto-fill it in the input box 👇
        </p>
      </aside>

      {/* === MAIN CHAT AREA === */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-green-700 text-white text-center py-3 shadow-lg text-xl font-semibold">
          🌾 Project Samarth — AI Agriculture Chatbot
        </header>

        {/* Chat messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex items-start ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.sender === 'bot' && (
                <div className="text-2xl mr-2">🤖</div>
              )}
              <div
                className={`max-w-[85%] sm:max-w-xl px-4 py-2 rounded-2xl shadow-md text-base leading-relaxed prose prose-sm ${
                  msg.sender === 'user'
                    ? 'bg-green-600 text-white rounded-br-none'
                    : 'bg-white text-gray-900 rounded-bl-none'
                }`}
                dangerouslySetInnerHTML={renderMarkdown(msg.text)}
              />
              {msg.sender === 'user' && (
                <div className="text-2xl ml-2">🧑‍🌾</div>
              )}
            </div>
          ))}
          {loading && (
            <div className="text-center text-gray-500 italic">Thinking...</div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="p-3 bg-white border-t border-gray-300 flex items-center gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Ask something like: ‘Top 3 crops in Kerala (2022)’..."
            className="flex-1 border border-gray-300 rounded-xl p-2 resize-none focus:outline-none focus:ring-2 focus:ring-green-500 text-base"
            rows="1"
          />
          <button
            onClick={sendMessage}
            disabled={loading}
            className="bg-green-600 hover:bg-green-700 text-white font-semibold px-5 py-2 rounded-xl disabled:opacity-50 transition-all"
          >
            {loading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<ChatApp />);
