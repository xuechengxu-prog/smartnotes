import request from './request'

/**
 * 添加文本到知识库
 */
export const addKnowledgeText = (data) => {
  return request({
    url: '/knowledge/add/text',
    method: 'post',
    data
  })
}

/**
 * 搜索知识库（语义搜索）
 * @param {Object} params - 搜索参数
 * @param {string} params.query - 搜索关键词
 * @param {string} params.collection_name - 集合名称，默认 'default'
 * @param {number} params.n_results - 返回结果数量，默认 5
 */
export const searchKnowledge = (params) => {
  return request({
    url: '/knowledge/search',
    method: 'get',
    params
  })
}

/**
 * 获取用户所有知识库 collection 列表
 */
export const getCollections = () => {
  return request({
    url: '/knowledge/collections',
    method: 'get',
  })
}

/**
 * 创建新的知识库 collection
 * @param {Object} data - { collection_name: string }
 */
export const createCollection = (data) => {
  return request({
    url: '/knowledge/collections',
    method: 'post',
    data,
  })
}
