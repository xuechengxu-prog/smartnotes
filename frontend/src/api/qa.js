import request from './request.js'

export const askQuestion = (data) => request.post('/qa/ask', data)
