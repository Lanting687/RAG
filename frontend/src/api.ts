export async function sendChatMessage(question: string) {
  const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
  const response = await fetch(`${apiUrl}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ question }),
  })

  if (!response.ok) {
    let errorMessage = 'Unable to reach the chatbot API'
    try {
      const body = await response.json()
      if (body?.detail) {
        errorMessage = body.detail
      }
    } catch {
      // Ignore JSON parse failures
    }
    throw new Error(errorMessage)
  }

  return response.json()
}
