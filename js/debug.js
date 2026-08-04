// debug.js - Utility for debugging OIDC authentication

// Enable debug mode
const DEBUG_MODE = false

// Debug logger
export function debugLog(category, message, data) {
  if (DEBUG_MODE) {
    if (data !== undefined) {
      console.log(`%c[${category}] ${message}`, "color: blue;", data)
    } else {
      console.log(`%c[${category}] ${message}`, "color: blue;")
    }
  }
}

// Add debug info to the page (for development only)
export function addDebugInfoToPage() {
  if (DEBUG_MODE) {
    const debugDiv = document.createElement("div")
    debugDiv.id = "oidc-debug"
    debugDiv.style.cssText =
      "position: fixed; bottom: 0; right: 0; background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; z-index: 9999;"
    document.body.appendChild(debugDiv)
  }
}

// Update the debug panel with auth status
export async function updateDebugPanel(auth) {
  if (DEBUG_MODE) {
    const debugDiv = document.getElementById("oidc-debug")
    if (debugDiv) {
      debugDiv.innerHTML = `
        <h3>Authentication Status</h3>
        <pre>${JSON.stringify(auth, null, 2)}</pre>
      `
    }
  }
}

// Export a function to initialize debugging
export function initializeDebugging(userManager) {
  if (DEBUG_MODE) {
   
    if(window.oidc){
      // Enable OIDC-Client logging
      oidc.Log.setLogger(console)
      oidc.Log.setLevel(oidc.Log.INFO)
    }
      
    addDebugInfoToPage()
    userManager.events.addUserLoaded(async (user) => {
      await updateDebugPanel(user)
    })
    userManager.events.addUserUnloaded(() => {
      updateDebugPanel(null)
    })
    userManager.events.addSilentRenewError((error) => {
      debugLog("Silent Renew Error", error)
    })
    userManager.events.addAccessTokenExpiring(() => {
      debugLog("Access Token Expiring")
    })
    userManager.events.addAccessTokenExpired(() => {
      debugLog("Access Token Expired")
    })
    userManager.events.addUserSignedOut(() => {
      debugLog("User Signed Out")
    })
  }

  return { debugLog }
}

