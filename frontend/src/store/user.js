import { defineStore } from 'pinia'
export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userId: localStorage.getItem('userId') || ''
  }),
  actions: {
    setToken(token, id) {
      this.token = token
      this.userId = id
      localStorage.setItem('token', token)
      localStorage.setItem('userId', id)
    }
  }
})