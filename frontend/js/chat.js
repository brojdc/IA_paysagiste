'use strict';
/* =============================================
   chat.js — Bulle de chat + SSE streaming
   Agent : assistant aménagement paysager
   ============================================= */

let chatOpen    = false;
let chatHistory = [];
let _isStreaming = false;

/* -----------------------------------------------
   Toggle panel
   ----------------------------------------------- */
function toggleChat() {
  chatOpen = !chatOpen;
  const panel    = document.getElementById('chat-panel');
  const bubble   = document.getElementById('chat-toggle');
  const iconOpen  = document.getElementById('chat-icon-open');
  const iconClose = document.getElementById('chat-icon-close');

  panel.classList.toggle('hidden', !chatOpen);
  bubble.classList.toggle('active', chatOpen);
  if (iconOpen)  iconOpen.style.display  = chatOpen ? 'none' : '';
  if (iconClose) iconClose.style.display = chatOpen ? ''     : 'none';

  if (chatOpen) {
    _updateWelcomeMessage();
    document.getElementById('chat-input')?.focus();
  }
}

/* Update the contextual welcome message based on terrain state */
function _updateWelcomeMessage() {
  const welcome = document.getElementById('chat-welcome');
  if (!welcome || chatHistory.length > 0) return;  // don't overwrite once chat started

  const payload = window.terrainPayload;
  const hasConfig = payload?.parcelle?.largeur && payload.parcelle.largeur > 0;

  if (hasConfig) {
    const w = payload.parcelle.largeur;
    const h = payload.parcelle.hauteur;
    const surfJ = Math.max(0, w * h - (payload.maisons?.[0]?.largeur ?? 0) * (payload.maisons?.[0]?.hauteur ?? 0)).toFixed(0);
    welcome.innerHTML = `
      <p>Bonjour ! Je suis votre assistant en aménagement paysager.</p>
      <p>J'ai accès à votre terrain : <strong>${w} × ${h} m</strong> (environ <strong>${surfJ} m²</strong> de jardin). Posez-moi vos questions sur l'exposition solaire, les plantes adaptées ou l'aménagement de votre espace.</p>
    `;
  } else {
    welcome.innerHTML = `
      <p>Bonjour ! Je suis votre assistant en aménagement paysager.</p>
      <p>Configurez votre terrain dans l'éditeur pour que je puisse vous donner des recommandations précises sur l'exposition solaire, les plantes adaptées et l'aménagement de votre espace.</p>
    `;
  }
}

/* -----------------------------------------------
   DOM helpers
   ----------------------------------------------- */
function scrollToBottom() {
  const el = document.getElementById('chat-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

function appendMessage(role, html) {
  const el  = document.getElementById('chat-messages');
  if (!el) return null;
  const div = document.createElement('div');
  div.className = `chat-message chat-message-${role}`;
  div.innerHTML = html;
  el.appendChild(div);
  scrollToBottom();
  return div;
}

function appendTypingIndicator() {
  const el = document.getElementById('chat-messages');
  if (!el) return;
  const div = document.createElement('div');
  div.id        = 'typing-indicator';
  div.className = 'chat-message chat-message-assistant typing-indicator';
  div.innerHTML = '<span></span><span></span><span></span>';
  el.appendChild(div);
  scrollToBottom();
}

function removeTypingIndicator() {
  document.getElementById('typing-indicator')?.remove();
}

function safeMarkdown(text) {
  if (typeof marked !== 'undefined') {
    try { return marked.parse(text); } catch (_) {}
  }
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
             .replace(/\n/g, '<br>');
}

/* Build enriched terrain context including synthesis values */
function _buildTerrainContext() {
  const payload = window.terrainPayload;
  if (!payload) return null;

  // Attach synthesis text from DOM for additional context
  const getSynth = id => document.getElementById(id)?.textContent?.trim() || null;
  return {
    ...payload,
    _synthese: {
      surf_parcelle : getSynth('synth-surf-parc'),
      surf_maison   : getSynth('synth-surf-maison'),
      surf_jardin   : getSynth('synth-surf-jard'),
      surf_terrasse : getSynth('synth-surf-terr'),
      orient_parcelle: getSynth('synth-orient-parc'),
      orient_maison : getSynth('synth-orient-mais'),
      haies         : getSynth('synth-haies'),
      massifs       : getSynth('synth-massifs'),
    },
  };
}

/* -----------------------------------------------
   Send message
   ----------------------------------------------- */
async function sendMessage() {
  if (_isStreaming) return;

  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text) return;

  // Hide welcome message on first message
  const welcome = document.getElementById('chat-welcome');
  if (welcome) welcome.style.display = 'none';

  input.value = '';
  input.style.height = '';

  appendMessage('user', safeMarkdown(text));
  chatHistory.push({ role: 'user', content: text });

  _isStreaming = true;
  const statusEl = document.getElementById('chat-status');
  if (statusEl) statusEl.textContent = 'En train de répondre…';
  appendTypingIndicator();

  const requestBody = JSON.stringify({
    question: text,
    terrain:  _buildTerrainContext(),
    history:  chatHistory.slice(0, -1),
  });

  let assistantDiv = null;
  let fullText     = '';

  try {
    const response = await fetch('/agent/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    requestBody,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }

    removeTypingIndicator();

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;

        let event;
        try { event = JSON.parse(line.slice(6)); }
        catch (_) { continue; }

        if (event.type === 'text_delta') {
          if (!assistantDiv) {
            assistantDiv = document.createElement('div');
            assistantDiv.className = 'chat-message chat-message-assistant';
            document.getElementById('chat-messages').appendChild(assistantDiv);
          }
          fullText += event.text;
          assistantDiv.innerHTML = safeMarkdown(fullText);
          scrollToBottom();

        } else if (event.type === 'tool_start') {
          const div = document.createElement('div');
          div.id        = `tool-${event.name}`;
          div.className = 'chat-tool-running';
          div.innerHTML = `<span class="tool-spinner"></span> ${event.label}…`;
          document.getElementById('chat-messages').appendChild(div);
          scrollToBottom();

        } else if (event.type === 'tool_done') {
          const div = document.getElementById(`tool-${event.name}`);
          if (div) {
            div.className = `chat-tool-done ${event.success ? 'success' : 'error'}`;
            div.innerHTML = `${event.success ? '✓' : '✗'} ${event.label}`;
          }

        } else if (event.type === 'done') {
          if (!assistantDiv && event.full_text) {
            appendMessage('assistant', safeMarkdown(event.full_text));
          }
          chatHistory.push({ role: 'assistant', content: event.full_text || fullText });

        } else if (event.type === 'error') {
          removeTypingIndicator();
          appendMessage('assistant', `<em style="color:#c62828">Erreur : ${event.message}</em>`);
          chatHistory.pop();
        }
      }
    }

  } catch (err) {
    removeTypingIndicator();
    appendMessage('assistant', `<em style="color:#c62828">Erreur de connexion : ${err.message}</em>`);
    chatHistory.pop();
  } finally {
    _isStreaming = false;
    if (statusEl) statusEl.textContent = 'En ligne';
  }
}

/* -----------------------------------------------
   Event listeners
   ----------------------------------------------- */
document.getElementById('chat-toggle')?.addEventListener('click', toggleChat);
document.getElementById('chat-send')?.addEventListener('click', sendMessage);
document.getElementById('chat-close')?.addEventListener('click', toggleChat);

document.getElementById('chat-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

document.getElementById('chat-input')?.addEventListener('input', function () {
  this.style.height = '';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});
