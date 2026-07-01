import { reactive } from 'vue'

const cache = reactive({
  note: {
    content: '',
    result: ''
  },
  plan: {
    subject: '',
    examDate: '',
    result: '',
    dailyHours: 4
  },
  qa: {
    question: '',
    result: ''
  },
  knowledge: {
    textContent: '',
    collectionName: 'default',
    searchQuery: '',
    searchCollection: 'default'
  }
})

const cacheStore = {
  get: (module) => cache[module] || {},
  
  set: (module, data) => {
    if (cache[module]) {
      Object.assign(cache[module], data)
    }
  },
  
  clear: (module) => {
    if (cache[module]) {
      Object.keys(cache[module]).forEach(key => {
        cache[module][key] = ''
      })
    }
  },
  
  clearAll: () => {
    Object.keys(cache).forEach(module => {
      Object.keys(cache[module]).forEach(key => {
        cache[module][key] = ''
      })
    })
  }
}

export default cacheStore
