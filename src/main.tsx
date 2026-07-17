import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { CustomerChat } from './customer/CustomerChat.tsx'

const customerPage = window.location.pathname.replace(/\/+$/, '') === '/customer'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {customerPage ? <CustomerChat /> : <App />}
  </StrictMode>,
)
