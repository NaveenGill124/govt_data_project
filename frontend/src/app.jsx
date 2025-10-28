import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm'; // This plugin enables table rendering

const BotAvatar = () => (<div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center mr-3 flex-shrink-0"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-green-600"><path d="M12 8V4H8"/><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M12 18v-4h4"/></svg></div>);
const UserAvatar = () => (<div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center ml-3 flex-shrink-0"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-blue-600"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>);
const SendIcon = () => (<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white"><path d="m22 2-7 20-4-9-9-4Z"/><path d="m22 2-11 11"/></svg>);
const LoadingBubble = () => (<div className="flex justify-start mb-6"><BotAvatar /><div className="px-4 py-3 rounded-lg shadow-md bg-white"><div className="flex items-center space-x-2"><div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div><div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div><div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div></div></div></div>);

const Message = ({ sender, text }) => {
  const isUser = sender === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      {!isUser && <BotAvatar />}
      <div className={`max-w-xl lg:max-w-2xl px-4 py-3 rounded-lg shadow-md ${isUser ? 'bg-blue-600 text-white' : 'bg-white text-gray-800'}`}>
        <div className={isUser ? 'prose prose-dark' : 'prose'}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      </div>
      {isUser && <UserAvatar />}
    </div>
  );
};

const ExamplePrompt = ({ text, onClick }) => (<button onClick={onClick} className="w-full text-left bg-white/50 hover:bg-white p-3 rounded-lg transition-colors duration-200 text-sm text-green-900">{text}</button>);

export default function App() {
  const examplePrompts = ["Compare the rice production of Haryana with Kerala in 2012.", "What were the top 3 crops in Kerala in 2014?", "Show the top crop in Punjab and its rainfall in 2022."];
  const [messages, setMessages] = useState([{ sender: 'bot', text: "Welcome! Ask a question about Indian agriculture & climate. Try an example or type your own." }]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const handleSend = async (queryText) => {
    const textToSend = queryText || input;
    if (textToSend.trim() === '' || isLoading) return;
    setMessages((prev) => [...prev, { sender: 'user', text: textToSend }]);
    setInput('');
    setIsLoading(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ "query": textToSend }) });
      if (!response.ok) throw new Error(`API Error: ${response.status}`);
      const data = await response.json();
      setMessages((prev) => [...prev, { sender: 'bot', text: data.output || "Sorry, I couldn't find an answer." }]);
    } catch (error) {
      console.error("Fetch Error:", error);
      setMessages((prev) => [...prev, { sender: 'bot', text: `> **Error:** Connection to backend failed. Please ensure the server is running.\n\n> *Details: ${error.message}*` }]);
    } finally { setIsLoading(false); }
  };

  const handleKeyPress = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } };

  return (
      <div className="flex h-screen font-sans main-bg">
        <aside className="bg-green-500/20 p-6 flex-col flex w-full max-w-xs transition-all">
          <div className="flex items-center mb-8">
            <div className="w-12 h-12 rounded-full bg-green-600 flex items-center justify-center mr-4"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.2,15c.7-1.2,1-2.5,1-4,0-4.4-3.6-8-8-8s-8,3.6-8,8c0,1.5.3,2.8,1,4"/><path d="M4,15s1.5-2,4-2,4,2,4,2"/><path d="m12,15,2-2,2,2"/></svg></div>
            <div><h1 className="text-xl font-bold text-gray-800">Project Samarth</h1><p className="text-sm text-gray-600">Agri & Climate AI</p></div>
          </div>
          <div className="space-y-4"><h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider">Example Prompts</h2>{examplePrompts.map(p => (<ExamplePrompt key={p} text={p} onClick={() => handleSend(p)} />))}</div>
          <div className="mt-auto text-center text-xs text-gray-500"><p>&copy; {new Date().getFullYear()} Project Samarth</p><p>Data-driven insights for a greener future.</p></div>
        </aside>

        <div className="flex-1 flex flex-col">
          <main className="flex-1 overflow-y-auto p-6 lg:p-10"><div className="max-w-4xl mx-auto">
            {messages.map((msg, i) => <Message key={i} {...msg} />)}
            {isLoading && <LoadingBubble />}
            <div ref={messagesEndRef} />
          </div></main>

          <footer className="bg-white/80 backdrop-blur-md p-4 border-t border-gray-200">
            <div className="max-w-4xl mx-auto"><div className="flex items-center bg-white rounded-xl shadow-lg border border-gray-200 p-2">
              <textarea className="flex-1 bg-transparent text-gray-800 focus:outline-none resize-none px-3 py-2" placeholder="Ask a question or click an example..." value={input} onChange={(e) => setInput(e.target.value)} onKeyPress={handleKeyPress} rows={1} disabled={isLoading} />
              <button className={`ml-2 w-10 h-10 flex items-center justify-center rounded-full font-semibold text-white transition-all duration-200 ease-in-out ${isLoading ? 'bg-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'}`} onClick={() => handleSend()} disabled={isLoading}><SendIcon /></button>
            </div></div>
          </footer>
        </div>
      </div>
  );
}

