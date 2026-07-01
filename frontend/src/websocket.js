export default class SocketService {
  constructor(userId) {
    this.userId = userId
    this.socket = null
    this.onMessage = null
  }

  connect() {
    this.socket = new WebSocket(`ws://localhost/ws/${this.userId}`)
    this.socket.onmessage = (res) => {
      if (this.onMessage) this.onMessage(JSON.parse(res.data))
    }
  }

  send(data) {
    this.socket.send(JSON.stringify(data))
  }
}