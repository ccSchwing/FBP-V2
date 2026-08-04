// Simple chatbot integration
async function askFootballBot(question) {
    const response = await fetch('YOUR_API_ENDPOINT', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            question: question,
            knowledgeBaseId: 'YOUR_KB_ID'
        })
    });
    
    const answer = await response.json();
    return answer.response;
}
