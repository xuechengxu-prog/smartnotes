import request from './request.js'

export const organizeNote = (data) => request.post('/note/organize', data)
