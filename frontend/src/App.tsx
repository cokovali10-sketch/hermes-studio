import { useState, useEffect, useRef } from 'react'

// Types
type Message = { role: 'user' | 'assistant'; text: string; img?: string }

// API base
const API = 'http://127.0.0.1:8765'

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Привет! Я Hermes Studio. Задай вопрос, кинь скрин 📎 или скажи «сделай лендинг для кофейни» — соберу сайт.' }
  ])
  const [input, setInput] = useState('')
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [pendingB64, setPendingB64] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [abortCtrl, setAbortCtrl] = useState<AbortController | null>(null)
  const [voiceOn, setVoiceOn] = useState(localStorage.getItem('hermes-voice') !== 'off')
  const [events, setEvents] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Scroll to bottom
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  useEffect(() => { scrollToBottom() }, [messages, streaming])

  // Voice toggle
  useEffect(() => {
    localStorage.setItem('hermes-voice', voiceOn ? 'on' : 'off')
    if (!voiceOn) speechSynthesis.cancel()
  }, [voiceOn])

  // SSE Events
  useEffect(() => {
    const es = new EventSource(`${API}/api/events`)
    es.onmessage = (e) => {
      try {
        const m = JSON.parse(e.data)
        setEvents(prev => [...prev.slice(-49), `[${m.event}] ${JSON.stringify(m.payload).slice(0, 100)}`])
      } catch {}
    }
    return () => es.close()
  }, [])

  // File handling
  const onFile = async (f: File) => {
    setPendingFile(f)
    if (f.type.startsWith('image/')) {
      const b64 = await new Promise<string>(res => {
        const r = new FileReader()
        r.onload = () => res((r.result as string).split(',')[1])
        r.readAsDataURL(f)
      })
      setPendingB64(b64)
    } else {
      setPendingB64(null)
    }
  }

  // Send message
  const send = async () => {
    const prompt = input.trim()
    if (!prompt && !pendingFile) return

    const imgB64 = pendingB64
    const file = pendingFile
    setMessages(m => [...m, { role: 'user', text: prompt || '📎 файл', img: imgB64 ? `data:image/png;base64,${imgB64}` : undefined }])
    setInput('')
    setPendingFile(null)
    setPendingB64(null)

    // Upload file if present
    let imagePath: string | undefined
    if (file) {
      const fd = new FormData()
      fd.append('file', file)
      try {
        const r = await fetch(`${API}/api/upload`, { method: 'POST', body: fd })
        const j = await r.json()
        imagePath = j.path
      } catch {}
    }

    // Check if it's a site generation request
    const isSite = /сайт|лендинг|магазин|портфолио|сгенери|сделай.*приложение/i.test(prompt)
    if (isSite) {
      setMessages(m => [...m, { role: 'assistant', text: 'Принято — собираю сайт. Функция в разработке.' }])
      return
    }

    // Regular chat - streaming
    setStreaming(true)
    const controller = new AbortController()
    setAbortCtrl(controller)
    let full = ''
    setMessages(m => [...m, { role: 'assistant', text: '' }])

    try {
      const body: any = { prompt, history: messages.slice(-8).map(m => ({ role: m.role, content: m.text })), stream: true }
      if (imgB64) body.images = [imgB64]

      const r = await fetch(`${API}/api/chat?stream=1`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal
      })

      if (!r.ok || !r.body) throw new Error('Stream failed')

      const reader = r.body.getReader()
      const dec = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const p of parts) {
          if (!p.startsWith('data:')) continue
          try {
            const j = JSON.parse(p.slice(5))
            if (j.done) break
            if (j.text) {
              full += j.text
              setMessages(m => { const n = [...m]; n[n.length - 1].text = full; return n })
            }
          } catch {}
        }
      }

      if (voiceOn && full) {
        try {
          const u = new SpeechSynthesisUtterance(full.slice(0, 220))
          u.lang = 'ru-RU'
          speechSynthesis.speak(u)
        } catch {}
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
        setMessages(m => { const n = [...m]; n[n.length - 1].text += ' ⏹ Остановлено'; return n })
      } else {
        // Fallback non-stream
        try {
          const r = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, history: messages.slice(-8).map(m => ({ role: m.role, content: m.text })), images: imgB64 ? [imgB64] : undefined })
          })
          const j = await r.json()
          full = j.text || ''
          setMessages(m => { const n = [...m]; n[n.length - 1].text = full; return n })
        } catch {
          setMessages(m => { const n = [...m]; n[n.length - 1].text = 'Ошибка — попробуй еще раз'; return n })
        }
      }
    }

    setStreaming(false)
    setAbortCtrl(null)
  }

  const stop = () => {
    if (abortCtrl) abortCtrl.abort()
    setStreaming(false)
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white flex flex-col">
      {/* Header */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-black/30 border-b border-white/[0.06]">
        <div className="max-w-[1400px] mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-white text-black grid place-items-center font-bold text-xs">◆</div>
            <span className="font-mono text-xs tracking-[0.18em] text-white">HERMES STUDIO</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setVoiceOn(v => !v)} className={`px-3 py-1.5 rounded-full font-mono text-xs border ${voiceOn ? 'bg-white text-black border-white' : 'bg-zinc-900 text-zinc-400 border-zinc-700'}`}>
              {voiceOn ? '🔊 Вкл' : '🔇 Выкл'}
            </button>
          </div>
        </div>
      </header>

      {/* Main */}
      <div className="flex-1 flex max-w-[1400px] mx-auto w-full min-h-0 p-4 gap-4">
        {/* Chat */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 overflow-auto p-4 space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`${m.role === 'user' ? 'bg-white text-black' : 'bg-white/[0.07] border border-white/[0.08]'} max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-6 whitespace-pre-wrap`}>
                  {m.text}
                  {m.img && <img src={m.img} alt="attach" className="mt-2 rounded-xl max-h-64 border border-black/10" />}
                </div>
              </div>
            ))}
            {streaming && (
              <div className="flex justify-start">
                <div className="bg-white/[0.07] border border-white/[0.08] rounded-2xl px-4 py-3 text-sm animate-pulse">● Думаю...</div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-white/[0.06] bg-black/30 backdrop-blur">
            {pendingFile && (
              <div className="mb-2 flex items-center gap-2 p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-xs">
                <span className="truncate">{pendingFile.name} {(pendingFile.size / 1024).toFixed(0)}KB</span>
                {pendingB64 && <img src={`data:image/png;base64,${pendingB64}`} alt="preview" className="w-10 h-10 rounded-lg object-cover" />}
                <button onClick={() => { setPendingFile(null); setPendingB64(null) }} className="ml-auto text-zinc-400">✕</button>
              </div>
            )}
            <div className="flex items-end gap-2 bg-zinc-900 rounded-2xl border border-white/10 p-2">
              <label className="w-9 h-9 grid place-items-center rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 cursor-pointer shrink-0">
                📎<input type="file" accept="image/*,.txt,.md,.json" onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} className="hidden" />
              </label>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                rows={1}
                placeholder="Сообщение Hermes...  Enter — отправить · Shift+Enter — перенос"
                className="flex-1 bg-transparent outline-none resize-none py-2.5 text-sm placeholder:text-zinc-500 max-h-28"
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) onFile(f) }}
              />
              {streaming ? (
                <button onClick={stop} className="w-9 h-9 rounded-xl bg-red-500 text-white grid place-items-center font-bold shrink-0">■</button>
              ) : (
                <button onClick={send} className="w-9 h-9 rounded-xl bg-white text-black grid place-items-center font-bold hover:bg-zinc-200 shrink-0">↑</button>
              )}
            </div>
            <div className="flex items-center justify-between mt-2 px-1 text-[11px] mono text-zinc-500">
              <span>Hermes Super 3.8B · Vision qwen2.5-vl · <button onClick={() => setVoiceOn(v => !v)} className="underline">{voiceOn ? '🔊 Вкл' : '🔇 Выкл'}</button></span>
              <span>D: only · offline free</span>
            </div>
          </div>
        </div>

        {/* Events sidebar */}
        <div className="hidden lg:block w-72 border-l border-white/[0.06] bg-black/20 flex-col">
          <div className="p-3 border-b border-white/[0.06] font-mono text-xs tracking-widest text-zinc-400">LIVE EVENTS</div>
          <div className="flex-1 p-3 overflow-auto space-y-1 font-mono text-[10px] leading-tight">
            {events.slice().reverse().map((e, i) => (
              <div key={i} className="text-zinc-400 border-l-2 border-zinc-600 pl-2 py-0.5">{e}</div>
            ))}
            {events.length === 0 && <div className="text-zinc-600 text-center py-8">No events yet</div>}
          </div>
        </div>
      </div>
    </div>
  )
}