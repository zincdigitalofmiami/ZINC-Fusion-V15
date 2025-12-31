import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/sentiment',
    name: 'Sentiment',
    component: () => import('../views/Sentiment.vue'),
  },
  {
    path: '/legislation',
    name: 'Legislation',
    component: () => import('../views/Legislation.vue'),
  },
  {
    path: '/strategy',
    name: 'Strategy',
    component: () => import('../views/Strategy.vue'),
  },
  {
    path: '/vegas-intel',
    name: 'VegasIntel',
    component: () => import('../views/VegasIntel.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
