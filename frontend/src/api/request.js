import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      const status = error.response.status
      const detail = error.response.data?.detail || '请求失败'
      const url = error.config?.url || ''

      // 登录接口的 401：用户名或密码错误
      if (status === 401 && url.includes('/auth/login')) {
        ElMessage.error('用户名或密码错误')
      }
      // 注册接口的 422：参数验证失败
      else if (status === 422 && url.includes('/auth/register')) {
        ElMessage.error(detail)
      }
      // 其他接口的 401：token 过期
      else if (status === 401) {
        ElMessage.error('登录已过期，请重新登录')
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        window.location.href = '/login'
      }
      else if (status === 422) {
        ElMessage.error(detail)
      }
      else {
        ElMessage.error(detail)
      }
    } else {
      ElMessage.error('网络错误，请检查连接')
    }
    return Promise.reject(error)
  }
)

export default request
