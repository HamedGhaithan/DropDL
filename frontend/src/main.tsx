import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import PlayerApp from './PlayerApp'
import EditorApp from './EditorApp'
import ErrorBoundary from './ErrorBoundary'
import {reportDiagnostic} from './api'
import './styles.css'
import './upgrade.css'
import './upgrade2.css'
import './studio.css'
import './custom-studio.css'
import './editor.css'
import './editor-v2.css'
import './v2.css'
import '@fontsource-variable/inter'
import '@fontsource/ibm-plex-sans-arabic/400.css'
import '@fontsource/ibm-plex-sans-arabic/500.css'
import '@fontsource/ibm-plex-sans-arabic/600.css'
import '@fontsource/ibm-plex-sans-arabic/700.css'
import './design.css'
import './editor-design.css'
import './shell.css'
import './editor-pro.css'
import { startDesktopBackend } from './desktop'

window.addEventListener('error',event=>reportDiagnostic('ui-error',event.error?.stack||event.message))
window.addEventListener('unhandledrejection',event=>reportDiagnostic('ui-unhandled-rejection',String(event.reason?.stack||event.reason)))
reportDiagnostic('ui-started')
void startDesktopBackend()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>{new URLSearchParams(location.search).get('player')?<PlayerApp/>:new URLSearchParams(location.search).get('editor')?<EditorApp sourceId={new URLSearchParams(location.search).get('editor')!}/>:<App />}</ErrorBoundary>
  </React.StrictMode>,
)
