import {Component, ErrorInfo, ReactNode} from 'react'
import {Language, translate} from './i18n'
import {API_BASE,reportDiagnostic} from './api'

export default class ErrorBoundary extends Component<{children:ReactNode},{error:Error|null}> {
  state:{error:Error|null}={error:null}
  static getDerivedStateFromError(error:Error){return {error}}
  componentDidCatch(error:Error,info:ErrorInfo){
    reportDiagnostic('ui-render-error',`${error.stack||error.message}\n${info.componentStack}`)
    console.error('DropDL interface error',error,info.componentStack)
    try{localStorage.setItem('dropdl-last-ui-error',`${error.stack||error.message}\n${info.componentStack}`)}catch{}
  }
  render(){
    if(!this.state.error)return this.props.children
    let lang:Language='en'
    try{if(localStorage.getItem('dropdl-language')==='ar')lang='ar'}catch{}
    return <main className="ui-recovery" dir={lang==='ar'?'rtl':'ltr'} role="alert">
      <h1>{translate(lang,'interfaceError')}</h1><p>{translate(lang,'interfaceRecovery')}</p>
      <pre dir="ltr">{this.state.error.message}</pre>
      <button className="primary" onClick={()=>window.location.reload()}>{translate(lang,'reload')}</button>
      <a className="secondary link-button" onClick={e=>{if(window.pywebview?.api.export_diagnostics){e.preventDefault();void window.pywebview.api.export_diagnostics().catch(()=>{})}}} href={API_BASE+"/api/support/bundle"}>{lang==='ar'?'تصدير تقرير التشخيص':'Export diagnostics'}</a>
    </main>
  }
}
