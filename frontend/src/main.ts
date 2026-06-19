import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import './styles.css'

const pinia = createPinia()

pinia.use(({ store }) => {
  const key = `sentinel:${store.$id}`
  const saved = localStorage.getItem(key)
  if (saved) {
    store.$patch(JSON.parse(saved))
  }
  store.$subscribe((_, state) => {
    localStorage.setItem(key, JSON.stringify(state))
  })
})

createApp(App).use(pinia).use(router).mount('#app')
