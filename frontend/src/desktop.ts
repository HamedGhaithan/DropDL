let childStarted = false

export async function startDesktopBackend() {
  if (!('__TAURI_INTERNALS__' in window) || childStarted) return
  childStarted = true
  try {
    const { Command } = await import('@tauri-apps/plugin-shell')
    const command = Command.sidecar('binaries/dropdl-backend')
    await command.spawn()
  } catch (error) {
    childStarted = false
    console.error('Could not start DropDL backend sidecar:', error)
  }
}
