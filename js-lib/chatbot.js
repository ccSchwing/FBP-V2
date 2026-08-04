import { getServiceUrl } from "/js-lib/urlConfig.js";

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('chat-input')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') sendChatBotMessage();
    });
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
        thinking.textContent = response.ok ? data.answer : 'Sorry, I encountered an error. Please try again.';
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
    div.textContent = message;
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
