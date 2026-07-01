import request from './request.js'

export const generatePlan = (data) => request.post('/plan/generate', data)
