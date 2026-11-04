import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const app = createApp(App)
app.config.errorHandler = (error) => {
  console.error('Error de interfaz de Songo', error)
  window.dispatchEvent(new Event('songo:app-error'))
}
app.mount('#app')
