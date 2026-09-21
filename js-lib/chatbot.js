// Import marked.min.js for Markdown parsing
import { marked, parse } from '/js-lib/marked.esm.js';
// Don't know if I need DOMPurify since the only HTML is mine.
// import DOMPurify from '/js-lib/purify.min.js';

import { getServiceUrl } from "/js-lib/urlConfig.js";

document.addEventListener('DOMContentLoaded', () => {
    if (!document.getElementById('chat-widget')) {
        document.body.insertAdjacentHTML('beforeend', `
            <div id="chat-widget">
                <button id="chat-toggle" onclick="document.getElementById('chat-widget').classList.toggle('open')" aria-label="Toggle chat">
                    💬 FBP Assistant
                </button>
                <div id="chat-body">
                    <div id="chat-messages"></div>
                    <div id="chat-input-row">
                        <input type="text" id="chat-input" placeholder="Ask me about FBP..." autocomplete="off">
                        <button id="chat-send" onclick="window.sendChatBotMessage()">Send</button>
                    </div>
                </div>
            </div>`);
    }
    document.getElementById('chat-input').addEventListener('keydown', e => {
        if (e.key === 'Enter') sendChatBotMessage();
    });
    window.sendChatBotMessage = sendChatBotMessage;
});

export async function sendChatBotMessage() {
    const input = document.getElementById('chat-input');
    const question = input.value.trim();
    if (!question) return;

    addMessage('user', question);
    input.value = '';

    const thinking = addMessage('bot thinking', '...');

    try {
        const apiEndpoint = await getServiceUrl("chatbot");
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question, sessionId: getSessionId() })
        });
        const data = await response.json();
        if (response.ok) {
            let html = marked(data.answer);
            if (data.sources?.length) {
                html += '<div class="chat-sources"><strong>Sources:</strong><ul>'
                    + data.sources.map(s => `<li>[${s.citation}] ${s.uri}</li>`).join('')
                    + '</ul></div>';
            }
            thinking.innerHTML = html;
        } else {
            thinking.innerHTML = 'Sorry, I encountered an error. Please try again.';
        }
        // data.answer contains the chatbot's response.
        thinking.classList.remove('thinking');
    } catch (error) {
        console.error('Error:', error);
        thinking.textContent = 'Sorry, I could not connect to the server.';
        thinking.classList.remove('thinking');
    }
}

function addMessage(classes, message) {
    const messagesDiv = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'msg ' + classes;
    div.innerHTML = marked(message);
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return div;
}

function getSessionId() {
    let sessionId = localStorage.getItem('fbp-chat-session');
    if (!sessionId) {
        sessionId = 'session-' + Date.now();
        localStorage.setItem('fbp-chat-session', sessionId);
    }
    return sessionId;
}
